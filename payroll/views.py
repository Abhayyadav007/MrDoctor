from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db import IntegrityError
from django.db.models import Avg, Count
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from accounts.models import User
from cases.models import Case
from accounts.access import case_for_user
from .forms import (
    DoctorRatingForm,
    DoctorCompensationForm,
    PayrollAdjustmentForm,
    PayrollGenerationForm,
    RatingBonusSettingsForm,
)
from .models import (
    DoctorCompensation,
    DoctorRating,
    PayrollAdjustment,
    PayrollAudit,
    PayrollRecord,
    RatingBonusTier,
)


class AdminRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != User.Role.ADMIN and not request.user.is_superuser:
            return HttpResponseForbidden("Administrator access is required.")
        return super().dispatch(request, *args, **kwargs)


class DoctorRatingCreateView(LoginRequiredMixin, View):
    def post(self, request, case_id):
        case = case_for_user(request.user, case_id)
        if request.user.role != User.Role.PATIENT:
            return HttpResponseForbidden("Only the patient may rate this case.")
        if case.status not in (Case.Status.RECOVERED, Case.Status.CLOSED) or not case.doctor_id:
            return HttpResponseForbidden("Ratings are available after a doctor closes or recovers a case.")
        form = DoctorRatingForm(request.POST)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.case, rating.patient, rating.doctor = case, request.user, case.doctor
            try:
                rating.full_clean()
                rating.save()
            except ValidationError:
                messages.error(request, "You have already rated this case or the rating is invalid.")
                return redirect("case_detail", pk=case.pk)
            except IntegrityError:
                messages.error(request, "You have already rated this case.")
                return redirect("case_detail", pk=case.pk)
            messages.success(request, "Thank you. Your rating was recorded.")
        else:
            messages.error(request, "Please choose a rating from 1 to 5 stars.")
        return redirect("case_detail", pk=case.pk)


class PayrollDashboardView(AdminRequiredMixin, View):
    def get(self, request):
        doctors = User.objects.filter(role=User.Role.DOCTOR).annotate(
            average_rating=Avg("received_doctor_ratings__score"),
            rating_count=Count("received_doctor_ratings"),
        ).order_by("last_name", "first_name")
        for doctor in doctors:
            doctor.pay_profile = DoctorCompensation.objects.filter(doctor=doctor).first()
        return render(request, "payroll/dashboard.html", {
            "doctors": doctors,
            "records": PayrollRecord.objects.select_related("doctor").prefetch_related("adjustments")[:50],
            "salary_form": DoctorCompensationForm(),
            "bonus_form": RatingBonusSettingsForm(),
            "generation_form": PayrollGenerationForm(initial={"month": timezone.localdate().strftime("%Y-%m")}),
        })


class CompensationUpdateView(AdminRequiredMixin, View):
    def post(self, request):
        form = DoctorCompensationForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Check the salary form and try again.")
            return redirect("payroll_dashboard")
        doctor = form.cleaned_data["doctor"]
        new_salary = form.cleaned_data["base_monthly_salary"]
        reason = form.cleaned_data["reason"]
        with transaction.atomic():
            profile, _ = DoctorCompensation.objects.select_for_update().get_or_create(doctor=doctor)
            old_salary = profile.base_monthly_salary
            profile.base_monthly_salary = new_salary
            profile.updated_by = request.user
            profile.save(update_fields=["base_monthly_salary", "updated_by", "updated_at"])
            PayrollAudit.objects.create(
                actor=request.user,
                action="Base salary changed",
                details=f"{doctor} · INR {old_salary} -> INR {new_salary}. Reason: {reason}",
            )
        messages.success(request, "Monthly base salary updated and audit recorded.")
        return redirect("payroll_dashboard")


class BonusTierUpdateView(AdminRequiredMixin, View):
    def post(self, request):
        form = RatingBonusSettingsForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Bonus tiers must be non-negative INR amounts.")
            return redirect("payroll_dashboard")
        with transaction.atomic():
            form.save(request.user)
            PayrollAudit.objects.create(
                actor=request.user,
                action="Rating bonus tiers updated",
                details="Updated monthly INR bonus amounts for 1–5 star ratings.",
            )
        messages.success(request, "Rating bonus tiers saved.")
        return redirect("payroll_dashboard")


class PayrollGenerateView(AdminRequiredMixin, View):
    def post(self, request):
        form = PayrollGenerationForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Choose a valid payroll month.")
            return redirect("payroll_dashboard")
        period = form.cleaned_data["month"]
        tiers = {tier.stars: tier.monthly_bonus for tier in RatingBonusTier.objects.all()}
        created_count = 0
        updated_count = 0
        with transaction.atomic():
            doctors = User.objects.filter(role=User.Role.DOCTOR).order_by("pk")
            for doctor in doctors:
                existing = PayrollRecord.objects.select_for_update().filter(doctor=doctor, period=period).first()
                if existing and existing.status != PayrollRecord.Status.DRAFT:
                    continue
                rating_stats = DoctorRating.objects.filter(
                    doctor=doctor,
                    created_at__year=period.year,
                    created_at__month=period.month,
                ).aggregate(average=Avg("score"), count=Count("id"))
                average = rating_stats["average"]
                average_rating = Decimal(str(average)).quantize(Decimal("0.01")) if average is not None else None
                rounded_stars = int(average_rating.quantize(Decimal("1"), rounding=ROUND_HALF_UP)) if average_rating else 0
                rating_bonus = tiers.get(rounded_stars, Decimal("0.00"))
                compensation = DoctorCompensation.objects.filter(doctor=doctor).first()
                base_salary = compensation.base_monthly_salary if compensation else Decimal("0.00")
                _, created = PayrollRecord.objects.update_or_create(
                    doctor=doctor,
                    period=period,
                    defaults={
                        "base_salary": base_salary,
                        "average_rating": average_rating,
                        "rating_count": rating_stats["count"] or 0,
                        "rating_bonus": rating_bonus,
                        "status": PayrollRecord.Status.DRAFT,
                        "generated_by": request.user,
                        "paid_at": None,
                    },
                )
                created_count += int(created)
                updated_count += int(not created)
            PayrollAudit.objects.create(
                actor=request.user,
                action="Payroll generated",
                details=f"{period:%B %Y}: {created_count} new, {updated_count} draft records refreshed.",
            )
        messages.success(request, f"Payroll prepared for {period:%B %Y}. Paid or approved records were left unchanged.")
        return redirect("payroll_dashboard")


class PayrollAdjustmentCreateView(AdminRequiredMixin, View):
    def post(self, request, payroll_id):
        payroll = get_object_or_404(PayrollRecord, pk=payroll_id)
        if payroll.status != PayrollRecord.Status.DRAFT:
            messages.error(request, "Only draft payroll records may be adjusted.")
            return redirect("payroll_dashboard")
        form = PayrollAdjustmentForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Enter a non-zero INR adjustment and a reason.")
            return redirect("payroll_dashboard")
        with transaction.atomic():
            adjustment = form.save(commit=False)
            adjustment.payroll = payroll
            adjustment.actor = request.user
            adjustment.save()
            PayrollAudit.objects.create(
                actor=request.user,
                action="Payroll adjustment",
                details=f"{payroll.doctor} · {payroll.period:%B %Y} · INR {adjustment.amount:+}. {adjustment.reason}",
            )
        messages.success(request, "Payroll adjustment recorded.")
        return redirect("payroll_dashboard")


class PayrollStatusUpdateView(AdminRequiredMixin, View):
    def post(self, request, payroll_id):
        payroll = get_object_or_404(PayrollRecord, pk=payroll_id)
        decision = request.POST.get("status")
        allowed = {
            PayrollRecord.Status.DRAFT: PayrollRecord.Status.APPROVED,
            PayrollRecord.Status.APPROVED: PayrollRecord.Status.PAID,
        }
        if allowed.get(payroll.status) != decision:
            messages.error(request, "Payroll status must move from Draft to Approved, then to Paid.")
            return redirect("payroll_dashboard")
        old_status = payroll.status
        payroll.status = decision
        payroll.paid_at = timezone.now() if decision == PayrollRecord.Status.PAID else None
        payroll.save(update_fields=["status", "paid_at"])
        PayrollAudit.objects.create(
            actor=request.user,
            action="Payroll status changed",
            details=f"{payroll.doctor} · {payroll.period:%B %Y}: {old_status} -> {payroll.status}",
        )
        messages.success(request, f"Payroll marked {payroll.get_status_display().lower()}.")
        return redirect("payroll_dashboard")

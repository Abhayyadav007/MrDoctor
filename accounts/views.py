from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from appointments.models import Appointment
from cases.models import Case
from notifications.models import Notification
from .access import RoleRequiredMixin
from .forms import AccountProfileForm, PatientProfileForm
from .models import DoctorProfile, PatientProfile, User


class DashboardView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        if user.role == User.Role.ADMIN or user.is_superuser:
            statuses = list(Case.objects.values("status").annotate(total=Count("id")).order_by("status"))
            doctors = list(User.objects.filter(role=User.Role.DOCTOR).annotate(total=Count("assigned_cases")))
            today = timezone.localdate()
            week_start = today - timedelta(days=today.weekday())
            week_dates = [week_start + timedelta(days=i) for i in range(7)]
            week_rows = Appointment.objects.filter(date__gte=week_dates[0], date__lte=week_dates[-1]).values(
                "date").annotate(total=Count("id"))
            by_date = {row["date"]: row["total"] for row in week_rows}
            appointment_stats = [{"day": day.strftime("%a"), "total": by_date.get(day, 0)} for day in week_dates]
            appointments = sum(by_date.values())
            return render(request, "accounts/dashboard_admin.html", {
                "users": User.objects.count(), "cases": Case.objects.count(),
                "doctors": User.objects.filter(role=User.Role.DOCTOR).count(),
                "statuses": statuses, "doctor_stats": doctors, "week_appointments": appointments,
                "appointment_stats": appointment_stats,
            })
        if user.role == User.Role.DOCTOR:
            cases = Case.objects.filter(doctor=user).select_related("patient")
            status = request.GET.get("status", "")
            priority = request.GET.get("priority", "")
            if status:
                cases = cases.filter(status=status)
            if priority:
                cases = cases.filter(priority=priority)
            return render(request, "accounts/dashboard_doctor.html", {
                "cases": cases, "appointments": Appointment.objects.filter(doctor=user).exclude(
                    status__in=[Appointment.Status.REJECTED, Appointment.Status.COMPLETED]),
                "statuses": Case.Status.choices, "priorities": Case.Priority.choices,
            })
        return render(request, "accounts/dashboard_patient.html", {
            "cases": Case.objects.filter(patient=user),
            "appointments": Appointment.objects.filter(patient=user).select_related("doctor"),
            "profile": PatientProfile.objects.filter(user=user).first(),
        })


class ProfileView(LoginRequiredMixin, View):
    def get(self, request):
        context = {"account_form": AccountProfileForm(instance=request.user)}
        if request.user.role == User.Role.PATIENT:
            profile, _ = PatientProfile.objects.get_or_create(user=request.user)
            context["form"] = PatientProfileForm(instance=profile)
        return render(request, "accounts/profile.html", context)

    def post(self, request):
        account_form = AccountProfileForm(request.POST, request.FILES, instance=request.user)
        profile_form = None
        if request.user.role == User.Role.PATIENT:
            profile, _ = PatientProfile.objects.get_or_create(user=request.user)
            profile_form = PatientProfileForm(request.POST, instance=profile)
        if account_form.is_valid() and (profile_form is None or profile_form.is_valid()):
            account_form.save()
            if profile_form:
                profile_form.save()
            messages.success(request, "Profile updated.")
            return redirect("profile")
        context = {"account_form": account_form, "form": profile_form}
        return render(request, "accounts/profile.html", context)


class PatientDirectoryView(RoleRequiredMixin, ListView):
    allowed_roles = (User.Role.ADMIN, User.Role.DOCTOR)
    model = User
    template_name = "accounts/patient_list.html"
    context_object_name = "patients"
    paginate_by = 20

    def get_queryset(self):
        qs = User.objects.filter(role=User.Role.PATIENT).order_by("last_name", "first_name")
        query = self.request.GET.get("q", "")
        if query:
            qs = qs.filter(first_name__icontains=query) | qs.filter(last_name__icontains=query) | qs.filter(username__icontains=query)
        return qs


class DoctorCreateView(RoleRequiredMixin, View):
    allowed_roles = (User.Role.ADMIN,)
    template_name = "accounts/doctor_create.html"

    def get(self, request):
        return render(request, self.template_name)

    def post(self, request):
        from django.contrib.auth import get_user_model
        from django.db import transaction
        UserModel = get_user_model()
        data = request.POST
        required = ["username", "email", "password", "first_name", "last_name", "specialization"]
        if any(not data.get(field) for field in required):
            messages.error(request, "Complete all required fields.")
            return render(request, self.template_name)
        if UserModel.objects.filter(username=data["username"]).exists():
            messages.error(request, "That username is already in use.")
            return render(request, self.template_name)
        with transaction.atomic():
            doctor = UserModel.objects.create_user(
                username=data["username"], email=data["email"], password=data["password"],
                first_name=data["first_name"], last_name=data["last_name"],
                phone=data.get("phone", ""), role=User.Role.DOCTOR,
            )
            DoctorProfile.objects.create(user=doctor, specialization=data["specialization"],
                                          experience=data.get("experience") or 0,
                                          availability=data.get("availability", ""))
        messages.success(request, "Doctor account created.")
        return redirect("dashboard")

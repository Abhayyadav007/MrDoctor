from pathlib import Path
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from accounts.access import case_for_user
from accounts.models import User
from notifications.models import Notification
from .forms import AttachmentForm, CaseAssignmentForm, CaseForm, VisitForm
from .models import Attachment, Case, CaseAudit, Visit
from payroll.forms import DoctorRatingForm
from payroll.models import DoctorRating


class CaseListView(LoginRequiredMixin, ListView):
    model = Case
    template_name = "cases/case_list.html"
    context_object_name = "cases"
    paginate_by = 15

    def get_queryset(self):
        user = self.request.user
        qs = Case.objects.select_related("patient", "doctor")
        if user.is_superuser or user.role == User.Role.ADMIN:
            pass
        elif user.role == User.Role.PATIENT:
            qs = qs.filter(patient=user)
        elif user.role == User.Role.DOCTOR:
            qs = qs.filter(doctor=user)
        else:
            return qs.none()
        term = self.request.GET.get("q", "")
        status = self.request.GET.get("status", "")
        if term:
            qs = qs.filter(Q(title__icontains=term) | Q(description__icontains=term) |
                           Q(patient__first_name__icontains=term) | Q(patient__last_name__icontains=term))
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = Case.Status.choices
        return context


class CaseCreateView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != User.Role.PATIENT:
            raise PermissionDenied
        return render(request, "cases/case_form.html", {"form": CaseForm()})

    def post(self, request):
        if request.user.role != User.Role.PATIENT:
            raise PermissionDenied
        form = CaseForm(request.POST)
        if form.is_valid():
            case = form.save(commit=False)
            case.patient = request.user
            case.save()
            CaseAudit.objects.create(case=case, actor=request.user, action="Case created")
            messages.success(request, "Case created.")
            return redirect("case_detail", pk=case.pk)
        return render(request, "cases/case_form.html", {"form": form})


class CaseDetailView(LoginRequiredMixin, View):
    def get(self, request, pk):
        case = case_for_user(request.user, pk)
        existing_rating = DoctorRating.objects.filter(case=case).first() if request.user.role == User.Role.PATIENT else None
        can_treat = request.user.role in (User.Role.DOCTOR, User.Role.ADMIN) and (
            request.user.is_superuser or request.user.role == User.Role.ADMIN or case.doctor_id == request.user.id)
        can_rate = (
            request.user.role == User.Role.PATIENT
            and case.status in (Case.Status.RECOVERED, Case.Status.CLOSED)
            and case.doctor_id is not None
            and existing_rating is None
        )
        return render(request, "cases/case_detail.html", {
            "case": case, "can_treat": can_treat,
            "visit_form": VisitForm(), "attachment_form": AttachmentForm(),
            "assignment_form": CaseAssignmentForm(instance=case)
            if request.user.role == User.Role.ADMIN or request.user.is_superuser else None,
            "can_rate": can_rate, "rating_form": DoctorRatingForm() if can_rate else None,
            "existing_rating": existing_rating,
        })


class AddVisitView(LoginRequiredMixin, View):
    def post(self, request, pk):
        case = case_for_user(request.user, pk)
        if request.user.role != User.Role.DOCTOR or case.doctor_id != request.user.id:
            raise PermissionDenied
        form = VisitForm(request.POST)
        if form.is_valid():
            visit = form.save(commit=False)
            visit.case, visit.doctor = case, request.user
            visit.save()
            CaseAudit.objects.create(case=case, actor=request.user, action="Visit added",
                                     details=f"Visit recorded: {visit.diagnosis[:160]}")
            Notification.objects.create(recipient=case.patient, message="Your doctor added a visit to your case.",
                                        url=f"/cases/{case.pk}/")
            messages.success(request, "Visit added to the case.")
        else:
            messages.error(request, "Please correct the visit form.")
        return redirect("case_detail", pk=pk)


class CaseUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        case = case_for_user(request.user, pk)
        if request.user.role == User.Role.ADMIN or request.user.is_superuser:
            form = CaseAssignmentForm(request.POST, instance=case)
            if form.is_valid():
                previous = case.doctor
                previous_status = case.status
                updated = form.save()
                if updated.status != previous_status:
                    updated.closed_at = timezone.now() if updated.status == Case.Status.CLOSED else None
                    updated.save(update_fields=["closed_at"])
                CaseAudit.objects.create(case=case, actor=request.user, action="Case updated",
                                         details=f"Doctor: {previous or 'Unassigned'} -> {updated.doctor or 'Unassigned'}; "
                                                 f"Status: {updated.status}; Priority: {updated.priority}")
                if updated.doctor:
                    Notification.objects.create(recipient=updated.doctor, message=f"Case assigned: {case.title}",
                                                url=f"/cases/{case.pk}/")
                messages.success(request, "Case assignment and status updated.")
        elif request.user.role == User.Role.DOCTOR and case.doctor_id == request.user.id:
            status = request.POST.get("status")
            valid = [value for value, _ in Case.Status.choices]
            if status not in valid:
                raise PermissionDenied
            old_status = case.status
            case.status = status
            case.closed_at = timezone.now() if status == Case.Status.CLOSED else None
            case.save(update_fields=["status", "closed_at"])
            CaseAudit.objects.create(case=case, actor=request.user, action="Status changed",
                                     details=f"{old_status} -> {case.status}")
            messages.success(request, "Case status updated.")
        else:
            raise PermissionDenied
        return redirect("case_detail", pk=pk)


class UploadAttachmentView(LoginRequiredMixin, View):
    def post(self, request, pk):
        case = case_for_user(request.user, pk)
        if request.user.role not in (User.Role.PATIENT, User.Role.DOCTOR, User.Role.ADMIN):
            raise PermissionDenied
        form = AttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.case, attachment.uploaded_by = case, request.user
            attachment.save()
            CaseAudit.objects.create(case=case, actor=request.user, action="Attachment uploaded",
                                     details=attachment.description or attachment.file.name)
            messages.success(request, "Report uploaded.")
        else:
            messages.error(request, "Select a valid report file.")
        return redirect("case_detail", pk=pk)


class DownloadAttachmentView(LoginRequiredMixin, View):
    def get(self, request, pk):
        attachment = get_object_or_404(Attachment.objects.select_related("case"), pk=pk)
        case_for_user(request.user, attachment.case_id)
        attachment.file.open("rb")
        response = FileResponse(attachment.file, as_attachment=True, filename=Path(attachment.file.name).name)
        response["Cache-Control"] = "private, no-store"
        return response


class CasePDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        case = case_for_user(request.user, pk)
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="case-{case.pk}-summary.pdf"'
        response["Cache-Control"] = "private, no-store"
        pdf = canvas.Canvas(response, pagesize=letter)
        y = 750
        def line(text, size=11):
            nonlocal y
            pdf.setFont("Helvetica", size)
            for part in str(text).splitlines() or [""]:
                pdf.drawString(48, y, part[:110])
                y -= size + 6
                if y < 60:
                    pdf.showPage()
                    y = 750
        line("Patient Case Tracker - Case Summary", 16)
        line(f"Case #{case.pk}: {case.title}", 13)
        line(f"Patient: {case.patient.get_full_name() or case.patient.username}")
        line(f"Doctor: {case.doctor or 'Not assigned'}")
        line(f"Status: {case.status}    Priority: {case.priority}")
        line(f"Opened: {case.opened_at:%Y-%m-%d}")
        line(f"Description: {case.description}")
        for visit in case.visits.all():
            line(f"Visit {visit.created_at:%Y-%m-%d} - Diagnosis: {visit.diagnosis}")
            line(f"Prescription: {visit.prescription}")
            line(f"Notes: {visit.notes}")
        pdf.save()
        return response


class PatientHistoryView(LoginRequiredMixin, View):
    def get(self, request, patient_id):
        patient = get_object_or_404(User, pk=patient_id, role=User.Role.PATIENT)
        if request.user.role not in (User.Role.DOCTOR, User.Role.ADMIN) and not request.user.is_superuser:
            raise PermissionDenied
        if request.user.role == User.Role.DOCTOR and not Case.objects.filter(patient=patient, doctor=request.user).exists():
            raise PermissionDenied
        cases = Case.objects.filter(patient=patient)
        if request.user.role == User.Role.DOCTOR:
            cases = cases.filter(doctor=request.user)
        return render(request, "cases/patient_history.html", {
            "patient": patient, "cases": cases.prefetch_related("visits"),
        })

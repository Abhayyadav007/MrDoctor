from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from accounts.models import User
from notifications.models import Notification
from .forms import AppointmentRequestForm
from .models import Appointment


class AppointmentRequestView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role != User.Role.PATIENT:
            raise PermissionDenied
        return render(request, "appointments/request.html", {"form": AppointmentRequestForm()})

    def post(self, request):
        if request.user.role != User.Role.PATIENT:
            raise PermissionDenied
        form = AppointmentRequestForm(request.POST)
        if form.is_valid():
            appointment = form.save(commit=False)
            appointment.patient = request.user
            appointment.save()
            Notification.objects.create(recipient=appointment.doctor, message="A patient requested an appointment.",
                                        url="/")
            messages.success(request, "Appointment request sent.")
            return redirect("dashboard")
        return render(request, "appointments/request.html", {"form": form})


class AppointmentDecisionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        appointment = get_object_or_404(Appointment.objects.select_related("patient", "doctor"), pk=pk)
        if request.user.role == User.Role.DOCTOR and appointment.doctor_id != request.user.id:
            return HttpResponseForbidden()
        if request.user.role not in (User.Role.DOCTOR, User.Role.ADMIN) and not request.user.is_superuser:
            return HttpResponseForbidden()
        decision = request.POST.get("decision")
        if decision not in (Appointment.Status.APPROVED, Appointment.Status.REJECTED, Appointment.Status.COMPLETED):
            return HttpResponseForbidden()
        appointment.status = decision
        appointment.save(update_fields=["status"])
        Notification.objects.create(recipient=appointment.patient, message=f"Your appointment was {decision.lower()}.")
        messages.success(request, f"Appointment {decision.lower()}.")
        return redirect("dashboard")

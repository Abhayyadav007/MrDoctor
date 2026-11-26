from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View

from accounts.models import User
from .forms import EmployeeRemarkForm, StaffMeetingForm
from .models import EmployeeRemark, StaffMeeting, StaffMessage
from .permissions import can_manage_employee, can_staff_chat, managed_employees, staff_chat_peers


class ManagerRequiredMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.role != User.Role.ADMIN:
            return HttpResponseForbidden("Manager access is required.")
        return super().dispatch(request, *args, **kwargs)


def _meeting_scope(user):
    employees = managed_employees(user)
    if user.is_superuser:
        visibility = Q(organizer=user) | Q(attendees__in=employees)
    else:
        visibility = Q(organizer=user) | Q(attendees=user)
    return StaffMeeting.objects.filter(
        visibility,
    ).distinct()


class ManagerDashboardView(ManagerRequiredMixin, View):
    def get(self, request):
        employees = managed_employees(request.user).annotate(remark_count=Count("manager_remarks")).order_by(
            "role", "last_name", "first_name",
        )
        return render(request, "workplace/manager_dashboard.html", {
            "employees": employees,
            "meetings": _meeting_scope(request.user).filter(
                scheduled_at__gte=timezone.now(), status=StaffMeeting.Status.SCHEDULED,
            ).select_related("organizer").prefetch_related("attendees")[:20],
            "meeting_form": StaffMeetingForm(employee_queryset=managed_employees(request.user)),
        })


class EmployeeWorkspaceView(ManagerRequiredMixin, View):
    def get(self, request, employee_id):
        employee = get_object_or_404(User, pk=employee_id)
        if not can_manage_employee(request.user, employee):
            return HttpResponseForbidden("You cannot manage this employee.")
        return render(request, "workplace/employee_workspace.html", {
            "employee": employee,
            "remarks": EmployeeRemark.objects.filter(employee=employee).select_related("author"),
            "remark_form": EmployeeRemarkForm(),
            "meetings": StaffMeeting.objects.filter(
                organizer=request.user, attendees=employee,
            ).select_related("organizer").order_by("-scheduled_at")[:30],
        })


class RemarkCreateView(ManagerRequiredMixin, View):
    def post(self, request, employee_id):
        employee = get_object_or_404(User, pk=employee_id)
        if not can_manage_employee(request.user, employee):
            return HttpResponseForbidden("You cannot add a remark for this employee.")
        form = EmployeeRemarkForm(request.POST)
        if form.is_valid():
            remark = form.save(commit=False)
            remark.author = request.user
            remark.employee = employee
            remark.save()
            messages.success(request, "Your remark was recorded.")
        else:
            messages.error(request, "Enter a remark of no more than 2,400 characters.")
        return redirect("employee_workspace", employee_id=employee.pk)


class MeetingCreateView(ManagerRequiredMixin, View):
    def post(self, request):
        employees = managed_employees(request.user)
        form = StaffMeetingForm(request.POST, employee_queryset=employees)
        if not form.is_valid():
            messages.error(request, "Please correct the meeting details and choose a future date and time.")
            employees = managed_employees(request.user).annotate(remark_count=Count("manager_remarks")).order_by(
                "role", "last_name", "first_name",
            )
            return render(request, "workplace/manager_dashboard.html", {
                "employees": employees,
                "meetings": _meeting_scope(request.user).filter(
                    scheduled_at__gte=timezone.now(), status=StaffMeeting.Status.SCHEDULED,
                ).select_related("organizer").prefetch_related("attendees")[:20],
                "meeting_form": form,
            })
        meeting = form.save(commit=False)
        meeting.organizer = request.user
        meeting.save()
        meeting.attendees.add(request.user, *form.cleaned_data["attendees"])
        messages.success(request, "The staff meeting was scheduled.")
        return redirect("workplace_dashboard")


class MeetingCancelView(ManagerRequiredMixin, View):
    def post(self, request, meeting_id):
        meeting = get_object_or_404(StaffMeeting, pk=meeting_id)
        if meeting.organizer_id != request.user.pk or meeting.status != StaffMeeting.Status.SCHEDULED:
            return HttpResponseForbidden("Only the organizer can cancel a scheduled meeting.")
        meeting.status = StaffMeeting.Status.CANCELLED
        meeting.save(update_fields=["status"])
        messages.success(request, "The meeting was cancelled.")
        return redirect("workplace_dashboard")


class MyStaffWorkView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role == User.Role.PATIENT:
            return HttpResponseForbidden("Staff access is required.")
        return render(request, "workplace/my_work.html", {
            "remarks": EmployeeRemark.objects.filter(employee=request.user).select_related("author"),
            "meetings": StaffMeeting.objects.filter(attendees=request.user).select_related(
                "organizer",
            ).order_by("scheduled_at"),
            "peers": staff_chat_peers(request.user),
        })


class StaffChatListView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role == User.Role.PATIENT:
            return HttpResponseForbidden("Staff access is required.")
        peers = list(staff_chat_peers(request.user))
        for peer in peers:
            peer.last_staff_message = StaffMessage.objects.filter(
                Q(sender=request.user, recipient=peer) | Q(sender=peer, recipient=request.user),
            ).order_by("-created_at").first()
        return render(request, "workplace/chat_list.html", {"peers": peers})


class StaffChatView(LoginRequiredMixin, View):
    def get(self, request, peer_id):
        if request.user.role == User.Role.PATIENT:
            return HttpResponseForbidden("Staff access is required.")
        peer = get_object_or_404(User, pk=peer_id)
        if not can_staff_chat(request.user, peer):
            return HttpResponseForbidden("You cannot open this staff conversation.")
        StaffMessage.objects.filter(sender=peer, recipient=request.user, is_read=False).update(is_read=True)
        recent = list(StaffMessage.objects.filter(
            Q(sender=request.user, recipient=peer) | Q(sender=peer, recipient=request.user),
        ).select_related("sender").order_by("-created_at")[:100])
        recent.reverse()
        return render(request, "workplace/chat_room.html", {
            "peer": peer, "chat_messages": recent,
        })

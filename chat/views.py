import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import render
from django.views import View
from accounts.models import User
from accounts.access import case_for_user
from cases.models import Case
from .models import ChatMessage


class ChatListView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.role == User.Role.PATIENT:
            cases = Case.objects.filter(patient=request.user, doctor__isnull=False)
        elif request.user.role == User.Role.DOCTOR:
            cases = Case.objects.filter(doctor=request.user)
        else:
            raise PermissionDenied
        cases = cases.select_related("patient", "doctor").annotate(
            unread_count=Count("messages", filter=Q(messages__is_read=False) & ~Q(messages__sender=request.user)))
        return render(request, "chat/list.html", {"cases": cases})


class ChatRoomView(LoginRequiredMixin, View):
    def get(self, request, pk):
        case = case_for_user(request.user, pk)
        if not case.doctor_id:
            raise PermissionDenied("A doctor must be assigned before chat is available.")
        if request.user.role not in (User.Role.PATIENT, User.Role.DOCTOR):
            raise PermissionDenied
        messages = case.messages.select_related("sender").all()
        unread_count = messages.filter(is_read=False).exclude(sender=request.user).count()
        messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
        initial = [{
            "id": item.pk, "sender_id": item.sender_id,
            "sender": item.sender.get_full_name() or item.sender.username,
            "text": item.text, "created_at": item.created_at.isoformat(),
        } for item in messages]
        peer = case.doctor if request.user.id == case.patient_id else case.patient
        return render(request, "chat/room.html", {
            "case": case, "peer": peer,
            "initial_messages": json.dumps(initial),
            "unread_count": unread_count,
        })

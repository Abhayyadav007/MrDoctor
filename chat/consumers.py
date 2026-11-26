import json
from threading import Lock
from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.utils import timezone
from calls.models import CallLog
from cases.models import Case
from .models import ChatMessage

_presence_lock = Lock()
_presence = {}


class CaseChatConsumer(WebsocketConsumer):
    def connect(self):
        user = self.scope["user"]
        if not user.is_authenticated:
            self.close(code=4401)
            return
        try:
            self.case = Case.objects.select_related("patient", "doctor").get(pk=self.scope["url_route"]["kwargs"]["case_id"])
        except Case.DoesNotExist:
            self.close(code=4404)
            return
        if user.pk not in (self.case.patient_id, self.case.doctor_id) or not self.case.doctor_id:
            self.close(code=4403)
            return
        self.user = user
        self.group_name = f"case_{self.case.pk}"
        self.peer_id = self.case.doctor_id if user.pk == self.case.patient_id else self.case.patient_id
        with _presence_lock:
            case_presence = _presence.setdefault(self.case.pk, {})
            peer_online = bool(case_presence.get(self.peer_id))
            user_channels = case_presence.setdefault(user.pk, set())
            was_online = bool(user_channels)
            user_channels.add(self.channel_name)
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()
        self.send_json({"type": "presence", "user_id": self.peer_id, "online": peer_online})
        if not was_online:
            self.broadcast({"type": "presence", "user_id": user.pk, "online": True})

    def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            with _presence_lock:
                case_presence = _presence.get(self.case.pk, {})
                user_channels = case_presence.get(self.user.pk, set())
                user_channels.discard(self.channel_name)
                user_offline = not user_channels
                if user_offline:
                    case_presence.pop(self.user.pk, None)
                if not case_presence:
                    _presence.pop(self.case.pk, None)
            call_id = getattr(self, "active_call_id", None)
            if call_id:
                call = CallLog.objects.filter(pk=call_id, status=CallLog.Status.RINGING).first()
                if call:
                    call.ended_at = timezone.now()
                    if getattr(self, "active_call_accepted", False):
                        call.status = CallLog.Status.COMPLETED
                        call.duration = max(0, int((call.ended_at - call.started_at).total_seconds()))
                    else:
                        call.status = CallLog.Status.MISSED
                    call.save(update_fields=["status", "ended_at", "duration"])
            if user_offline:
                self.broadcast({"type": "presence", "user_id": self.user.pk, "online": False})
            async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)

    def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            self.send_json({"type": "error", "message": "Invalid message format."})
            return
        kind = data.get("type")
        if kind == "message":
            text = str(data.get("text", "")).strip()
            if not text or len(text) > 4000:
                self.send_json({"type": "error", "message": "Messages must be 1-4000 characters."})
                return
            message = ChatMessage.objects.create(case=self.case, sender=self.user, text=text)
            self.broadcast({"type": "chat_message", "id": message.pk, "sender_id": self.user.pk,
                            "sender": self.user.get_full_name() or self.user.username, "text": text,
                            "created_at": message.created_at.isoformat()})
        elif kind == "typing":
            self.broadcast({"type": "typing", "user_id": self.user.pk, "active": bool(data.get("active"))})
        elif kind in ("offer", "answer", "ice_candidate", "media_state"):
            self.broadcast({"type": kind, "sender_id": self.user.pk, "payload": data.get("payload")})
        elif kind == "call_start":
            peer = self.case.doctor if self.user.pk == self.case.patient_id else self.case.patient
            call = CallLog.objects.create(case=self.case, caller=self.user, recipient=peer,
                                          audio_only=bool(data.get("audio_only")))
            self.active_call_id = call.pk
            self.active_call_accepted = False
            self.broadcast({"type": "call_invite", "sender_id": self.user.pk, "sender": str(self.user),
                            "call_id": call.pk, "audio_only": call.audio_only})
        elif kind in ("call_accept", "call_reject", "call_end", "call_missed"):
            call_id = data.get("call_id")
            try:
                call = CallLog.objects.get(pk=call_id, case=self.case)
            except (CallLog.DoesNotExist, TypeError, ValueError):
                self.send_json({"type": "error", "message": "Call was not found."})
                return
            if self.user.pk not in (call.caller_id, call.recipient_id):
                self.close(code=4403)
                return
            if kind == "call_accept":
                call.started_at = timezone.now()
                call.save(update_fields=["started_at"])
            elif kind == "call_reject":
                call.status = CallLog.Status.REJECTED
                call.ended_at = timezone.now()
            elif kind == "call_missed":
                call.status = CallLog.Status.MISSED
                call.ended_at = timezone.now()
            elif kind == "call_end":
                call.status = CallLog.Status.COMPLETED
                call.ended_at = timezone.now()
                call.duration = max(0, int((call.ended_at - call.started_at).total_seconds()))
            call.save(update_fields=["status", "ended_at", "duration"])
            self.broadcast({"type": kind, "sender_id": self.user.pk, "call_id": call.pk,
                            "duration": call.duration})
        else:
            self.send_json({"type": "error", "message": "Unsupported event."})

    def broadcast(self, data):
        async_to_sync(self.channel_layer.group_send)(self.group_name, {"type": "relay", "data": data})

    def relay(self, event):
        data = event["data"]
        if data.get("type") == "call_invite" and data.get("sender_id") != self.user.pk:
            self.active_call_id = data["call_id"]
            self.active_call_accepted = False
        elif data.get("type") == "call_accept" and data.get("call_id") == getattr(self, "active_call_id", None):
            self.active_call_accepted = True
        self.send_json(data)

    def send_json(self, data):
        self.send(text_data=json.dumps(data))

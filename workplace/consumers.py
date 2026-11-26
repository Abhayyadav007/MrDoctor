import json

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer

from accounts.models import User
from .models import StaffMessage
from .permissions import can_staff_chat


class StaffChatConsumer(WebsocketConsumer):
    def connect(self):
        self.user = self.scope["user"]
        if not self.user.is_authenticated:
            self.close(code=4401)
            return
        try:
            self.peer = User.objects.get(pk=self.scope["url_route"]["kwargs"]["peer_id"])
        except User.DoesNotExist:
            self.close(code=4404)
            return
        if not can_staff_chat(self.user, self.peer):
            self.close(code=4403)
            return
        first_id, second_id = sorted((self.user.pk, self.peer.pk))
        self.group_name = f"staff_dm_{first_id}_{second_id}"
        async_to_sync(self.channel_layer.group_add)(self.group_name, self.channel_name)
        self.accept()

    def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            async_to_sync(self.channel_layer.group_discard)(self.group_name, self.channel_name)

    def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            self.send_json({"type": "error", "message": "Invalid message format."})
            return
        if not isinstance(data, dict):
            self.send_json({"type": "error", "message": "Invalid message format."})
            return
        kind = data.get("type")
        if kind == "message":
            body = str(data.get("body", "")).strip()
            if not body or len(body) > 4000:
                self.send_json({"type": "error", "message": "Messages must be 1–4000 characters."})
                return
            message = StaffMessage.objects.create(sender=self.user, recipient=self.peer, body=body)
            self.broadcast({
                "type": "message",
                "id": message.pk,
                "sender_id": self.user.pk,
                "sender": self.user.get_full_name() or self.user.username,
                "body": message.body,
                "created_at": message.created_at.isoformat(),
            })
        elif kind == "typing":
            self.broadcast({"type": "typing", "sender_id": self.user.pk, "active": bool(data.get("active"))})
        else:
            self.send_json({"type": "error", "message": "Unsupported event."})

    def broadcast(self, data):
        async_to_sync(self.channel_layer.group_send)(self.group_name, {"type": "relay", "data": data})

    def relay(self, event):
        self.send_json(event["data"])

    def send_json(self, data):
        self.send(text_data=json.dumps(data))

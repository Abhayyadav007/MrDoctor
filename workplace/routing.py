from django.urls import re_path

from .consumers import StaffChatConsumer

websocket_urlpatterns = [
    re_path(r"ws/management/messages/(?P<peer_id>\d+)/$", StaffChatConsumer.as_asgi()),
]

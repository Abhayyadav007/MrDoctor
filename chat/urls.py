from django.urls import path
from .views import ChatListView, ChatRoomView

urlpatterns = [
    path("", ChatListView.as_view(), name="chat_list"),
    path("<int:pk>/", ChatRoomView.as_view(), name="chat_room"),
]

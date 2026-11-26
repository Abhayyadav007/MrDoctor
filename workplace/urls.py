from django.urls import path

from .views import (
    EmployeeWorkspaceView,
    ManagerDashboardView,
    MeetingCancelView,
    MeetingCreateView,
    MyStaffWorkView,
    RemarkCreateView,
    StaffChatListView,
    StaffChatView,
)

urlpatterns = [
    path("", ManagerDashboardView.as_view(), name="workplace_dashboard"),
    path("my-work/", MyStaffWorkView.as_view(), name="my_staff_work"),
    path("staff/<int:employee_id>/", EmployeeWorkspaceView.as_view(), name="employee_workspace"),
    path("staff/<int:employee_id>/remarks/", RemarkCreateView.as_view(), name="employee_remark_create"),
    path("meetings/create/", MeetingCreateView.as_view(), name="staff_meeting_create"),
    path("meetings/<int:meeting_id>/cancel/", MeetingCancelView.as_view(), name="staff_meeting_cancel"),
    path("messages/", StaffChatListView.as_view(), name="staff_chat_list"),
    path("messages/<int:peer_id>/", StaffChatView.as_view(), name="staff_chat"),
]

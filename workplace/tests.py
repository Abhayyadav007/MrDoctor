from datetime import timedelta
from channels.db import database_sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from .models import EmployeeRemark, StaffMeeting, StaffMessage
from .routing import websocket_urlpatterns


class UserScopeMiddleware:
    def __init__(self, app, user):
        self.app = app
        self.user = user

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = self.user
        await self.app(scope, receive, send)


class ManagerWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="team-admin", email="team-admin@example.test", password="Strong-Test-Password-984!",
            role=User.Role.ADMIN,
        )
        self.doctor = User.objects.create_user(
            username="team-doctor", email="team-doctor@example.test", password="Strong-Test-Password-984!",
            role=User.Role.DOCTOR,
        )
        self.other_admin = User.objects.create_user(
            username="other-admin", email="other-admin@example.test", password="Strong-Test-Password-984!",
            role=User.Role.ADMIN,
        )
        self.other_doctor = User.objects.create_user(
            username="other-doctor", email="other-doctor@example.test", password="Strong-Test-Password-984!",
            role=User.Role.DOCTOR,
        )
        self.patient = User.objects.create_user(
            username="team-patient", email="team-patient@example.test", password="Strong-Test-Password-984!",
            role=User.Role.PATIENT,
        )

    def test_admin_can_manage_doctors_but_not_other_admins_or_patients(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("workplace_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("employee_workspace", args=[self.doctor.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("employee_workspace", args=[self.other_admin.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("employee_workspace", args=[self.patient.pk])).status_code, 403)
        self.assertEqual(
            self.client.post(reverse("employee_remark_create", args=[self.patient.pk]), {"body": "Not allowed"}).status_code,
            403,
        )

    def test_manager_remarks_are_visible_to_employee_and_attributed(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("employee_remark_create", args=[self.doctor.pk]), {
            "body": "Excellent patient follow-up.",
        })
        self.assertEqual(response.status_code, 302)
        remark = EmployeeRemark.objects.get(employee=self.doctor)
        self.assertEqual(remark.author, self.admin)

        self.client.force_login(self.doctor)
        response = self.client.get(reverse("my_staff_work"))
        self.assertContains(response, "Excellent patient follow-up.")
        self.assertContains(response, self.admin.get_full_name() or self.admin.username)

    def test_manager_can_schedule_urgent_meeting_and_cancel_it(self):
        self.client.force_login(self.admin)
        meeting_time = (timezone.now() + timedelta(days=2)).replace(second=0, microsecond=0)
        response = self.client.post(reverse("staff_meeting_create"), {
            "title": "Care team review",
            "details": "Review open cases.",
            "scheduled_at": meeting_time.strftime("%Y-%m-%dT%H:%M"),
            "tag": StaffMeeting.Tag.URGENT,
            "attendees": [self.doctor.pk],
        })
        self.assertEqual(response.status_code, 302)
        meeting = StaffMeeting.objects.get(title="Care team review")
        self.assertEqual(meeting.organizer, self.admin)
        self.assertEqual(meeting.tag, StaffMeeting.Tag.URGENT)
        self.assertSetEqual(set(meeting.attendees.values_list("pk", flat=True)), {self.admin.pk, self.doctor.pk})
        self.assertContains(self.client.get(reverse("workplace_dashboard")), "Urgent")

        self.client.force_login(self.doctor)
        self.assertContains(self.client.get(reverse("my_staff_work")), "Care team review")
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse("staff_meeting_cancel", args=[meeting.pk])).status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, StaffMeeting.Status.CANCELLED)

    def test_only_manager_can_schedule_meetings_and_attendees_are_scope_limited(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse("workplace_dashboard")).status_code, 403)
        self.assertEqual(self.client.post(reverse("staff_meeting_create")).status_code, 403)

        self.client.force_login(self.admin)
        meeting_time = (timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)
        response = self.client.post(reverse("staff_meeting_create"), {
            "title": "Invalid cross-team meeting",
            "scheduled_at": meeting_time.strftime("%Y-%m-%dT%H:%M"),
            "tag": StaffMeeting.Tag.STANDARD,
            "attendees": [self.other_admin.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StaffMeeting.objects.filter(title="Invalid cross-team meeting").exists())

    def test_superadmin_can_manage_administrators_and_doctors(self):
        superadmin = User.objects.create_superuser(
            username=settings.SUPERADMIN_USERNAME, email=settings.SUPERADMIN_EMAIL,
            password="Secure-Test-Password-984!",
        )
        self.client.force_login(superadmin)
        self.assertEqual(self.client.get(reverse("employee_workspace", args=[self.admin.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("employee_workspace", args=[self.doctor.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("workplace_dashboard")).status_code, 200)
        self.assertEqual(
            self.client.post(reverse("employee_remark_create", args=[self.admin.pk]), {
                "body": "Great operational leadership.",
            }).status_code,
            302,
        )
        self.assertTrue(EmployeeRemark.objects.filter(employee=self.admin, author=superadmin).exists())
        self.assertEqual(
            self.client.get(reverse("staff_chat", args=[self.other_admin.pk])).status_code,
            200,
        )


class StaffChatConsumerTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.admin = User.objects.create_user(username="socket-manager", password="Strong-Test-Password-984!",
                                              role=User.Role.ADMIN)
        self.doctor = User.objects.create_user(username="socket-employee", password="Strong-Test-Password-984!",
                                               role=User.Role.DOCTOR)
        self.patient = User.objects.create_user(username="socket-patient", password="Strong-Test-Password-984!",
                                                role=User.Role.PATIENT)
        self.peer_doctor = User.objects.create_user(username="socket-other-doctor",
                                                    password="Strong-Test-Password-984!", role=User.Role.DOCTOR)

    async def test_manager_and_employee_can_chat_and_message_is_persisted(self):
        path = f"/ws/management/messages/{self.doctor.pk}/"
        manager = WebsocketCommunicator(
            UserScopeMiddleware(URLRouter(websocket_urlpatterns), self.admin), path,
        )
        employee = WebsocketCommunicator(
            UserScopeMiddleware(URLRouter(websocket_urlpatterns), self.doctor),
            f"/ws/management/messages/{self.admin.pk}/",
        )
        manager_connected, _ = await manager.connect()
        employee_connected, _ = await employee.connect()
        self.assertTrue(manager_connected)
        self.assertTrue(employee_connected)

        await manager.send_json_to({"type": "message", "body": "Please review the new schedule."})
        manager_event = await manager.receive_json_from()
        employee_event = await employee.receive_json_from()
        self.assertEqual(manager_event["body"], "Please review the new schedule.")
        self.assertEqual(employee_event["sender_id"], self.admin.pk)
        self.assertTrue(await database_sync_to_async(
            StaffMessage.objects.filter(sender=self.admin, recipient=self.doctor).exists,
        )())
        await manager.disconnect()
        await employee.disconnect()

    async def test_patient_and_unrelated_employee_cannot_connect(self):
        path = f"/ws/management/messages/{self.doctor.pk}/"
        patient = WebsocketCommunicator(UserScopeMiddleware(URLRouter(websocket_urlpatterns), self.patient), path)
        connected, _ = await patient.connect()
        self.assertFalse(connected)

        unrelated = WebsocketCommunicator(
            UserScopeMiddleware(URLRouter(websocket_urlpatterns), self.peer_doctor), path,
        )
        connected, _ = await unrelated.connect()
        self.assertFalse(connected)

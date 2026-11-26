from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from allauth.account.models import EmailAddress
from accounts.models import PatientProfile
from accounts.models import User
from calls.models import CallLog
from cases.models import Case
from chat.models import ChatMessage
from chat.routing import websocket_urlpatterns


class CasePermissionsTests(TestCase):
    def setUp(self):
        self.patient = User.objects.create_user(username="patient-a", password="test-pass-123", role=User.Role.PATIENT)
        self.other = User.objects.create_user(username="patient-b", password="test-pass-123", role=User.Role.PATIENT)
        self.doctor = User.objects.create_user(username="doctor-a", password="test-pass-123", role=User.Role.DOCTOR)
        self.case = Case.objects.create(patient=self.other, doctor=self.doctor, title="Private case", description="Private")

    def test_owner_can_open_case_and_chat(self):
        owned_case = Case.objects.create(patient=self.patient, doctor=self.doctor,
                                         title="My case", description="Visible")
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse("case_detail", args=[owned_case.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("chat_room", args=[owned_case.pk])).status_code, 200)

    def test_patient_cannot_open_another_patients_case(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse("case_detail", args=[self.case.pk]))
        self.assertEqual(response.status_code, 403)

    def test_patient_cannot_open_another_patients_chat(self):
        self.client.force_login(self.patient)
        response = self.client.get(reverse("chat_room", args=[self.case.pk]))
        self.assertEqual(response.status_code, 403)


class UserScopeMiddleware:
    def __init__(self, app, user):
        self.app, self.user = app, user

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"] = self.user
        await self.app(scope, receive, send)


class AllauthTests(TestCase):
    def test_allauth_login_and_signup_pages_render(self):
        self.assertEqual(self.client.get(reverse("account_login")).status_code, 200)
        self.assertEqual(self.client.get(reverse("account_signup")).status_code, 200)

    def test_email_signup_creates_patient_and_sends_verification(self):
        response = self.client.post(reverse("account_signup"), {
            "username": "email-patient",
            "email": "email-patient@example.test",
            "password1": "Strong-Test-Password-984!",
            "password2": "Strong-Test-Password-984!",
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="email-patient")
        self.assertEqual(user.role, User.Role.PATIENT)
        self.assertTrue(PatientProfile.objects.filter(user=user).exists())
        self.assertTrue(EmailAddress.objects.filter(user=user, email=user.email, verified=False).exists())

    def test_superuser_is_admin_and_email_verified_for_allauth(self):
        admin = User.objects.create_superuser(username="allauth-admin", email="admin@example.test",
                                              password="Strong-Test-Password-984!")
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(EmailAddress.objects.filter(user=admin, verified=True).exists())


class ChatConsumerPermissionTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.patient = User.objects.create_user(username="socket-patient", password="test-pass-123",
                                                role=User.Role.PATIENT)
        self.other = User.objects.create_user(username="socket-other", password="test-pass-123",
                                              role=User.Role.PATIENT)
        self.doctor = User.objects.create_user(username="socket-doctor", password="test-pass-123",
                                               role=User.Role.DOCTOR)
        self.case = Case.objects.create(patient=self.patient, doctor=self.doctor,
                                        title="Socket case", description="Test")
        self.other_case = Case.objects.create(patient=self.other, doctor=self.doctor,
                                              title="Other case", description="Test")

    async def test_assigned_patient_can_connect_and_other_patient_is_rejected(self):
        path = f"/ws/cases/{self.case.pk}/"
        allowed = WebsocketCommunicator(UserScopeMiddleware(URLRouter(websocket_urlpatterns), self.patient), path)
        connected, _ = await allowed.connect()
        self.assertTrue(connected)
        presence = await allowed.receive_json_from()
        self.assertEqual(presence["type"], "presence")
        await allowed.send_json_to({"type": "message", "text": "Test message"})
        delivered = await allowed.receive_json_from()
        if delivered["type"] == "presence":
            delivered = await allowed.receive_json_from()
        self.assertEqual(delivered["type"], "chat_message")
        self.assertEqual(delivered["text"], "Test message")
        self.assertTrue(await database_sync_to_async(ChatMessage.objects.filter(case=self.case, text="Test message").exists)())
        await allowed.disconnect()

        forbidden = WebsocketCommunicator(
            UserScopeMiddleware(URLRouter(websocket_urlpatterns), self.other), path)
        connected, _ = await forbidden.connect()
        self.assertFalse(connected)

    async def test_chat_and_call_signaling_are_relayed_and_call_is_logged(self):
        async def receive_type(communicator, expected_type):
            for _ in range(10):
                event = await communicator.receive_json_from(timeout=2)
                if event["type"] == expected_type:
                    return event
            self.fail(f"Did not receive WebSocket event {expected_type}")

        path = f"/ws/cases/{self.case.pk}/"
        patient = WebsocketCommunicator(UserScopeMiddleware(URLRouter(websocket_urlpatterns), self.patient), path)
        doctor = WebsocketCommunicator(UserScopeMiddleware(URLRouter(websocket_urlpatterns), self.doctor), path)
        patient_connected, _ = await patient.connect()
        doctor_connected, _ = await doctor.connect()
        self.assertTrue(patient_connected)
        self.assertTrue(doctor_connected)

        await patient.send_json_to({"type": "call_start", "audio_only": True})
        invite = await receive_type(patient, "call_invite")
        doctor_invite = await receive_type(doctor, "call_invite")
        self.assertEqual(doctor_invite["call_id"], invite["call_id"])
        self.assertTrue(invite["audio_only"])
        self.assertTrue(await database_sync_to_async(
            CallLog.objects.filter(pk=invite["call_id"], status=CallLog.Status.RINGING).exists)())

        await doctor.send_json_to({"type": "call_accept", "call_id": invite["call_id"]})
        await receive_type(patient, "call_accept")
        await receive_type(doctor, "call_accept")

        await patient.send_json_to({"type": "offer", "payload": {"type": "offer", "sdp": "sample-sdp"}})
        patient_offer = await receive_type(patient, "offer")
        doctor_offer = await receive_type(doctor, "offer")
        self.assertEqual(doctor_offer["payload"]["sdp"], "sample-sdp")

        await patient.disconnect()
        await doctor.disconnect()

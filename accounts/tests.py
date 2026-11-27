from datetime import date, timedelta
from io import StringIO
from unittest.mock import patch

from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from channels.db import database_sync_to_async
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase, override_settings
from django.conf import settings
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.account.models import EmailAddress
from allauth.account.utils import has_verified_email
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialLogin
from allauth.socialaccount.providers.google.provider import GoogleProvider
from accounts.adapters import PatientSocialAccountAdapter
from accounts.models import PatientProfile
from accounts.models import User
from calls.models import CallLog
from cases.models import Case
from chat.models import ChatMessage
from chat.routing import websocket_urlpatterns
from payroll.models import PayrollAdjustment, PayrollRecord
from workplace.models import StaffMeeting


class AccountRemovalTests(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username=settings.SUPERADMIN_USERNAME,
            email=settings.SUPERADMIN_EMAIL,
            password="Secure-Test-Password-984!",
        )
        self.doctor = User.objects.create_user(
            username="removable-doctor",
            password="Secure-Test-Password-984!",
            role=User.Role.DOCTOR,
        )

    def test_only_superadmin_can_remove_accounts(self):
        manager = User.objects.create_user(
            username="regular-manager",
            password="Secure-Test-Password-984!",
            role=User.Role.ADMIN,
        )
        self.client.force_login(manager)
        response = self.client.post(reverse("user_remove", args=[self.doctor.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.doctor.pk).exists())

    def test_superadmin_removal_cleans_protected_account_relations(self):
        payroll = PayrollRecord.objects.create(
            doctor=self.doctor,
            period=date(2026, 1, 1),
            base_salary="1000.00",
        )
        adjustment = PayrollAdjustment.objects.create(
            payroll=payroll,
            amount="100.00",
            reason="Test adjustment",
            actor=self.doctor,
        )
        meeting = StaffMeeting.objects.create(
            organizer=self.doctor,
            title="Test meeting",
            scheduled_at=timezone.now() + timedelta(days=1),
        )
        self.client.force_login(self.superadmin)

        response = self.client.post(reverse("user_remove", args=[self.doctor.pk]))

        self.assertRedirects(response, reverse("workplace_dashboard"))
        self.assertFalse(User.objects.filter(pk=self.doctor.pk).exists())
        self.assertFalse(PayrollRecord.objects.filter(pk=payroll.pk).exists())
        self.assertFalse(PayrollAdjustment.objects.filter(pk=adjustment.pk).exists())
        self.assertFalse(StaffMeeting.objects.filter(pk=meeting.pk).exists())

    def test_superadmin_cannot_remove_themselves(self):
        self.client.force_login(self.superadmin)
        response = self.client.post(reverse("user_remove", args=[self.superadmin.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(User.objects.filter(pk=self.superadmin.pk, is_superuser=True).exists())

    def test_superadmin_can_remove_an_admin(self):
        admin = User.objects.create_user(
            username="removable-admin",
            password="Secure-Test-Password-984!",
            role=User.Role.ADMIN,
        )
        self.client.force_login(self.superadmin)

        response = self.client.post(reverse("user_remove", args=[admin.pk]))

        self.assertRedirects(response, reverse("workplace_dashboard"))
        self.assertFalse(User.objects.filter(pk=admin.pk).exists())


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

    @override_settings(SOCIALACCOUNT_PROVIDERS={
        "google": {"APPS": [{"client_id": "test-client-id", "secret": "test-secret", "key": ""}]}
    })
    def test_login_google_option_and_remember_checkbox_render_correctly(self):
        response = self.client.get(reverse("account_login"))
        self.assertContains(response, 'id="google-login-option"')
        self.assertNotContains(response, 'id="google-login-option" hidden')
        self.assertContains(response, 'class="form-check-input"')

        response = self.client.post(reverse("account_login"), {
            "login": "not-a-user",
            "password": "invalid",
            "role": User.Role.ADMIN,
        })
        self.assertContains(response, 'id="google-login-option" hidden')

    def test_login_requires_the_selected_account_role_to_match(self):
        user = User.objects.create_user(username="role-doctor", email="role-doctor@example.test",
                                        password="Strong-Test-Password-984!", role=User.Role.DOCTOR)
        correct_role = self.client.post(reverse("account_login"), {
            "login": user.username, "password": "Strong-Test-Password-984!", "role": User.Role.DOCTOR,
        })
        self.assertEqual(correct_role.status_code, 302)
        self.client.logout()
        wrong_role = self.client.post(reverse("account_login"), {
            "login": user.username, "password": "Strong-Test-Password-984!", "role": User.Role.PATIENT,
        })
        self.assertEqual(wrong_role.status_code, 200)
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_manager_created_staff_emails_are_verified_without_patient_verification(self):
        doctor = User.objects.create_user(
            username="verified-doctor",
            email="verified-doctor@example.test",
            password="Secure-Test-Password-984!",
            role=User.Role.DOCTOR,
        )
        admin = User.objects.create_user(
            username="verified-admin",
            email="verified-admin@example.test",
            password="Secure-Test-Password-984!",
            role=User.Role.ADMIN,
        )
        patient = User.objects.create_user(
            username="unverified-patient",
            email="unverified-patient@example.test",
            password="Secure-Test-Password-984!",
            role=User.Role.PATIENT,
        )

        for staff_user in (doctor, admin):
            self.assertTrue(EmailAddress.objects.get(user=staff_user, email=staff_user.email).verified)
        self.assertFalse(EmailAddress.objects.filter(user=patient, verified=True).exists())

    def test_superadmin_staff_list_shows_doctor_and_admin_usernames(self):
        doctor = User.objects.create_user(
            username="listed-doctor",
            email="listed-doctor@example.test",
            password="Secure-Test-Password-984!",
            role=User.Role.DOCTOR,
        )
        admin = User.objects.create_user(
            username="listed-admin",
            email="listed-admin@example.test",
            password="Secure-Test-Password-984!",
            role=User.Role.ADMIN,
        )
        superadmin = User.objects.create_superuser(
            username=settings.SUPERADMIN_USERNAME,
            email=settings.SUPERADMIN_EMAIL,
            password="Secure-Test-Password-984!",
        )
        self.client.force_login(superadmin)

        response = self.client.get(reverse("workplace_dashboard"))

        self.assertContains(response, f"Username: <code>{doctor.username}</code>")
        self.assertContains(response, f"Username: <code>{admin.username}</code>")

    def test_staff_use_usernames_and_patients_use_emails_for_password_login(self):
        doctor = User.objects.create_user(
            username="username-doctor", email="username-doctor@example.test",
            password="Strong-Test-Password-984!", role=User.Role.DOCTOR,
        )
        patient = User.objects.create_user(
            username="email-patient-login", email="email-patient-login@example.test",
            password="Strong-Test-Password-984!", role=User.Role.PATIENT,
        )
        EmailAddress.objects.create(user=patient, email=patient.email, primary=True, verified=True)

        response = self.client.post(reverse("account_login"), {
            "login": doctor.email, "password": "Strong-Test-Password-984!", "role": User.Role.DOCTOR,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get("_auth_user_id"))
        response = self.client.post(reverse("account_login"), {
            "login": doctor.username, "password": "Strong-Test-Password-984!", "role": User.Role.DOCTOR,
        })
        self.assertEqual(response.status_code, 302)
        self.client.logout()

        response = self.client.post(reverse("account_login"), {
            "login": patient.username, "password": "Strong-Test-Password-984!", "role": User.Role.PATIENT,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get("_auth_user_id"))
        response = self.client.post(reverse("account_login"), {
            "login": patient.email, "password": "Strong-Test-Password-984!", "role": User.Role.PATIENT,
        })
        self.assertEqual(response.status_code, 302)

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

    def test_patient_signup_cannot_duplicate_a_preprovisioned_staff_email(self):
        doctor = User.objects.create_user(
            username="preprovisioned-doctor", email="staff-google@example.test",
            password="Secure-Test-Password-984!", role=User.Role.DOCTOR,
        )
        response = self.client.post(reverse("account_signup"), {
            "username": "duplicate-staff-email",
            "email": doctor.email,
            "password1": "Strong-Test-Password-984!",
            "password2": "Strong-Test-Password-984!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="duplicate-staff-email").exists())
        self.assertContains(response, "already associated with an account")

    def test_only_configured_superadmin_email_is_allowed_and_verified(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(username="wrong-admin", email="admin@example.test",
                                          password="Strong-Test-Password-984!")
        with self.assertRaises(ValueError):
            User.objects.create_superuser(username="wrong-username", email=settings.SUPERADMIN_EMAIL,
                                          password="Strong-Test-Password-984!")
        admin = User.objects.create_superuser(username=settings.SUPERADMIN_USERNAME,
                                              email=settings.SUPERADMIN_EMAIL,
                                              password="Strong-Test-Password-984!")
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(EmailAddress.objects.filter(user=admin, email=settings.SUPERADMIN_EMAIL,
                                                    verified=True).exists())

    def test_superadmin_password_login_uses_configured_username(self):
        admin = User.objects.create_superuser(
            username=settings.SUPERADMIN_USERNAME,
            email=settings.SUPERADMIN_EMAIL,
            password="Secure-Test-Password-984!",
        )
        response = self.client.post(reverse("account_login"), {
            "login": admin.email,
            "password": "Secure-Test-Password-984!",
            "role": User.Role.ADMIN,
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.client.session.get("_auth_user_id"))
        response = self.client.post(reverse("account_login"), {
            "login": settings.SUPERADMIN_USERNAME,
            "password": "Secure-Test-Password-984!",
            "role": User.Role.ADMIN,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("_auth_user_id"), str(admin.pk))

    def test_create_superadmin_command_prompts_and_verifies_configured_account(self):
        password = "Secure-Local-Test-Password-984!"
        with patch("accounts.management.commands.create_superadmin.getpass",
                   side_effect=[password, password]):
            call_command("create_superadmin", stdout=StringIO())
        admin = User.objects.get(email=settings.SUPERADMIN_EMAIL)
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.username, settings.SUPERADMIN_USERNAME)
        self.assertTrue(admin.check_password(password))
        self.assertTrue(EmailAddress.objects.get(user=admin).verified)

    def test_google_signin_rejects_existing_staff_accounts(self):
        doctor = User.objects.create_user(
            username="google-doctor", email="google-doctor@example.test",
            password="Secure-Test-Password-984!", role=User.Role.DOCTOR,
        )
        admin = User.objects.create_user(
            username="google-admin", email="google-admin@example.test",
            password="Secure-Test-Password-984!", role=User.Role.ADMIN,
        )
        superadmin = User.objects.create_superuser(
            username=settings.SUPERADMIN_USERNAME, email=settings.SUPERADMIN_EMAIL,
            password="Secure-Test-Password-984!",
        )

        for existing_user in (doctor, admin, superadmin):
            expected_role = existing_user.role
            email_was_verified = has_verified_email(existing_user, existing_user.email)
            request = RequestFactory().get("/")
            provider = GoogleProvider(
                request,
                SocialApp(provider="google", name="Google", client_id="test-id", secret="test-secret"),
            )
            login = SocialLogin(
                user=User(username="temporary-google-user"),
                account=SocialAccount(provider="google", uid=f"google-{existing_user.pk}"),
                provider=provider,
                email_addresses=[EmailAddress(email=existing_user.email, verified=True)],
            )
            login.lookup()
            self.assertEqual(login.user.pk, existing_user.pk)
            self.assertTrue(login._did_authenticate_by_email)
            with self.assertRaises(ImmediateHttpResponse) as raised:
                PatientSocialAccountAdapter().pre_social_login(request, login)
            self.assertEqual(raised.exception.response.status_code, 403)
            self.assertEqual(existing_user.role, expected_role)
            self.assertEqual(has_verified_email(existing_user, existing_user.email), email_was_verified)
            self.assertTrue(existing_user.has_usable_password())
            self.assertFalse(SocialAccount.objects.filter(user=existing_user, provider="google").exists())

    def test_staff_cannot_connect_google_to_an_account(self):
        doctor = User.objects.create_user(
            username="connect-google-doctor", email="connect-google-doctor@example.test",
            password="Secure-Test-Password-984!", role=User.Role.DOCTOR,
        )
        request = RequestFactory().get("/")
        request.user = doctor
        login = SocialLogin(
            user=User(username="temporary-google-user"),
            account=SocialAccount(provider="google", uid="new-google-uid"),
        )
        with self.assertRaises(ImmediateHttpResponse) as raised:
            PatientSocialAccountAdapter().pre_social_login(request, login)
        self.assertEqual(raised.exception.response.status_code, 403)
        self.assertFalse(SocialAccount.objects.filter(user=doctor, provider="google").exists())

    def test_unverified_google_email_cannot_authenticate_existing_staff(self):
        doctor = User.objects.create_user(
            username="unverified-google-doctor", email="unverified-doctor@example.test",
            password="Secure-Test-Password-984!", role=User.Role.DOCTOR,
        )
        provider = GoogleProvider(
            RequestFactory().get("/"),
            SocialApp(provider="google", name="Google", client_id="test-id", secret="test-secret"),
        )
        login = SocialLogin(
            user=User(username="temporary-google-user"),
            account=SocialAccount(provider="google", uid="unverified-google-uid"),
            provider=provider,
            email_addresses=[EmailAddress(email=doctor.email, verified=False)],
        )
        login.lookup()
        self.assertIsNone(login._did_authenticate_by_email)
        self.assertNotEqual(login.user.pk, doctor.pk)
        PatientSocialAccountAdapter().pre_social_login(RequestFactory().get("/"), login)
        self.assertFalse(SocialAccount.objects.filter(user=doctor, provider="google").exists())

    def test_google_signup_without_a_precreated_account_remains_a_patient(self):
        request = RequestFactory().get("/")
        login = SocialLogin(
            user=User(username="new-google-patient"),
            account=SocialAccount(provider="google", uid="new-google-patient-uid"),
        )
        user = PatientSocialAccountAdapter().populate_user(request, login, {
            "email": "new-google-patient@example.test",
            "first_name": "New",
            "last_name": "Patient",
        })
        self.assertEqual(user.role, User.Role.PATIENT)

    def test_google_signin_allows_existing_patient_accounts(self):
        patient = User.objects.create_user(
            username="google-patient", email="google-patient@example.test",
            password="Secure-Test-Password-984!", role=User.Role.PATIENT,
        )
        request = RequestFactory().get("/")
        provider = GoogleProvider(
            request,
            SocialApp(provider="google", name="Google", client_id="test-id", secret="test-secret"),
        )
        login = SocialLogin(
            user=User(username="temporary-google-patient"),
            account=SocialAccount(provider="google", uid="google-patient-uid"),
            provider=provider,
            email_addresses=[EmailAddress(email=patient.email, verified=True)],
        )
        login.lookup()
        self.assertEqual(login.user.pk, patient.pk)
        PatientSocialAccountAdapter().pre_social_login(request, login)
        self.assertTrue(has_verified_email(patient, patient.email))


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

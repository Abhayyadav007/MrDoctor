from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from cases.models import Case
from .models import DoctorCompensation, DoctorRating, PayrollAdjustment, PayrollAudit, PayrollRecord, RatingBonusTier


class PayrollWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="pay-admin", password="Strong-Test-Password-984!",
                                              role=User.Role.ADMIN)
        self.patient = User.objects.create_user(username="pay-patient", password="Strong-Test-Password-984!",
                                                role=User.Role.PATIENT)
        self.other_patient = User.objects.create_user(username="pay-other", password="Strong-Test-Password-984!",
                                                      role=User.Role.PATIENT)
        self.doctor = User.objects.create_user(username="pay-doctor", password="Strong-Test-Password-984!",
                                               role=User.Role.DOCTOR)
        self.case = Case.objects.create(
            patient=self.patient, doctor=self.doctor, title="Completed case", description="Case details",
            status=Case.Status.RECOVERED,
        )

    def test_only_admin_can_manage_payroll(self):
        self.client.force_login(self.patient)
        self.assertEqual(self.client.get(reverse("payroll_dashboard")).status_code, 403)
        self.client.force_login(self.doctor)
        self.assertEqual(self.client.get(reverse("payroll_dashboard")).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("payroll_dashboard")).status_code, 200)

    def test_rating_is_limited_to_own_completed_case(self):
        self.client.force_login(self.other_patient)
        self.assertEqual(
            self.client.post(reverse("doctor_rate_case", args=[self.case.pk]), {"score": 5}).status_code,
            403,
        )
        self.client.force_login(self.patient)
        response = self.client.post(reverse("doctor_rate_case", args=[self.case.pk]), {
            "score": 5, "feedback": "Helpful care",
        })
        self.assertEqual(response.status_code, 302)
        rating = DoctorRating.objects.get(case=self.case)
        self.assertEqual((rating.patient, rating.doctor, rating.score),
                         (self.patient, self.doctor, 5))
        self.assertEqual(
            self.client.post(reverse("doctor_rate_case", args=[self.case.pk]), {"score": 4}).status_code,
            302,
        )
        self.assertEqual(DoctorRating.objects.filter(case=self.case).count(), 1)

    def test_admin_can_generate_approve_adjust_and_mark_payroll_paid(self):
        today = date.today()
        period = date(today.year, today.month, 1)
        DoctorCompensation.objects.create(doctor=self.doctor, base_monthly_salary=Decimal("50000.00"))
        RatingBonusTier.objects.create(stars=5, monthly_bonus=Decimal("5000.00"))
        DoctorRating.objects.create(case=self.case, patient=self.patient, doctor=self.doctor, score=5)

        self.client.force_login(self.admin)
        response = self.client.post(reverse("payroll_generate"), {"month": period.strftime("%Y-%m")})
        self.assertEqual(response.status_code, 302)
        payroll = PayrollRecord.objects.get(doctor=self.doctor, period=period)
        self.assertEqual(payroll.total_due, Decimal("55000.00"))
        self.assertEqual(payroll.average_rating, Decimal("5.00"))
        self.assertEqual(payroll.rating_count, 1)

        response = self.client.post(reverse("payroll_adjust", args=[payroll.pk]), {
            "amount": "-250.00", "reason": "Approved correction",
        })
        self.assertEqual(response.status_code, 302)
        payroll.refresh_from_db()
        self.assertEqual(payroll.total_due, Decimal("54750.00"))
        self.assertEqual(PayrollAdjustment.objects.filter(payroll=payroll).count(), 1)

        response = self.client.post(reverse("payroll_status", args=[payroll.pk]), {"status": "APPROVED"})
        self.assertEqual(response.status_code, 302)
        payroll.refresh_from_db()
        self.assertEqual(payroll.status, PayrollRecord.Status.APPROVED)
        response = self.client.post(reverse("payroll_status", args=[payroll.pk]), {"status": "PAID"})
        self.assertEqual(response.status_code, 302)
        payroll.refresh_from_db()
        self.assertEqual(payroll.status, PayrollRecord.Status.PAID)
        self.assertIsNotNone(payroll.paid_at)
        self.assertGreaterEqual(PayrollAudit.objects.count(), 3)

    def test_payroll_status_cannot_skip_approval(self):
        payroll = PayrollRecord.objects.create(
            doctor=self.doctor, period=date(2025, 1, 1), base_salary=Decimal("1.00"),
        )
        self.client.force_login(self.admin)
        response = self.client.post(reverse("payroll_status", args=[payroll.pk]), {"status": "PAID"})
        self.assertEqual(response.status_code, 302)
        payroll.refresh_from_db()
        self.assertEqual(payroll.status, PayrollRecord.Status.DRAFT)

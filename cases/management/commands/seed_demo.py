from datetime import date, time, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from allauth.account.models import EmailAddress
from accounts.models import DoctorProfile, PatientProfile, User
from appointments.models import Appointment
from cases.models import Case, Visit


class Command(BaseCommand):
    help = "Create a local demo clinic with one admin, two doctors, three patients, and sample cases."

    def handle(self, *args, **options):
        admin, _ = User.objects.get_or_create(username="demo-admin", defaults={
            "email": "admin@example.test", "first_name": "Demo", "last_name": "Admin",
            "role": User.Role.ADMIN, "is_staff": True, "is_superuser": True,
        })
        admin.role, admin.is_staff, admin.is_superuser = User.Role.ADMIN, True, True
        admin.set_password("DemoAdmin123!")
        admin.save()
        EmailAddress.objects.update_or_create(user=admin, email=admin.email,
                                              defaults={"primary": True, "verified": True})
        doctors = []
        for username, first, last, specialty in [
            ("demo-doctor1", "Asha", "Shah", "Family Medicine"),
            ("demo-doctor2", "Noah", "Kim", "Cardiology"),
        ]:
            doctor, _ = User.objects.get_or_create(username=username, defaults={
                "email": f"{username}@example.test", "first_name": first, "last_name": last,
                "role": User.Role.DOCTOR,
            })
            doctor.role, doctor.first_name, doctor.last_name = User.Role.DOCTOR, first, last
            doctor.set_password("DemoDoctor123!")
            doctor.save()
            EmailAddress.objects.update_or_create(user=doctor, email=doctor.email,
                                                  defaults={"primary": True, "verified": True})
            DoctorProfile.objects.update_or_create(user=doctor, defaults={
                "specialization": specialty, "experience": 8, "availability": "Mon-Fri, 09:00-17:00",
            })
            doctors.append(doctor)
        patients = []
        for index, (first, last) in enumerate([("Maya", "Patel"), ("Ethan", "Brooks"), ("Lina", "Garcia")], 1):
            username = f"demo-patient{index}"
            patient, _ = User.objects.get_or_create(username=username, defaults={
                "email": f"{username}@example.test", "first_name": first, "last_name": last,
                "role": User.Role.PATIENT,
            })
            patient.role, patient.first_name, patient.last_name = User.Role.PATIENT, first, last
            patient.set_password("DemoPatient123!")
            patient.save()
            EmailAddress.objects.update_or_create(user=patient, email=patient.email,
                                                  defaults={"primary": True, "verified": True})
            PatientProfile.objects.get_or_create(user=patient, defaults={
                "dob": date(1990, 1, index), "blood_group": "O+",
            })
            patients.append(patient)
        samples = [
            (patients[0], doctors[0], "Seasonal allergies", "Recurring congestion and itchy eyes.", "Under Treatment", "Normal"),
            (patients[1], doctors[1], "Blood pressure review", "Follow-up for elevated readings.", "Open", "High"),
            (patients[2], doctors[0], "Annual wellness visit", "Routine preventive care and screening.", "Recovered", "Low"),
        ]
        for patient, doctor, title, description, status, priority in samples:
            case, created = Case.objects.get_or_create(patient=patient, title=title, defaults={
                "doctor": doctor, "description": description, "status": status, "priority": priority,
            })
            if created:
                Visit.objects.create(case=case, doctor=doctor, notes="Initial review completed.",
                                     diagnosis=title, prescription="Continue care plan as discussed.")
        appointment_date = timezone.localdate() + timedelta(days=2)
        Appointment.objects.get_or_create(patient=patients[0], doctor=doctors[0],
                                          date=appointment_date, time=time(10, 0),
                                          defaults={"reason": "Follow-up"})
        self.stdout.write(self.style.SUCCESS(
            "Demo data ready. Login: demo-admin / DemoAdmin123!, demo-doctor1 or demo-doctor2 / "
            "DemoDoctor123!, demo-patient1..3 / DemoPatient123!"))

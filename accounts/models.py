from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.conf import settings
from django.db import models
from django.db.models import Q


class UserManager(DjangoUserManager):
    use_in_migrations = True

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        expected_email = settings.SUPERADMIN_EMAIL.lower()
        if not email or email.lower() != expected_email:
            raise ValueError(f"The only superuser must use {settings.SUPERADMIN_EMAIL}.")
        if self.get_queryset().filter(is_superuser=True).exists():
            raise ValueError("A superuser already exists.")
        extra_fields.setdefault("role", "ADMIN")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        DOCTOR = "DOCTOR", "Doctor"
        PATIENT = "PATIENT", "Patient"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PATIENT)
    phone = models.CharField(max_length=30, blank=True)
    profile_photo = models.ImageField(upload_to="profiles/", blank=True, null=True)
    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=("is_superuser",),
                condition=Q(is_superuser=True),
                name="accounts_only_one_superuser",
            )
        ]

    def clean(self):
        super().clean()
        if self.is_superuser and self.email.lower() != settings.SUPERADMIN_EMAIL.lower():
            from django.core.exceptions import ValidationError
            raise ValidationError({"email": f"The only superuser email is {settings.SUPERADMIN_EMAIL}."})

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


class DoctorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="doctor_profile")
    specialization = models.CharField(max_length=120)
    experience = models.PositiveSmallIntegerField(default=0)
    availability = models.TextField(blank=True, help_text="Working days and hours")

    def __str__(self):
        return f"Dr. {self.user.get_full_name() or self.user.username}"


class PatientProfile(models.Model):
    class Gender(models.TextChoices):
        FEMALE = "F", "Female"
        MALE = "M", "Male"
        OTHER = "O", "Other"
        UNSPECIFIED = "U", "Prefer not to say"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="patient_profile")
    dob = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    blood_group = models.CharField(max_length=5, blank=True)
    address = models.TextField(blank=True)
    emergency_contact = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

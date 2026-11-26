from django.conf import settings
from django.db import models


class Case(models.Model):
    class Status(models.TextChoices):
        OPEN = "Open", "Open"
        TREATMENT = "Under Treatment", "Under Treatment"
        RECOVERED = "Recovered", "Recovered"
        REFERRED = "Referred", "Referred"
        CLOSED = "Closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "Low", "Low"
        NORMAL = "Normal", "Normal"
        HIGH = "High", "High"
        URGENT = "Urgent", "Urgent"

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cases")
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="assigned_cases", limit_choices_to={"role": "DOCTOR"})
    title = models.CharField(max_length=180)
    description = models.TextField()
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.OPEN)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self):
        return f"#{self.pk} {self.title}"


class Visit(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="visits")
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="visits")
    notes = models.TextField(blank=True)
    diagnosis = models.TextField(blank=True)
    prescription = models.TextField(blank=True)
    next_visit = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Attachment(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    file = models.FileField(upload_to="case-reports/%Y/%m/")
    description = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)


class CaseAudit(models.Model):
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name="audit_entries")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=120)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

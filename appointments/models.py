from django.conf import settings
from django.db import models


class Appointment(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "Requested", "Requested"
        APPROVED = "Approved", "Approved"
        REJECTED = "Rejected", "Rejected"
        COMPLETED = "Completed", "Completed"

    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="appointments")
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="doctor_appointments")
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.REQUESTED)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "time"]

    def __str__(self):
        return f"{self.date} {self.time}: {self.patient}"

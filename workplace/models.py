from django.conf import settings
from django.db import models


class EmployeeRemark(models.Model):
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="manager_remarks",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="written_employee_remarks",
    )
    body = models.CharField(max_length=2400)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Remark for {self.employee} by {self.author or 'former manager'}"


class StaffMessage(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_staff_messages",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_staff_messages",
    )
    body = models.CharField(max_length=4000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=("sender", "recipient", "created_at"))]

    def __str__(self):
        return f"Staff message from {self.sender} to {self.recipient}"


class StaffMeeting(models.Model):
    class Tag(models.TextChoices):
        STANDARD = "STANDARD", "Standard"
        IMPORTANT = "IMPORTANT", "Important"
        URGENT = "URGENT", "Urgent"

    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Scheduled"
        CANCELLED = "CANCELLED", "Cancelled"

    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="organized_staff_meetings",
    )
    attendees = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="staff_meetings",
    )
    title = models.CharField(max_length=180)
    details = models.TextField(blank=True, max_length=3000)
    scheduled_at = models.DateTimeField()
    tag = models.CharField(max_length=12, choices=Tag.choices, default=Tag.STANDARD)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SCHEDULED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.title} · {self.scheduled_at:%Y-%m-%d %H:%M}"

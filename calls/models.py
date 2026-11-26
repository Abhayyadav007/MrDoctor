from django.conf import settings
from django.db import models


class CallLog(models.Model):
    class Status(models.TextChoices):
        RINGING = "Ringing", "Ringing"
        COMPLETED = "Completed", "Completed"
        MISSED = "Missed", "Missed"
        REJECTED = "Rejected", "Rejected"

    case = models.ForeignKey("cases.Case", on_delete=models.CASCADE, related_name="calls")
    caller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="calls_made")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="calls_received")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RINGING)
    audio_only = models.BooleanField(default=False)

    class Meta:
        ordering = ["-started_at"]

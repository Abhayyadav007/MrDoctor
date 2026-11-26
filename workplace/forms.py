from django import forms
from django.utils import timezone

from accounts.models import User
from .models import EmployeeRemark, StaffMeeting


class EmployeeRemarkForm(forms.ModelForm):
    class Meta:
        model = EmployeeRemark
        fields = ("body",)
        widgets = {
            "body": forms.Textarea(attrs={
                "class": "form-control", "rows": 3, "maxlength": 2400,
                "placeholder": "Write clear, constructive feedback…",
            }),
        }


class StaffMessageForm(forms.Form):
    body = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={
            "class": "form-control", "rows": 2, "maxlength": 4000,
            "placeholder": "Write a message…",
        }),
    )


class StaffMeetingForm(forms.ModelForm):
    attendees = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "form-select", "size": 5}),
        help_text="Select one or more employees. The organizer is included automatically.",
    )

    class Meta:
        model = StaffMeeting
        fields = ("title", "details", "scheduled_at", "tag", "attendees")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "maxlength": 180}),
            "details": forms.Textarea(attrs={"class": "form-control", "rows": 3, "maxlength": 3000}),
            "scheduled_at": forms.DateTimeInput(
                attrs={"class": "form-control", "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "tag": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, employee_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["attendees"].queryset = (
            employee_queryset if employee_queryset is not None else User.objects.none()
        )
        self.fields["scheduled_at"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_scheduled_at(self):
        scheduled_at = self.cleaned_data["scheduled_at"]
        if scheduled_at <= timezone.now():
            raise forms.ValidationError("Choose a meeting time in the future.")
        return scheduled_at

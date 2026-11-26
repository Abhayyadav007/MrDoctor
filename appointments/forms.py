from django import forms
from accounts.models import User
from .models import Appointment


class AppointmentRequestForm(forms.ModelForm):
    doctor = forms.ModelChoiceField(queryset=User.objects.filter(role=User.Role.DOCTOR))

    class Meta:
        model = Appointment
        fields = ("doctor", "date", "time", "reason")
        widgets = {"date": forms.DateInput(attrs={"type": "date"}), "time": forms.TimeInput(attrs={"type": "time"})}

    def clean_date(self):
        from django.utils import timezone
        date = self.cleaned_data["date"]
        if date < timezone.localdate():
            raise forms.ValidationError("Choose today or a future date.")
        return date

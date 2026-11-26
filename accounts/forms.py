from django import forms
from .models import PatientProfile, User


class PatientProfileForm(forms.ModelForm):
    class Meta:
        model = PatientProfile
        fields = ("dob", "gender", "blood_group", "address", "emergency_contact")
        widgets = {"dob": forms.DateInput(attrs={"type": "date"})}


class AccountProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "profile_photo")

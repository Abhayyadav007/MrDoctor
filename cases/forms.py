from django import forms
from accounts.models import User
from .models import Attachment, Case, Visit


class CaseForm(forms.ModelForm):
    class Meta:
        model = Case
        fields = ("title", "description", "priority")


class VisitForm(forms.ModelForm):
    class Meta:
        model = Visit
        fields = ("notes", "diagnosis", "prescription", "next_visit")
        widgets = {"next_visit": forms.DateInput(attrs={"type": "date"})}


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ("file", "description")


class CaseAssignmentForm(forms.ModelForm):
    doctor = forms.ModelChoiceField(queryset=User.objects.filter(role=User.Role.DOCTOR), required=False)

    class Meta:
        model = Case
        fields = ("doctor", "status", "priority")

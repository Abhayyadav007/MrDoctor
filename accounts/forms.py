from django import forms
from django.contrib.auth.forms import UserCreationForm
from allauth.account.forms import LoginForm
from .models import PatientProfile, User


class RoleAwareLoginForm(LoginForm):
    role = forms.ChoiceField(choices=[
        (User.Role.PATIENT, "Patients"),
        (User.Role.DOCTOR, "Doctor"),
        (User.Role.ADMIN, "Admins"),
    ], initial=User.Role.PATIENT, label="Sign in as")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role = self.fields.pop("role")
        selected_role = self.data.get("role") if self.is_bound else self.initial.get("role", role.initial)
        if selected_role == User.Role.PATIENT:
            self.fields["login"].label = "Email address"
            self.fields["login"].widget.attrs.update({
                "placeholder": "Email address",
                "autocomplete": "email",
                "type": "email",
            })
        else:
            self.fields["login"].label = "Username"
            self.fields["login"].widget.attrs.update({
                "placeholder": "Username",
                "autocomplete": "username",
                "type": "text",
            })
        self.fields = {"role": role, **self.fields}

    def clean(self):
        cleaned_data = super().clean()
        selected_role = cleaned_data.get("role")
        if self.user and selected_role != self.user.role:
            self.add_error(None, "The selected account type does not match this account.")
            self.user = None
            self._login = None
        elif self.user and selected_role == User.Role.PATIENT:
            login_identifier = cleaned_data.get("login", "").strip()
            if login_identifier.casefold() != self.user.email.casefold():
                self.add_error("login", "Patients must sign in with their email address.")
                self.user = None
                self._login = None
        elif self.user:
            login_identifier = cleaned_data.get("login", "").strip()
            if login_identifier != self.user.get_username():
                self.add_error("login", "Staff accounts must sign in with their username.")
                self.user = None
                self._login = None
        return cleaned_data


class PatientProfileForm(forms.ModelForm):
    class Meta:
        model = PatientProfile
        fields = ("dob", "gender", "blood_group", "address", "emergency_contact")
        widgets = {"dob": forms.DateInput(attrs={"type": "date"})}


class AccountProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "profile_photo")


class AdminAccountCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("An account already uses this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.ADMIN
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user

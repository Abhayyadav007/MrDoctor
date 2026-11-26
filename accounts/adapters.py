from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from .models import PatientProfile, User


class PatientAccountAdapter(DefaultAccountAdapter):
    def save_user(self, request, user, form, commit=True):
        user.role = User.Role.PATIENT
        user = super().save_user(request, user, form, commit=commit)
        if commit:
            PatientProfile.objects.get_or_create(user=user)
        return user


class PatientSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        user.role = User.Role.PATIENT
        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form=form)
        if user.role != User.Role.PATIENT:
            user.role = User.Role.PATIENT
            user.save(update_fields=["role"])
        PatientProfile.objects.get_or_create(user=user)
        return user

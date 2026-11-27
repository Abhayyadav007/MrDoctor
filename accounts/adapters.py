from allauth.account.adapter import DefaultAccountAdapter
from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import ValidationError
from django.http import HttpResponseForbidden
from .models import PatientProfile, User


class PatientAccountAdapter(DefaultAccountAdapter):
    def clean_email(self, email):
        email = super().clean_email(email).strip().lower()
        if email and User.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email address is already associated with an account.")
        return email

    def save_user(self, request, user, form, commit=True):
        user.role = User.Role.PATIENT
        user = super().save_user(request, user, form, commit=commit)
        if commit:
            PatientProfile.objects.get_or_create(user=user)
        return user


class PatientSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)
        request_user = getattr(request, "user", None)
        if request_user and request_user.is_authenticated and request_user.role != User.Role.PATIENT:
            raise ImmediateHttpResponse(HttpResponseForbidden(
                "Google sign-in is only available to patient accounts."
            ))
        if sociallogin.is_existing and sociallogin.user.role != User.Role.PATIENT:
            raise ImmediateHttpResponse(HttpResponseForbidden(
                "Google sign-in is only available to patient accounts."
            ))
        email = getattr(sociallogin, "_did_authenticate_by_email", None)
        if email and sociallogin.user:
            EmailAddress.objects.update_or_create(
                user=sociallogin.user,
                email=email,
                defaults={"verified": True},
            )

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

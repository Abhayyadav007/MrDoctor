from getpass import getpass

from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User


class Command(BaseCommand):
    help = "Create or securely reset the one configured superadmin account."

    def handle(self, *args, **options):
        email = settings.SUPERADMIN_EMAIL
        existing = User.objects.filter(email__iexact=email).first()
        other_superuser = User.objects.filter(is_superuser=True)
        if existing:
            other_superuser = other_superuser.exclude(pk=existing.pk)
        if other_superuser.exists():
            raise CommandError("A different superuser already exists; resolve it before provisioning.")

        password = getpass(f"New password for {email}: ")
        confirmation = getpass("Confirm password: ")
        if not password or password != confirmation:
            raise CommandError("Passwords are empty or do not match.")

        username = existing.username if existing else email.split("@", 1)[0]
        user = existing or User(username=username, email=email)
        try:
            validate_password(password, user=user)
        except ValidationError as error:
            raise CommandError(str(error)) from error

        with transaction.atomic():
            user.email = email
            user.role = User.Role.ADMIN
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.set_password(password)
            user.save()
            EmailAddress.objects.update_or_create(
                user=user,
                email=email,
                defaults={"primary": True, "verified": True},
            )
        self.stdout.write(self.style.SUCCESS(f"Superadmin ready: {email}"))

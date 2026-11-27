from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.account.models import EmailAddress
from .models import User


@receiver(post_save, sender=User)
def verify_staff_email(sender, instance, **kwargs):
    is_staff_account = instance.is_superuser or instance.role in (User.Role.ADMIN, User.Role.DOCTOR)
    if is_staff_account and instance.email:
        EmailAddress.objects.filter(user=instance, primary=True).exclude(email=instance.email).update(primary=False)
        EmailAddress.objects.update_or_create(
            user=instance,
            email=instance.email,
            defaults={"primary": True, "verified": True},
        )

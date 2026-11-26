from django.db.models.signals import post_save
from django.dispatch import receiver
from allauth.account.models import EmailAddress
from .models import User


@receiver(post_save, sender=User)
def verify_superuser_email(sender, instance, **kwargs):
    if instance.is_superuser and instance.email:
        EmailAddress.objects.filter(user=instance, primary=True).exclude(email=instance.email).update(primary=False)
        EmailAddress.objects.update_or_create(
            user=instance,
            email=instance.email,
            defaults={"primary": True, "verified": True},
        )

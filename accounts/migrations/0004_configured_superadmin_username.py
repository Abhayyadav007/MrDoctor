from django.conf import settings
from django.db import migrations


def set_configured_superadmin_username(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    superadmin = User.objects.filter(
        is_superuser=True,
        email__iexact=settings.SUPERADMIN_EMAIL,
    ).first()
    if not superadmin:
        return
    collision = User.objects.filter(username=settings.SUPERADMIN_USERNAME).exclude(pk=superadmin.pk).exists()
    if collision:
        raise RuntimeError(
            f"Cannot assign configured superadmin username {settings.SUPERADMIN_USERNAME!r}: it is already in use."
        )
    User.objects.filter(pk=superadmin.pk).update(username=settings.SUPERADMIN_USERNAME)


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_user_accounts_only_one_superuser"),
    ]

    operations = [
        migrations.RunPython(set_configured_superadmin_username, migrations.RunPython.noop),
    ]

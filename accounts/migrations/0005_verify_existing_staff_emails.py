from django.db import migrations


def verify_existing_staff_emails(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    EmailAddress = apps.get_model("account", "EmailAddress")

    staff = User.objects.filter(role__in=("ADMIN", "DOCTOR")).exclude(email="")
    for user in staff.iterator():
        address = EmailAddress.objects.filter(user_id=user.pk, email__iexact=user.email).first()
        if address:
            EmailAddress.objects.filter(user_id=user.pk, primary=True).exclude(pk=address.pk).update(primary=False)
            EmailAddress.objects.filter(pk=address.pk).update(primary=True, verified=True)
        else:
            EmailAddress.objects.filter(user_id=user.pk, primary=True).update(primary=False)
            EmailAddress.objects.create(
                user_id=user.pk,
                email=user.email,
                primary=True,
                verified=True,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0009_emailaddress_unique_primary_email"),
        ("accounts", "0004_configured_superadmin_username"),
    ]

    operations = [
        migrations.RunPython(verify_existing_staff_emails, migrations.RunPython.noop),
    ]

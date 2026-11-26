from django.db import transaction
from django.db.models import Q

from calls.models import CallLog
from cases.models import Attachment
from payroll.models import PayrollAdjustment, PayrollRecord
from workplace.models import StaffMeeting


def _delete_stored_files(files):
    for storage, name in files:
        storage.delete(name)


@transaction.atomic
def remove_account(user):
    user = user.__class__.objects.select_for_update().get(pk=user.pk)
    if user.is_superuser:
        raise ValueError("The superadmin account cannot be removed.")

    files = []
    if user.profile_photo:
        files.append((user.profile_photo.storage, user.profile_photo.name))
    for attachment in Attachment.objects.filter(case__patient=user).only("file"):
        if attachment.file:
            files.append((attachment.file.storage, attachment.file.name))

    CallLog.objects.filter(Q(caller=user) | Q(recipient=user)).delete()
    StaffMeeting.objects.filter(organizer=user).delete()
    PayrollAdjustment.objects.filter(actor=user).delete()
    PayrollRecord.objects.filter(doctor=user).delete()
    user.delete()

    if files:
        transaction.on_commit(lambda: _delete_stored_files(files))

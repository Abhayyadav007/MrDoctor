from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from cases.models import Case


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles = ()

    def test_func(self):
        return self.request.user.role in self.allowed_roles or self.request.user.is_superuser


def case_for_user(user, case_id):
    case = get_object_or_404(Case, pk=case_id)
    if user.is_superuser or user.role == "ADMIN":
        return case
    if user.role == "PATIENT" and case.patient_id == user.id:
        return case
    if user.role == "DOCTOR" and case.doctor_id == user.id:
        return case
    raise PermissionDenied

from django.db.models import Q

from accounts.models import User


def managed_employees(manager):
    employees = User.objects.filter(is_active=True).exclude(pk=manager.pk)
    if manager.is_superuser:
        return employees.filter(role__in=(User.Role.ADMIN, User.Role.DOCTOR), is_superuser=False)
    if manager.role == User.Role.ADMIN:
        return employees.filter(role=User.Role.DOCTOR, is_superuser=False)
    return employees.none()


def can_manage_employee(manager, employee):
    if not manager.is_authenticated or manager.pk == employee.pk or not employee.is_active:
        return False
    if manager.is_superuser:
        return employee.role in (User.Role.ADMIN, User.Role.DOCTOR) and not employee.is_superuser
    return manager.role == User.Role.ADMIN and employee.role == User.Role.DOCTOR and not employee.is_superuser


def can_staff_chat(user, peer):
    return can_manage_employee(user, peer) or can_manage_employee(peer, user)


def staff_chat_peers(user):
    managed_ids = managed_employees(user).values("pk")
    managing_admin_ids = User.objects.filter(is_superuser=True, role=User.Role.ADMIN).exclude(pk=user.pk).values("pk")
    if user.is_superuser:
        return managed_employees(user).order_by("role", "last_name", "first_name")
    if user.role == User.Role.ADMIN:
        return User.objects.filter(
            Q(pk__in=managed_ids) | Q(pk__in=managing_admin_ids), is_active=True,
        ).distinct().order_by("role", "last_name", "first_name")
    if user.role == User.Role.DOCTOR:
        admins = User.objects.filter(role=User.Role.ADMIN, is_active=True)
        return admins.order_by("-is_superuser", "last_name", "first_name")
    return User.objects.none()

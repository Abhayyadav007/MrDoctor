from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import DoctorProfile, PatientProfile, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (("Patient Tracker", {"fields": ("role", "phone", "profile_photo")}),)
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff")
    list_filter = ("role", "is_staff")


admin.site.register(DoctorProfile)
admin.site.register(PatientProfile)

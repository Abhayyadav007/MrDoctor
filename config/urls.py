from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from accounts.views import DashboardView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", DashboardView.as_view(), name="dashboard"),
    path("accounts/", include("allauth.urls")),
    path("accounts/", include("accounts.urls")),
    path("cases/", include("cases.urls")),
    path("appointments/", include("appointments.urls")),
    path("chat/", include("chat.urls")),
    path("notifications/", include("notifications.urls")),
]
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()

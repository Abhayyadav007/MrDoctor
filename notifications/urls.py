from django.urls import path
from .views import mark_read

urlpatterns = [path("<int:pk>/read/", mark_read, name="notification_read")]

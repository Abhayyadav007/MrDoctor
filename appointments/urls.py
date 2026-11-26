from django.urls import path
from .views import AppointmentDecisionView, AppointmentRequestView

urlpatterns = [
    path("request/", AppointmentRequestView.as_view(), name="appointment_request"),
    path("<int:pk>/decision/", AppointmentDecisionView.as_view(), name="appointment_decision"),
]

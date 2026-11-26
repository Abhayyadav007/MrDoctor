from django.urls import path
from .views import (
    BonusTierUpdateView,
    CompensationUpdateView,
    DoctorRatingCreateView,
    PayrollAdjustmentCreateView,
    PayrollDashboardView,
    PayrollGenerateView,
    PayrollStatusUpdateView,
)

urlpatterns = [
    path("", PayrollDashboardView.as_view(), name="payroll_dashboard"),
    path("rating/<int:case_id>/", DoctorRatingCreateView.as_view(), name="doctor_rate_case"),
    path("salary/", CompensationUpdateView.as_view(), name="salary_update"),
    path("bonus-tiers/", BonusTierUpdateView.as_view(), name="bonus_tiers_update"),
    path("generate/", PayrollGenerateView.as_view(), name="payroll_generate"),
    path("<int:payroll_id>/adjust/", PayrollAdjustmentCreateView.as_view(), name="payroll_adjust"),
    path("<int:payroll_id>/status/", PayrollStatusUpdateView.as_view(), name="payroll_status"),
]

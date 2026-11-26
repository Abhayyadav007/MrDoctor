from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class DoctorRating(models.Model):
    case = models.OneToOneField("cases.Case", on_delete=models.CASCADE, related_name="doctor_rating")
    patient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submitted_doctor_ratings")
    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_doctor_ratings")
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    feedback = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(score__gte=1, score__lte=5), name="payroll_rating_score_1_to_5"),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.case_id:
            if self.case.patient_id != self.patient_id or self.case.doctor_id != self.doctor_id:
                raise ValidationError("The rating must match the patient and doctor assigned to the case.")
            if self.case.status not in ("Recovered", "Closed"):
                raise ValidationError("Patients may rate a doctor after a case is recovered or closed.")

    def __str__(self):
        return f"{self.score}/5 for {self.doctor} on case #{self.case_id}"


class DoctorCompensation(models.Model):
    doctor = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="compensation", limit_choices_to={"role": "DOCTOR"})
    base_monthly_salary = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="compensation_updates")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(base_monthly_salary__gte=0), name="payroll_base_salary_nonnegative"),
        ]

    def __str__(self):
        return f"{self.doctor}: INR {self.base_monthly_salary}/month"


class RatingBonusTier(models.Model):
    stars = models.PositiveSmallIntegerField(unique=True, validators=[MinValueValidator(1), MaxValueValidator(5)])
    monthly_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["stars"]
        constraints = [
            models.CheckConstraint(condition=Q(stars__gte=1, stars__lte=5), name="payroll_tier_stars_1_to_5"),
            models.CheckConstraint(condition=Q(monthly_bonus__gte=0), name="payroll_tier_bonus_nonnegative"),
        ]

    def __str__(self):
        return f"{self.stars} stars: INR {self.monthly_bonus}"


class PayrollRecord(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        APPROVED = "APPROVED", "Approved"
        PAID = "PAID", "Paid"

    doctor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payroll_records")
    period = models.DateField(help_text="First day of the payroll month")
    base_salary = models.DecimalField(max_digits=12, decimal_places=2)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    rating_count = models.PositiveIntegerField(default=0)
    rating_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    generated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
                                     related_name="generated_payroll_records")
    generated_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-period", "doctor__last_name"]
        constraints = [
            models.UniqueConstraint(fields=("doctor", "period"), name="payroll_one_record_per_doctor_month"),
            models.CheckConstraint(condition=Q(period__day=1), name="payroll_period_first_of_month"),
            models.CheckConstraint(condition=Q(base_salary__gte=0), name="payroll_record_base_nonnegative"),
            models.CheckConstraint(condition=Q(rating_bonus__gte=0), name="payroll_record_bonus_nonnegative"),
        ]

    @property
    def adjustment_total(self):
        return self.adjustments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")

    @property
    def total_due(self):
        return self.base_salary + self.rating_bonus + self.adjustment_total

    def __str__(self):
        return f"{self.doctor} · {self.period:%B %Y}"


class PayrollAdjustment(models.Model):
    payroll = models.ForeignKey(PayrollRecord, on_delete=models.CASCADE, related_name="adjustments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=240)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payroll_adjustments")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PayrollAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=80)
    details = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

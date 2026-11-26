from datetime import date
from decimal import Decimal

from django import forms
from accounts.models import User
from .models import PayrollAdjustment, DoctorRating


class DoctorRatingForm(forms.ModelForm):
    class Meta:
        model = DoctorRating
        fields = ("score", "feedback")
        widgets = {
            "score": forms.Select(
                choices=[(score, f"{score} star{'s' if score != 1 else ''}") for score in range(1, 6)],
                attrs={"class": "form-select"},
            ),
            "feedback": forms.Textarea(attrs={"rows": 3, "maxlength": 500, "class": "form-control"}),
        }


class PayrollGenerationForm(forms.Form):
    month = forms.CharField(widget=forms.DateInput(attrs={"type": "month"}), label="Payroll month")

    def clean_month(self):
        value = self.cleaned_data["month"]
        try:
            year, month = (int(part) for part in value.split("-", 1))
            return date(year, month, 1)
        except (ValueError, TypeError):
            raise forms.ValidationError("Choose a valid payroll month.")


class RatingBonusSettingsForm(forms.Form):
    def __init__(self, *args, **kwargs):
        from .models import RatingBonusTier
        super().__init__(*args, **kwargs)
        tiers = {tier.stars: tier.monthly_bonus for tier in RatingBonusTier.objects.all()}
        for stars in range(1, 6):
            self.fields[f"bonus_{stars}"] = forms.DecimalField(
                min_value=Decimal("0.00"),
                max_digits=12,
                decimal_places=2,
                initial=tiers.get(stars, Decimal("0.00")),
                label=f"{stars} star{'s' if stars != 1 else ''} (INR monthly bonus)",
            )

    def save(self, actor):
        from .models import RatingBonusTier
        for stars in range(1, 6):
            RatingBonusTier.objects.update_or_create(
                stars=stars,
                defaults={"monthly_bonus": self.cleaned_data[f"bonus_{stars}"], "updated_by": actor},
            )


class DoctorCompensationForm(forms.Form):
    doctor = forms.ModelChoiceField(
        queryset=User.objects.filter(role=User.Role.DOCTOR).order_by("last_name", "first_name")
    )
    base_monthly_salary = forms.DecimalField(
        min_value=Decimal("0.00"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        label="Monthly base salary (INR)",
    )
    reason = forms.CharField(max_length=240, label="Change reason")


class PayrollAdjustmentForm(forms.ModelForm):
    class Meta:
        model = PayrollAdjustment
        fields = ("amount", "reason")
        widgets = {"amount": forms.NumberInput(attrs={"step": "0.01"})}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount == 0:
            raise forms.ValidationError("Adjustment must be a non-zero INR amount.")
        return amount

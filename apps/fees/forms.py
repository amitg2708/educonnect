"""
EduConnect Fees Forms.
Provides forms for:
- Fee Structure configuration
- Student fee assignment with installment schemes
- Recording offline counter payments
- Verification of transactions
- Authorized fee adjustments and corrections
"""

from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import (
    FeeCategory,
    FeeStructure,
    FeeStructureItem,
    StudentFeeAllocation,
    FeeInstallment,
    Payment,
    PaymentMethod,
    PaymentStatus,
    FeeAdjustment,
    AdjustmentType,
)

User = get_user_model()


class FeeCategoryForm(forms.ModelForm):
    class Meta:
        model = FeeCategory
        fields = ["name", "code", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Tuition Fee"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. TUIT"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Fee component description"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class FeeStructureForm(forms.ModelForm):
    class Meta:
        model = FeeStructure
        fields = ["title", "code", "academic_year", "course", "total_amount", "description", "is_active"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Standard High School Tuition 2026-27"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. FS-HS-2026"}),
            "academic_year": forms.TextInput(attrs={"class": "form-control", "placeholder": "2026-2027"}),
            "course": forms.Select(attrs={"class": "form-select"}),
            "total_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Institutional billing terms"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class FeeStructureItemForm(forms.ModelForm):
    class Meta:
        model = FeeStructureItem
        fields = ["category", "amount", "is_optional"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "is_optional": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class StudentFeeAssignmentForm(forms.Form):
    """
    Form to allocate fee structures to an individual student or an entire course cohort.
    """
    ASSIGN_TARGET_CHOICES = [
        ("student", "Specific Individual Student"),
        ("course", "Entire Enrolled Course Cohort"),
    ]

    INSTALLMENT_SCHEME_CHOICES = [
        ("single", "Single Full Lump-Sum Payment (Due immediately)"),
        ("two_semesters", "Two Semester Installments (50% / 50%)"),
        ("four_quarters", "Four Quarterly Installments (25% each)"),
    ]

    target_type = forms.ChoiceField(
        choices=ASSIGN_TARGET_CHOICES,
        widget=forms.Select(attrs={"class": "form-select", "id": "target_type_select"}),
        initial="student",
    )
    student = forms.ModelChoiceField(
        queryset=User.objects.filter(role="student").order_by("username"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "student_select"}),
        help_text="Select target student if allocating individually.",
    )
    course = forms.ModelChoiceField(
        queryset=None,  # Populated dynamically in __init__
        required=False,
        widget=forms.Select(attrs={"class": "form-select", "id": "course_select"}),
        help_text="Select target course to bulk-assign to enrolled students.",
    )
    fee_structure = forms.ModelChoiceField(
        queryset=FeeStructure.objects.filter(is_active=True).order_by("title"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    academic_year = forms.CharField(
        max_length=30,
        initial="2026-2027",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    discount_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        initial=Decimal("0.00"),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        help_text="Grant, merit scholarship, or sibling discount.",
    )
    discount_reason = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Merit Scholarship 2026"}),
    )
    installment_scheme = forms.ChoiceField(
        choices=INSTALLMENT_SCHEME_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
        initial="two_semesters",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Course
        self.fields["course"].queryset = Course.objects.filter(is_active=True)

    def clean(self):
        cleaned_data = super().clean()
        target_type = cleaned_data.get("target_type")
        student = cleaned_data.get("student")
        course = cleaned_data.get("course")
        fee_structure = cleaned_data.get("fee_structure")
        discount = cleaned_data.get("discount_amount") or Decimal("0.00")

        if target_type == "student" and not student:
            self.add_error("student", "Please choose a student for individual allocation.")
        if target_type == "course" and not course:
            self.add_error("course", "Please select a course for cohort bulk allocation.")

        if fee_structure and discount > fee_structure.total_amount:
            self.add_error("discount_amount", "Discount cannot exceed the total structure fee amount.")

        return cleaned_data


class OfflinePaymentForm(forms.Form):
    """
    Form used by Accounts Staff and Admin to record authorized offline payments.
    """
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    payment_method = forms.ChoiceField(
        choices=[
            (PaymentMethod.CASH, "Cash (Authorized Counter Deposit)"),
            (PaymentMethod.BANK_TRANSFER, "Bank Wire / NEFT / RTGS / IMPS"),
            (PaymentMethod.CHEQUE, "Cheque / Banker's Draft"),
            (PaymentMethod.DEMAND_DRAFT, "Demand Draft (DD)"),
            (PaymentMethod.POS_TERMINAL, "POS Card Terminal Swipe"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
        initial=PaymentMethod.CASH,
    )
    transaction_reference = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "placeholder": "Bank UTR, Cheque No, DD No, or Counter Slip ID",
        }),
        help_text="Unique external transaction reference ID.",
    )
    payment_date = forms.DateField(
        initial=timezone.now().date,
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )
    payer_name = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Full name of depositor"}),
    )
    payer_relationship = forms.CharField(
        max_length=50,
        required=False,
        initial="Self",
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Father, Mother, Guardian, Self"}),
    )
    installment_id = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Optionally assign to a specific installment milestone.",
    )
    notes = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional internal remarks"}),
    )

    def __init__(self, allocation, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allocation = allocation
        # Populate installment choices
        choices = [("", "-- Automatically apply to earliest open dues --")]
        for inst in allocation.installments.all().order_by("installment_number"):
            choices.append((str(inst.id), f"{inst.title} (Remaining: ${inst.remaining_due:.2f})"))
        self.fields["installment_id"].choices = choices

    def clean_amount(self):
        amt = self.cleaned_data.get("amount")
        if not amt or amt <= Decimal("0.00"):
            raise forms.ValidationError("Payment amount must be greater than zero.")
        return amt

    def clean_transaction_reference(self):
        ref = self.cleaned_data.get("transaction_reference", "").strip()
        if not ref:
            raise forms.ValidationError("Transaction reference is required.")
        if Payment.objects.filter(transaction_reference=ref).exists():
            raise forms.ValidationError(f"Transaction reference '{ref}' has already been processed.")
        return ref


class PaymentVerificationForm(forms.Form):
    """
    Form to verify or reject a pending payment record.
    """
    decision = forms.ChoiceField(
        choices=[
            ("verify", "Verify & Issue Official Receipt"),
            ("reject", "Reject Transaction (Invalid / Unreconciled)"),
        ],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        initial="verify",
    )
    notes = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Bank reconciliation notes / Reason for rejection"}),
    )


class FeeAdjustmentForm(forms.Form):
    """
    Authorized accounting adjustment form with audit trail.
    """
    adjustment_type = forms.ChoiceField(
        choices=AdjustmentType.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "0.00"}),
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Mandatory official justification for this adjustment"}),
        help_text="Required official audit trail rationale.",
    )
    reference_document = forms.CharField(
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Bursar Memo # 2026/089"}),
    )

    def clean_amount(self):
        amt = self.cleaned_data.get("amount")
        if not amt or amt <= Decimal("0.00"):
            raise forms.ValidationError("Adjustment amount must be positive.")
        return amt

    def clean_reason(self):
        reason = self.cleaned_data.get("reason", "").strip()
        if not reason:
            raise forms.ValidationError("Audit reason is required.")
        return reason

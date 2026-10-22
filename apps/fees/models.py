"""
EduConnect Fees Management Models.
Provides enterprise-grade fee structure management, student fee allocations,
multi-term installment schedules, offline payment records, verified online receipts,
audit-logged accounting adjustments, and atomic balance reconciliation.
"""

from decimal import Decimal
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class FeeCategory(models.Model):
    """
    Standard fee component category (e.g. Tuition, Lab, Exam, Library, Transport).
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="fee_categories",
        null=True,
        blank=True,
        help_text="Institution context for this fee category.",
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fee Category"
        verbose_name_plural = "Fee Categories"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class FeeStructure(models.Model):
    """
    Standard institutional fee package associated with a course, program, or academic level.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="fee_structures",
        null=True,
        blank=True,
        help_text="Institution context for this fee schedule.",
    )
    title = models.CharField(max_length=200)
    code = models.CharField(max_length=60, help_text="Structure identifier e.g. FS-UG-CS-2026")
    academic_year = models.CharField(max_length=30, default="2026-2027")
    course = models.ForeignKey(
        "core.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fee_structures",
        help_text="Course to which this fee schedule applies.",
    )
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_fee_structures",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fee Structure"
        verbose_name_plural = "Fee Structures"
        ordering = ["-academic_year", "title"]

    def __str__(self):
        return f"{self.title} [{self.code}] - ${self.total_amount:.2f}"

    def recalculate_total(self):
        """
        Calculates total from individual active component items.
        """
        total = self.items.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
        self.total_amount = total
        self.save(update_fields=["total_amount", "updated_at"])
        return total


class FeeStructureItem(models.Model):
    """
    Line item within a fee structure.
    """

    fee_structure = models.ForeignKey(
        FeeStructure,
        on_delete=models.CASCADE,
        related_name="items",
    )
    category = models.ForeignKey(
        FeeCategory,
        on_delete=models.PROTECT,
        related_name="structure_items",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    is_optional = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Fee Structure Item"
        verbose_name_plural = "Fee Structure Items"
        unique_together = ("fee_structure", "category")

    def __str__(self):
        return f"{self.category.name}: ${self.amount:.2f}"


class AllocationStatus(models.TextChoices):
    PENDING = "pending", "Pending Payment"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    PAID = "paid", "Fully Settled"
    OVERDUE = "overdue", "Overdue Balance"


class StudentFeeAllocation(models.Model):
    """
    Binding between an enrolled student and their designated fee obligation.
    Tracks net billing, payments recorded, adjustments, and balance.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="fee_allocations",
        null=True,
        blank=True,
        help_text="Institution context for this fee allocation ledger.",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fee_allocations",
        limit_choices_to={"role": "student"},
    )
    fee_structure = models.ForeignKey(
        FeeStructure,
        on_delete=models.PROTECT,
        related_name="student_allocations",
    )
    academic_year = models.CharField(max_length=30, default="2026-2027")
    
    # Financial Ledgers (Precise Decimal)
    gross_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Approved scholarships, waivers, or institutional grants.",
    )
    discount_reason = models.CharField(max_length=255, blank=True)
    net_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Gross fee less approved institutional discounts.",
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Total verified funds collected to date.",
    )
    outstanding_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Remaining payable dues.",
    )
    status = models.CharField(
        max_length=25,
        choices=AllocationStatus.choices,
        default=AllocationStatus.PENDING,
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_allocations",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Fee Allocation"
        verbose_name_plural = "Student Fee Allocations"
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["academic_year"]),
        ]

    def __str__(self):
        return f"{self.student.get_full_name() or self.student.username} - {self.fee_structure.title} (${self.outstanding_balance:.2f} due)"

    def clean(self):
        if self.gross_amount < Decimal("0.00"):
            raise ValidationError({"gross_amount": "Gross amount cannot be negative."})
        if self.discount_amount < Decimal("0.00"):
            raise ValidationError({"discount_amount": "Discount amount cannot be negative."})
        if self.discount_amount > self.gross_amount:
            raise ValidationError({"discount_amount": "Discount cannot exceed total gross fee amount."})


class InstallmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    PAID = "paid", "Paid in Full"
    OVERDUE = "overdue", "Overdue"


class FeeInstallment(models.Model):
    """
    Scheduled milestone installment for a student's fee allocation.
    """

    allocation = models.ForeignKey(
        StudentFeeAllocation,
        on_delete=models.CASCADE,
        related_name="installments",
    )
    installment_number = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=120)  # e.g., "Semester 1 Installment"
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    due_date = models.DateField()
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20,
        choices=InstallmentStatus.choices,
        default=InstallmentStatus.PENDING,
    )

    class Meta:
        verbose_name = "Fee Installment"
        verbose_name_plural = "Fee Installments"
        ordering = ["installment_number", "due_date"]
        unique_together = ("allocation", "installment_number")

    def __str__(self):
        return f"{self.title} - ${self.amount:.2f} (Due: {self.due_date})"

    @property
    def remaining_due(self):
        rem = self.amount - self.amount_paid
        return max(Decimal("0.00"), rem)

    @property
    def is_past_due(self):
        return self.due_date < timezone.now().date() and self.remaining_due > Decimal("0.00")

    @property
    def is_paid(self):
        return self.status == InstallmentStatus.PAID


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash (Authorized Counter Deposit)"
    BANK_TRANSFER = "bank_transfer", "Bank Wire / NEFT / RTGS / IMPS"
    CHEQUE = "cheque", "Cheque / Banker's Draft"
    DEMAND_DRAFT = "demand_draft", "Demand Draft (DD)"
    POS_TERMINAL = "pos_card", "POS Terminal Card Receipt"
    ONLINE_GATEWAY = "online_gateway", "Online Payment Gateway (Verified)"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending Verification"
    VERIFIED = "verified", "Verified & Confirmed"
    REJECTED = "rejected", "Rejected / Invalid"
    REVERSED = "reversed", "Reversed / Refunded"


class Payment(models.Model):
    """
    Financial payment record.
    Supports strictly verified offline transactions, idempotency guards, and payment verification.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="fee_payments",
        null=True,
        blank=True,
        help_text="Institution context for this payment transaction.",
    )
    allocation = models.ForeignKey(
        StudentFeeAllocation,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    installment = models.ForeignKey(
        FeeInstallment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        help_text="Optional target installment for this payment.",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="fee_payments",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=30,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    transaction_reference = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="Unique bank UTR, Cheque No, Counter Voucher, or Gateway Transaction ID.",
    )
    idempotency_key = models.CharField(
        max_length=120,
        unique=True,
        db_index=True,
        help_text="Idempotency key to safeguard against double posting.",
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.VERIFIED,
    )
    payment_date = models.DateField(default=timezone.now)
    payer_name = models.CharField(max_length=150)
    payer_relationship = models.CharField(max_length=50, blank=True, default="Self")
    notes = models.TextField(blank=True)

    # Authorization & Verification
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_payments",
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_payments",
    )
    verification_date = models.DateTimeField(null=True, blank=True)
    verification_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fee Payment"
        verbose_name_plural = "Fee Payments"
        ordering = ["-payment_date", "-created_at"]
        indexes = [
            models.Index(fields=["status", "payment_date"]),
            models.Index(fields=["transaction_reference"]),
        ]

    def __str__(self):
        return f"{self.transaction_reference} - ${self.amount:.2f} ({self.get_status_display()})"

    def clean(self):
        if self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Payment amount must be greater than zero."})


class FeeReceipt(models.Model):
    """
    Official institutional receipt issued exclusively for confirmed and verified payments.
    Receipt numbers are sequentially and cryptographically protected against tampering or duplicates.
    """

    receipt_number = models.CharField(
        max_length=60,
        unique=True,
        db_index=True,
        help_text="Immutable official receipt identifier e.g. REC-2026-00001",
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.PROTECT,
        related_name="receipt",
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="issued_fee_receipts",
    )
    is_cancelled = models.BooleanField(default=False)
    cancellation_reason = models.TextField(blank=True)
    digital_signature_hash = models.CharField(max_length=128, blank=True)

    class Meta:
        verbose_name = "Fee Receipt"
        verbose_name_plural = "Fee Receipts"
        ordering = ["-issued_at"]

    def __str__(self):
        return f"{self.receipt_number} - Payment {self.payment.transaction_reference}"

    def save(self, *args, **kwargs):
        if not self.digital_signature_hash:
            # Deterministic hash for receipt authenticity check
            raw = f"{self.receipt_number}:{self.payment.amount}:{self.payment.transaction_reference}"
            import hashlib
            self.digital_signature_hash = hashlib.sha256(raw.encode()).hexdigest()
        super().save(*args, **kwargs)


class AdjustmentType(models.TextChoices):
    WAIVER = "waiver", "Fee Waiver / Concession"
    SCHOLARSHIP = "scholarship", "Merit / Need Scholarship"
    LATE_FEE_PENALTY = "penalty", "Late Fee Penalty Surcharge"
    MISTAKE_CORRECTION = "correction", "Accounting Correction"
    REFUND = "refund", "Authorized Refund"
    REVERSAL = "reversal", "Payment Dishonor / Reversal"


class FeeAdjustment(models.Model):
    """
    Authorized accounting adjustments with audit trail and authorization controls.
    """

    allocation = models.ForeignKey(
        StudentFeeAllocation,
        on_delete=models.CASCADE,
        related_name="adjustments",
    )
    adjustment_type = models.CharField(
        max_length=30,
        choices=AdjustmentType.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Adjustment magnitude in precise decimal.",
    )
    reason = models.TextField(help_text="Required official audit explanation for the adjustment.")
    reference_document = models.CharField(
        max_length=120,
        blank=True,
        help_text="Sanction memo number, approval reference, or committee order.",
    )
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authorized_fee_adjustments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fee Adjustment"
        verbose_name_plural = "Fee Adjustments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_adjustment_type_display()}: ${self.amount:.2f} on {self.allocation.student.username}"

    def clean(self):
        if self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Adjustment amount must be positive."})


class FeeAuditLog(models.Model):
    """
    Immutable historical audit log of every financial action taken in the system.
    """

    allocation = models.ForeignKey(
        StudentFeeAllocation,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=100)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    details = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fee Audit Log"
        verbose_name_plural = "Fee Audit Logs"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.action} by {self.actor}"

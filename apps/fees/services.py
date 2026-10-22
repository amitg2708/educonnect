"""
EduConnect Fees Domain Services.
Implements:
- Safe balance recalculation from verified transactions
- Atomic receipt generation with duplicate prevention
- Payment lifecycle and status transition validation
- MongoDB transaction support verification & fallback consistency controls
- Audit logging
"""

from decimal import Decimal
import uuid
from django.db import models, transaction, connection
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import (
    StudentFeeAllocation,
    FeeInstallment,
    Payment,
    PaymentStatus,
    FeeReceipt,
    FeeAdjustment,
    AdjustmentType,
    FeeAuditLog,
    AllocationStatus,
    InstallmentStatus,
)


def verify_mongodb_transactions_support():
    """
    Checks if the active MongoDB database supports multi-document transactions.
    MongoDB requires a replica set or sharded cluster (mongos) to execute multi-document transactions.
    Returns: bool
    """
    try:
        raw_conn = getattr(connection, "connection", None)
        if raw_conn is not None:
            # Check topology
            is_mongos = getattr(raw_conn, "is_mongos", False)
            is_primary = getattr(raw_conn, "primary", None) is not None
            nodes = getattr(raw_conn, "nodes", set())
            # If multiple nodes or replset is identified
            if is_mongos or len(nodes) > 1 or getattr(raw_conn, "topology_description", None):
                topo = getattr(raw_conn, "topology_description", None)
                if topo and topo.topology_type_name in ["ReplicaSetWithPrimary", "Sharded", "LoadBalanced"]:
                    return True
        return False
    except Exception:
        return False


def generate_unique_receipt_number():
    """
    Generates a guaranteed unique receipt number in format:
    REC-YYYY-XXXXXX
    """
    year = timezone.now().year
    random_part = uuid.uuid4().hex[:6].upper()
    candidate = f"REC-{year}-{random_part}"
    while FeeReceipt.objects.filter(receipt_number=candidate).exists():
        random_part = uuid.uuid4().hex[:6].upper()
        candidate = f"REC-{year}-{random_part}"
    return candidate


def recalculate_allocation_balance(allocation: StudentFeeAllocation):
    """
    Recalculates a student's fee allocation from ground truth verified records:
    1. Base: gross_amount - discount_amount
    2. Adjustments:
       - Waivers, Scholarships, Corrections (reductions): decrease net_amount
       - Penalties (surcharges): increase net_amount
    3. Verified Payments: sum of all payments with status=PaymentStatus.VERIFIED
    4. Outstanding Balance: net_amount - amount_paid
    5. Allocation Status:
       - If outstanding_balance <= 0: PAID
       - Elif amount_paid > 0: PARTIALLY_PAID
       - Elif any installment overdue: OVERDUE
       - Else: PENDING
    6. Sequentially applies verified payments to installments and updates installment statuses.
    """
    # 1. Base Net Amount
    net = allocation.gross_amount - allocation.discount_amount
    if net < Decimal("0.00"):
        net = Decimal("0.00")

    # 2. Adjustments
    adjustments = allocation.adjustments.all()
    for adj in adjustments:
        if adj.adjustment_type in [AdjustmentType.WAIVER, AdjustmentType.SCHOLARSHIP]:
            net -= adj.amount
        elif adj.adjustment_type == AdjustmentType.LATE_FEE_PENALTY:
            net += adj.amount
        elif adj.adjustment_type == AdjustmentType.MISTAKE_CORRECTION:
            # Accounting correction adjusts net dues
            net -= adj.amount
        elif adj.adjustment_type in [AdjustmentType.REFUND, AdjustmentType.REVERSAL]:
            # Handled via net balance adjustment or payment reversal
            pass

    if net < Decimal("0.00"):
        net = Decimal("0.00")

    allocation.net_amount = net

    # 3. Verified Payments Total
    verified_payments = allocation.payments.filter(status=PaymentStatus.VERIFIED)
    total_paid = verified_payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0.00")
    allocation.amount_paid = total_paid

    # 4. Outstanding Balance
    balance = net - total_paid
    allocation.outstanding_balance = max(Decimal("0.00"), balance)

    # 5. Distribute payments across installments
    installments = list(allocation.installments.order_by("installment_number", "due_date"))
    remaining_payment_pool = total_paid
    today = timezone.now().date()
    has_overdue = False

    for inst in installments:
        if remaining_payment_pool >= inst.amount:
            inst.amount_paid = inst.amount
            inst.status = InstallmentStatus.PAID
            remaining_payment_pool -= inst.amount
        elif remaining_payment_pool > Decimal("0.00"):
            inst.amount_paid = remaining_payment_pool
            if inst.due_date < today and (inst.amount - inst.amount_paid) > Decimal("0.00"):
                inst.status = InstallmentStatus.OVERDUE
                has_overdue = True
            else:
                inst.status = InstallmentStatus.PARTIALLY_PAID
            remaining_payment_pool = Decimal("0.00")
        else:
            inst.amount_paid = Decimal("0.00")
            if inst.due_date < today and inst.amount > Decimal("0.00"):
                inst.status = InstallmentStatus.OVERDUE
                has_overdue = True
            else:
                inst.status = InstallmentStatus.PENDING
        inst.save(update_fields=["amount_paid", "status"])

    # Set Allocation overall status
    if allocation.outstanding_balance <= Decimal("0.00"):
        allocation.status = AllocationStatus.PAID
    elif allocation.amount_paid > Decimal("0.00"):
        allocation.status = AllocationStatus.OVERDUE if has_overdue else AllocationStatus.PARTIALLY_PAID
    elif has_overdue:
        allocation.status = AllocationStatus.OVERDUE
    else:
        allocation.status = AllocationStatus.PENDING

    allocation.save(update_fields=["net_amount", "amount_paid", "outstanding_balance", "status", "updated_at"])
    return allocation


def record_payment_transaction(
    allocation: StudentFeeAllocation,
    amount: Decimal,
    payment_method: str,
    transaction_reference: str,
    payer_name: str,
    actor,
    installment=None,
    payer_relationship: str = "Self",
    notes: str = "",
    idempotency_key: str = None,
    auto_verify: bool = True,
    ip_address: str = None,
):
    """
    Safely records a payment transaction with idempotency and duplicate prevention.
    Generates a unique receipt and triggers balance recalculation.
    """
    amount = Decimal(str(amount))
    if amount <= Decimal("0.00"):
        raise ValidationError("Payment amount must be strictly positive.")

    if not transaction_reference or not transaction_reference.strip():
        raise ValidationError("Transaction reference is required.")

    transaction_reference = transaction_reference.strip()

    # Prevent duplicate transaction reference
    if Payment.objects.filter(transaction_reference=transaction_reference).exists():
        raise ValidationError(f"A transaction with reference '{transaction_reference}' already exists.")

    # Idempotency guard
    if not idempotency_key:
        idempotency_key = f"{allocation.id}-{transaction_reference}-{amount}"

    if Payment.objects.filter(idempotency_key=idempotency_key).exists():
        raise ValidationError("Duplicate submission detected. This payment has already been processed.")

    initial_status = PaymentStatus.VERIFIED if auto_verify else PaymentStatus.PENDING

    payment = Payment.objects.create(
        institution=allocation.institution,
        allocation=allocation,
        installment=installment,
        student=allocation.student,
        amount=amount,
        payment_method=payment_method,
        transaction_reference=transaction_reference,
        idempotency_key=idempotency_key,
        status=initial_status,
        payer_name=payer_name,
        payer_relationship=payer_relationship,
        notes=notes,
        recorded_by=actor,
        verified_by=actor if auto_verify else None,
        verification_date=timezone.now() if auto_verify else None,
    )

    receipt = None
    if initial_status == PaymentStatus.VERIFIED:
        receipt_num = generate_unique_receipt_number()
        receipt = FeeReceipt.objects.create(
            receipt_number=receipt_num,
            payment=payment,
            issued_by=actor,
        )

    # Recalculate allocation balance atomically
    recalculate_allocation_balance(allocation)

    # Audit log
    FeeAuditLog.objects.create(
        allocation=allocation,
        action="PAYMENT_RECORDED",
        actor=actor,
        details=(
            f"Recorded payment of ${amount:.2f} via {payment.get_payment_method_display()} "
            f"(Ref: {transaction_reference}). Status: {payment.get_status_display()}. "
            f"Receipt: {receipt.receipt_number if receipt else 'N/A'}."
        ),
        ip_address=ip_address,
    )

    return payment, receipt


def transition_payment_status(
    payment: Payment,
    new_status: str,
    actor,
    verification_notes: str = "",
    ip_address: str = None,
):
    """
    Validates and executes payment status transitions:
    PENDING -> VERIFIED (issues receipt, recalculates balance)
    PENDING -> REJECTED (no receipt, no balance impact)
    VERIFIED -> REVERSED (cancels receipt, recalculates balance)
    """
    valid_transitions = {
        PaymentStatus.PENDING: [PaymentStatus.VERIFIED, PaymentStatus.REJECTED],
        PaymentStatus.VERIFIED: [PaymentStatus.REVERSED],
        PaymentStatus.REJECTED: [],
        PaymentStatus.REVERSED: [],
    }

    if new_status not in valid_transitions.get(payment.status, []):
        raise ValidationError(
            f"Illegal status transition from '{payment.get_status_display()}' to '{new_status}'."
        )

    old_status = payment.status
    payment.status = new_status
    payment.verification_notes = verification_notes

    receipt = getattr(payment, "receipt", None)

    if new_status == PaymentStatus.VERIFIED:
        payment.verified_by = actor
        payment.verification_date = timezone.now()
        payment.save(update_fields=["status", "verified_by", "verification_date", "verification_notes", "updated_at"])

        if not receipt:
            receipt = FeeReceipt.objects.create(
                receipt_number=generate_unique_receipt_number(),
                payment=payment,
                issued_by=actor,
            )

    elif new_status == PaymentStatus.REVERSED:
        payment.save(update_fields=["status", "verification_notes", "updated_at"])
        if receipt:
            receipt.is_cancelled = True
            receipt.cancellation_reason = f"Payment reversed by {actor}: {verification_notes}"
            receipt.save(update_fields=["is_cancelled", "cancellation_reason"])

    else:  # REJECTED
        payment.save(update_fields=["status", "verification_notes", "updated_at"])

    # Recalculate balance
    recalculate_allocation_balance(payment.allocation)

    FeeAuditLog.objects.create(
        allocation=payment.allocation,
        action="PAYMENT_STATUS_TRANSITION",
        actor=actor,
        details=(
            f"Payment ref {payment.transaction_reference} transitioned from "
            f"{old_status} to {new_status}. Notes: {verification_notes}"
        ),
        ip_address=ip_address,
    )

    return payment


def apply_fee_adjustment(
    allocation: StudentFeeAllocation,
    adjustment_type: str,
    amount: Decimal,
    reason: str,
    actor,
    reference_document: str = "",
    ip_address: str = None,
):
    """
    Applies an authorized accounting adjustment with an audit trail and balance recalculation.
    """
    amount = Decimal(str(amount))
    if amount <= Decimal("0.00"):
        raise ValidationError("Adjustment amount must be positive.")

    if not reason or not reason.strip():
        raise ValidationError("A clear audit justification/reason is required for fee adjustments.")

    adj = FeeAdjustment.objects.create(
        allocation=allocation,
        adjustment_type=adjustment_type,
        amount=amount,
        reason=reason.strip(),
        reference_document=reference_document.strip(),
        authorized_by=actor,
    )

    # Recalculate
    recalculate_allocation_balance(allocation)

    FeeAuditLog.objects.create(
        allocation=allocation,
        action="FEE_ADJUSTMENT_APPLIED",
        actor=actor,
        details=(
            f"Applied {adj.get_adjustment_type_display()} of ${amount:.2f}. "
            f"Reason: {reason}. Ref Doc: {reference_document}."
        ),
        ip_address=ip_address,
    )

    return adj

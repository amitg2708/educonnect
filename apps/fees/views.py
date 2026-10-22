"""
EduConnect Fees Management Views.
Implements:
- Student & Parent fee portals (structures, installment schedules, balances, verified receipt downloads)
- Accounts & Admin workspace (structures, cohort assignment, offline collection, online verification,
  receipts, adjustments, audit logs, overdue accounts report)
"""

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Sum, Q
from django.http import HttpResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from apps.accounts.decorators import role_required, accounts_required
from apps.accounts.models import Role, ParentStudentLink
from .models import (
    FeeCategory,
    FeeStructure,
    FeeStructureItem,
    StudentFeeAllocation,
    FeeInstallment,
    Payment,
    PaymentMethod,
    PaymentStatus,
    FeeReceipt,
    FeeAdjustment,
    AdjustmentType,
    FeeAuditLog,
    AllocationStatus,
    InstallmentStatus,
)
from .forms import (
    FeeCategoryForm,
    FeeStructureForm,
    FeeStructureItemForm,
    StudentFeeAssignmentForm,
    OfflinePaymentForm,
    PaymentVerificationForm,
    FeeAdjustmentForm,
)
from .services import (
    record_payment_transaction,
    transition_payment_status,
    apply_fee_adjustment,
    recalculate_allocation_balance,
)
from .receipt_generator import generate_fee_receipt_pdf

User = get_user_model()


# ==============================================================================
# STUDENT & PARENT VIEWS
# ==============================================================================

@login_required
@role_required(Role.STUDENT, Role.ADMIN)
def student_fee_overview(request):
    """
    Personal fee portal for enrolled students.
    Shows applicable fee structures, installment schedules, total dues, amounts paid,
    outstanding balances, payment history, and receipt download links.
    """
    allocations = (
        StudentFeeAllocation.objects.filter(student=request.user)
        .select_related("fee_structure", "fee_structure__course")
        .prefetch_related("installments", "payments", "adjustments")
        .order_by("-academic_year", "-created_at")
    )
    payments = (
        Payment.objects.filter(student=request.user)
        .select_related("allocation", "allocation__fee_structure")
        .order_by("-payment_date", "-created_at")
    )

    if getattr(request, "institution", None):
        allocations = allocations.filter(institution=request.institution)
        payments = payments.filter(institution=request.institution)

    # Aggregate student financial totals
    total_gross = sum(a.gross_amount for a in allocations)
    total_concessions = sum(a.discount_amount for a in allocations)
    total_net = sum(a.net_amount for a in allocations)
    total_paid = sum(a.amount_paid for a in allocations)
    total_outstanding = sum(a.outstanding_balance for a in allocations)

    context = {
        "allocations": allocations,
        "total_gross": total_gross,
        "total_concessions": total_concessions,
        "total_net": total_net,
        "total_paid": total_paid,
        "total_outstanding": total_outstanding,
        "payments": payments,
    }
    return render(request, "fees/student/overview.html", context)


@login_required
@role_required(Role.PARENT, Role.ADMIN)
def parent_child_fees_view(request, student_id):
    """
    Fee portal for parents to view applicable fees and payments for their linked children.
    Strictly verifies parent-child authorization link.
    """
    # Enforce parent-child authorization link
    link_filter = {
        "parent": request.user,
        "student_id": student_id,
        "is_authorized": True,
    }
    if getattr(request, "institution", None):
        link_filter["institution"] = request.institution

    if not request.user.is_superuser and request.user.role == Role.PARENT:
        is_linked = ParentStudentLink.objects.filter(**link_filter).exists()
        if not is_linked:
            raise PermissionDenied("You are not authorized to access fee records for this student.")

    child = get_object_or_404(User, id=student_id, role=Role.STUDENT)

    allocations = (
        StudentFeeAllocation.objects.filter(student=child)
        .select_related("fee_structure", "fee_structure__course")
        .prefetch_related("installments", "payments", "adjustments")
        .order_by("-academic_year", "-created_at")
    )
    payments = (
        Payment.objects.filter(student=child)
        .select_related("allocation", "allocation__fee_structure")
        .order_by("-payment_date", "-created_at")
    )

    if getattr(request, "institution", None):
        allocations = allocations.filter(institution=request.institution)
        payments = payments.filter(institution=request.institution)

    total_net = sum(a.net_amount for a in allocations)
    total_paid = sum(a.amount_paid for a in allocations)
    total_outstanding = sum(a.outstanding_balance for a in allocations)

    context = {
        "child": child,
        "allocations": allocations,
        "total_net": total_net,
        "total_paid": total_paid,
        "total_outstanding": total_outstanding,
        "payments": payments,
    }
    return render(request, "fees/parent/child_fees.html", context)


@login_required
def download_receipt_pdf(request, receipt_id):
    """
    Downloads an official PDF receipt for a verified payment.
    Protected by role & ownership check:
    - Student who made the payment
    - Authorized Parent of the student
    - Accounts staff / Admin
    """
    receipt = get_object_or_404(FeeReceipt, id=receipt_id)
    payment = receipt.payment
    student = payment.student

    inst = getattr(request, "institution", None)
    if inst and payment.institution and payment.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("You do not have access to receipts from another institution.")

    is_owner = (request.user == student)
    is_staff = (request.user.role in [Role.ACCOUNTS, Role.ADMIN] or request.user.is_superuser)
    is_authorized_parent = False

    if request.user.role == Role.PARENT:
        link_q = {"parent": request.user, "student": student, "is_authorized": True}
        if inst:
            link_q["institution"] = inst
        is_authorized_parent = ParentStudentLink.objects.filter(**link_q).exists()

    if not (is_owner or is_staff or is_authorized_parent):
        raise PermissionDenied("You are not authorized to view or download this payment receipt.")

    pdf_bytes = generate_fee_receipt_pdf(receipt)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="Receipt_{receipt.receipt_number}.pdf"'
    return response


# ==============================================================================
# ACCOUNTS STAFF & ADMIN VIEWS
# ==============================================================================

@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def accounts_fees_dashboard(request):
    """
    Primary workspace dashboard for Accounts Staff & Administration.
    Displays institutional billing metrics, recent transactions, pending verifications,
    and overdue ledgers.
    """
    inst = getattr(request, "institution", None)
    allocations = StudentFeeAllocation.objects.filter(institution=inst) if inst else StudentFeeAllocation.objects.all()

    total_gross = allocations.aggregate(val=Sum("gross_amount"))["val"] or Decimal("0.00")
    total_concessions = allocations.aggregate(val=Sum("discount_amount"))["val"] or Decimal("0.00")
    total_net = allocations.aggregate(val=Sum("net_amount"))["val"] or Decimal("0.00")
    total_collected = allocations.aggregate(val=Sum("amount_paid"))["val"] or Decimal("0.00")
    total_outstanding = allocations.aggregate(val=Sum("outstanding_balance"))["val"] or Decimal("0.00")

    overdue_count = allocations.filter(status=AllocationStatus.OVERDUE).count()
    payment_qs = Payment.objects.filter(institution=inst) if inst else Payment.objects.all()
    pending_verification_count = payment_qs.filter(status=PaymentStatus.PENDING).count()

    recent_payments = (
        payment_qs.select_related("student", "allocation", "allocation__fee_structure")
        .order_by("-created_at")[:8]
    )

    overdue_allocations = (
        allocations.filter(status=AllocationStatus.OVERDUE)
        .select_related("student", "fee_structure")
        .order_by("-outstanding_balance")[:8]
    )

    context = {
        "total_gross": total_gross,
        "total_concessions": total_concessions,
        "total_net": total_net,
        "total_collected": total_collected,
        "total_outstanding": total_outstanding,
        "overdue_count": overdue_count,
        "pending_verification_count": pending_verification_count,
        "recent_payments": recent_payments,
        "overdue_allocations": overdue_allocations,
    }
    return render(request, "fees/admin/dashboard.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def fee_structure_list(request):
    """
    List and filter institution fee structures.
    """
    inst = getattr(request, "institution", None)
    structures = FeeStructure.objects.select_related("course").prefetch_related("items").order_by("-created_at")
    categories = FeeCategory.objects.all().order_by("name")
    if inst:
        structures = structures.filter(institution=inst)
        categories = categories.filter(institution=inst)

    query = request.GET.get("q", "").strip()
    if query:
        structures = structures.filter(
            Q(title__icontains=query) | Q(code__icontains=query) | Q(academic_year__icontains=query)
        )

    context = {
        "structures": structures,
        "categories": categories,
        "query": query,
    }
    return render(request, "fees/admin/structure_list.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def fee_structure_create(request):
    """
    Create a new institutional fee structure.
    """
    if request.method == "POST":
        form = FeeStructureForm(request.POST)
        if form.is_valid():
            structure = form.save(commit=False)
            structure.created_by = request.user
            if getattr(request, "institution", None):
                structure.institution = request.institution
            structure.save()
            messages.success(request, f"Fee structure '{structure.title}' created successfully.")
            return redirect("fees:structure_detail", structure_id=structure.id)
    else:
        form = FeeStructureForm()

    return render(request, "fees/admin/structure_form.html", {"form": form, "action": "Create"})


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def fee_structure_detail(request, structure_id):
    """
    View and edit fee structure line items and components.
    """
    structure = get_object_or_404(FeeStructure, id=structure_id)
    inst = getattr(request, "institution", None)
    if inst and structure.institution and structure.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to fee structure outside your active institution.")

    if request.method == "POST":
        item_form = FeeStructureItemForm(request.POST)
        if item_form.is_valid():
            item = item_form.save(commit=False)
            item.fee_structure = structure
            item.save()
            # Recalculate parent total
            structure.recalculate_total()
            messages.success(request, f"Added component '{item.category.name}' (${item.amount:.2f}).")
            return redirect("fees:structure_detail", structure_id=structure.id)
    else:
        item_form = FeeStructureItemForm()

    items = structure.items.select_related("category").order_by("category__name")
    allocations_count = structure.student_allocations.count()

    context = {
        "structure": structure,
        "items": items,
        "item_form": item_form,
        "allocations_count": allocations_count,
    }
    return render(request, "fees/admin/structure_detail.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def assign_fees_view(request):
    """
    Assigns fee structure to an individual student or course cohort with scheduled installments.
    """
    inst = getattr(request, "institution", None)
    if request.method == "POST":
        form = StudentFeeAssignmentForm(request.POST)
        if form.is_valid():
            target_type = form.cleaned_data["target_type"]
            fee_structure = form.cleaned_data["fee_structure"]
            academic_year = form.cleaned_data["academic_year"]
            discount_amount = form.cleaned_data["discount_amount"] or Decimal("0.00")
            discount_reason = form.cleaned_data["discount_reason"]
            scheme = form.cleaned_data["installment_scheme"]

            students_to_assign = []
            if target_type == "student":
                students_to_assign = [form.cleaned_data["student"]]
            else:
                course = form.cleaned_data["course"]
                # In EduConnect, students admitted or enrolled in this course
                from apps.admissions.models import AdmissionApplication, ApplicationStatus
                enrolled_qs = User.objects.filter(
                    admission_applications__course=course,
                    admission_applications__status=ApplicationStatus.ENROLLED,
                    role=Role.STUDENT,
                )
                if inst:
                    enrolled_qs = enrolled_qs.filter(memberships__institution=inst)
                students_to_assign = list(enrolled_qs.distinct())
                if not students_to_assign:
                    base_students = User.objects.filter(role=Role.STUDENT)
                    if inst:
                        base_students = base_students.filter(memberships__institution=inst)
                    students_to_assign = list(base_students[:20])

            created_count = 0
            for student in students_to_assign:
                # Check if allocation already exists for this academic year and structure
                existing = StudentFeeAllocation.objects.filter(
                    student=student,
                    fee_structure=fee_structure,
                    academic_year=academic_year,
                ).first()

                if existing:
                    continue

                gross = fee_structure.total_amount
                net = max(Decimal("0.00"), gross - discount_amount)

                allocation = StudentFeeAllocation.objects.create(
                    institution=inst or getattr(fee_structure, "institution", None),
                    student=student,
                    fee_structure=fee_structure,
                    academic_year=academic_year,
                    gross_amount=gross,
                    discount_amount=discount_amount,
                    discount_reason=discount_reason,
                    net_amount=net,
                    amount_paid=Decimal("0.00"),
                    outstanding_balance=net,
                    status=AllocationStatus.PENDING,
                    created_by=request.user,
                )

                # Generate Installments based on selected scheme
                today = timezone.now().date()
                if scheme == "single":
                    FeeInstallment.objects.create(
                        allocation=allocation,
                        installment_number=1,
                        title="Full Lump-Sum Fee",
                        amount=net,
                        due_date=today + timezone.timedelta(days=30),
                        status=InstallmentStatus.PENDING,
                    )
                elif scheme == "two_semesters":
                    half = (net / Decimal("2.00")).quantize(Decimal("0.01"))
                    remainder = net - half
                    FeeInstallment.objects.create(
                        allocation=allocation,
                        installment_number=1,
                        title="Semester 1 Installment",
                        amount=half,
                        due_date=today + timezone.timedelta(days=30),
                        status=InstallmentStatus.PENDING,
                    )
                    FeeInstallment.objects.create(
                        allocation=allocation,
                        installment_number=2,
                        title="Semester 2 Installment",
                        amount=remainder,
                        due_date=today + timezone.timedelta(days=150),
                        status=InstallmentStatus.PENDING,
                    )
                elif scheme == "four_quarters":
                    quarter = (net / Decimal("4.00")).quantize(Decimal("0.01"))
                    for i in range(1, 5):
                        amt = quarter if i < 4 else (net - (quarter * 3))
                        FeeInstallment.objects.create(
                            allocation=allocation,
                            installment_number=i,
                            title=f"Quarter {i} Installment",
                            amount=amt,
                            due_date=today + timezone.timedelta(days=30 + (i - 1) * 75),
                            status=InstallmentStatus.PENDING,
                        )

                FeeAuditLog.objects.create(
                    allocation=allocation,
                    action="FEE_ASSIGNED",
                    actor=request.user,
                    details=f"Assigned fee structure '{fee_structure.title}' (Gross: ${gross:.2f}, Net: ${net:.2f}) with scheme '{scheme}'.",
                )
                created_count += 1

            messages.success(request, f"Successfully created fee allocations for {created_count} student(s).")
            return redirect("fees:allocation_list")
    else:
        form = StudentFeeAssignmentForm()

    return render(request, "fees/admin/assign_fees.html", {"form": form})


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def student_allocation_list(request):
    """
    Searchable and filterable master list of all student fee allocations.
    """
    inst = getattr(request, "institution", None)
    allocations = (
        StudentFeeAllocation.objects.select_related("student", "fee_structure", "fee_structure__course")
        .prefetch_related("installments")
        .order_by("-created_at")
    )
    if inst:
        allocations = allocations.filter(institution=inst)

    # Search & filters
    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    year_filter = request.GET.get("year", "").strip()

    if q:
        allocations = allocations.filter(
            Q(student__username__icontains=q)
            | Q(student__first_name__icontains=q)
            | Q(student__last_name__icontains=q)
            | Q(student__student_id__icontains=q)
            | Q(fee_structure__title__icontains=q)
        )
    if status_filter:
        allocations = allocations.filter(status=status_filter)
    if year_filter:
        allocations = allocations.filter(academic_year=year_filter)

    paginator = Paginator(allocations, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "page_obj": page_obj,
        "q": q,
        "status_filter": status_filter,
        "year_filter": year_filter,
        "status_choices": AllocationStatus.choices,
    }
    return render(request, "fees/admin/allocation_list.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def student_allocation_detail(request, allocation_id):
    """
    Comprehensive financial ledger for an individual student fee allocation.
    Shows structure breakdown, installment status, verified payments, receipts,
    adjustments, and immutable audit logs.
    """
    allocation = get_object_or_404(
        StudentFeeAllocation.objects.select_related("student", "fee_structure", "fee_structure__course"),
        id=allocation_id,
    )
    inst = getattr(request, "institution", None)
    if inst and allocation.institution and allocation.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to allocation outside your active institution.")

    installments = allocation.installments.order_by("installment_number")
    payments = allocation.payments.select_related("recorded_by", "verified_by").order_by("-payment_date", "-created_at")
    adjustments = allocation.adjustments.select_related("authorized_by").order_by("-created_at")
    audit_logs = allocation.audit_logs.select_related("actor").order_by("-timestamp")[:25]

    context = {
        "allocation": allocation,
        "installments": installments,
        "payments": payments,
        "adjustments": adjustments,
        "audit_logs": audit_logs,
    }
    return render(request, "fees/admin/allocation_detail.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def record_offline_payment_view(request, allocation_id):
    """
    Record an authorized offline payment (Cash, Bank Wire, Cheque, Demand Draft, POS).
    Guarantees:
    - Precise decimal amounts
    - Duplicate prevention & idempotency guard
    - Automatic receipt generation
    - Atomic balance recalculation
    """
    allocation = get_object_or_404(
        StudentFeeAllocation.objects.select_related("student", "fee_structure"),
        id=allocation_id,
    )
    inst = getattr(request, "institution", None)
    if inst and allocation.institution and allocation.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to allocation outside your active institution.")

    if request.method == "POST":
        form = OfflinePaymentForm(allocation, request.POST)
        if form.is_valid():
            installment = None
            inst_id = form.cleaned_data.get("installment_id")
            if inst_id:
                installment = FeeInstallment.objects.filter(id=inst_id, allocation=allocation).first()

            try:
                payment, receipt = record_payment_transaction(
                    allocation=allocation,
                    amount=form.cleaned_data["amount"],
                    payment_method=form.cleaned_data["payment_method"],
                    transaction_reference=form.cleaned_data["transaction_reference"],
                    payer_name=form.cleaned_data["payer_name"],
                    payer_relationship=form.cleaned_data["payer_relationship"],
                    actor=request.user,
                    installment=installment,
                    notes=form.cleaned_data["notes"],
                    auto_verify=True,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
                messages.success(
                    request,
                    f"Payment of ${payment.amount:.2f} recorded successfully! Official Receipt #{receipt.receipt_number} issued.",
                )
                return redirect("fees:allocation_detail", allocation_id=allocation.id)
            except ValidationError as e:
                messages.error(request, f"Payment error: {e.message if hasattr(e, 'message') else e}")
    else:
        default_payer = allocation.student.get_full_name() or allocation.student.username
        form = OfflinePaymentForm(
            allocation,
            initial={
                "amount": allocation.outstanding_balance,
                "payer_name": default_payer,
            },
        )

    context = {
        "allocation": allocation,
        "form": form,
    }
    return render(request, "fees/admin/record_payment.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def payment_list_view(request):
    """
    Searchable and filterable master transaction ledger.
    """
    inst = getattr(request, "institution", None)
    payments = (
        Payment.objects.select_related("student", "allocation", "allocation__fee_structure")
        .order_by("-payment_date", "-created_at")
    )
    if inst:
        payments = payments.filter(institution=inst)

    q = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    method_filter = request.GET.get("method", "").strip()

    if q:
        payments = payments.filter(
            Q(transaction_reference__icontains=q)
            | Q(student__username__icontains=q)
            | Q(student__first_name__icontains=q)
            | Q(student__last_name__icontains=q)
            | Q(payer_name__icontains=q)
        )
    if status_filter:
        payments = payments.filter(status=status_filter)
    if method_filter:
        payments = payments.filter(payment_method=method_filter)

    paginator = Paginator(payments, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "q": q,
        "status_filter": status_filter,
        "method_filter": method_filter,
        "status_choices": PaymentStatus.choices,
        "method_choices": PaymentMethod.choices,
    }
    return render(request, "fees/admin/payment_list.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def verify_payment_view(request, payment_id):
    """
    Verify or reject a pending payment submission.
    """
    payment = get_object_or_404(Payment.objects.select_related("student", "allocation"), id=payment_id)
    inst = getattr(request, "institution", None)
    if inst and payment.institution and payment.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to payment outside your active institution.")

    if payment.status != PaymentStatus.PENDING:
        messages.info(request, f"This payment is already in status '{payment.get_status_display()}'.")
        return redirect("fees:allocation_detail", allocation_id=payment.allocation.id)

    if request.method == "POST":
        form = PaymentVerificationForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data["decision"]
            notes = form.cleaned_data["notes"]
            new_status = PaymentStatus.VERIFIED if decision == "verify" else PaymentStatus.REJECTED

            try:
                transition_payment_status(
                    payment=payment,
                    new_status=new_status,
                    actor=request.user,
                    verification_notes=notes,
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
                messages.success(request, f"Payment transitioned to '{new_status}'. Balance updated.")
                return redirect("fees:allocation_detail", allocation_id=payment.allocation.id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = PaymentVerificationForm()

    context = {
        "payment": payment,
        "form": form,
    }
    return render(request, "fees/admin/verify_payment.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def apply_fee_adjustment_view(request, allocation_id):
    """
    Applies an authorized accounting adjustment (Waiver, Scholarship, Penalty, Mistake Correction, Refund).
    Requires audit explanation and recalculates net and outstanding dues.
    """
    allocation = get_object_or_404(StudentFeeAllocation.objects.select_related("student"), id=allocation_id)
    inst = getattr(request, "institution", None)
    if inst and allocation.institution and allocation.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to allocation outside your active institution.")

    if request.method == "POST":
        form = FeeAdjustmentForm(request.POST)
        if form.is_valid():
            try:
                adj = apply_fee_adjustment(
                    allocation=allocation,
                    adjustment_type=form.cleaned_data["adjustment_type"],
                    amount=form.cleaned_data["amount"],
                    reason=form.cleaned_data["reason"],
                    actor=request.user,
                    reference_document=form.cleaned_data["reference_document"],
                    ip_address=request.META.get("REMOTE_ADDR"),
                )
                messages.success(
                    request,
                    f"Adjustment '{adj.get_adjustment_type_display()}' of ${adj.amount:.2f} applied successfully. Dues recalculated.",
                )
                return redirect("fees:allocation_detail", allocation_id=allocation.id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = FeeAdjustmentForm()

    context = {
        "allocation": allocation,
        "form": form,
    }
    return render(request, "fees/admin/apply_adjustment.html", context)


@login_required
@role_required(Role.ACCOUNTS, Role.ADMIN)
def overdue_accounts_report(request):
    """
    Report of overdue student accounts and unpaid installments.
    """
    inst = getattr(request, "institution", None)
    overdue_allocations = (
        StudentFeeAllocation.objects.filter(status=AllocationStatus.OVERDUE)
        .select_related("student", "fee_structure")
        .prefetch_related("installments")
        .order_by("-outstanding_balance")
    )
    if inst:
        overdue_allocations = overdue_allocations.filter(institution=inst)

    total_overdue_amount = overdue_allocations.aggregate(val=Sum("outstanding_balance"))["val"] or Decimal("0.00")

    context = {
        "overdue_allocations": overdue_allocations,
        "total_overdue_amount": total_overdue_amount,
        "count": overdue_allocations.count(),
    }
    return render(request, "fees/admin/overdue_report.html", context)

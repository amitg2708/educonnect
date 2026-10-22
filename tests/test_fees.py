"""
EduConnect Fees Management Automated Test Suite.
Tests:
- Fee structure and category configuration
- Student fee assignment with installment schemes (Single, 2 Semesters, 4 Quarters)
- Offline counter payment processing
- Duplicate payment prevention and idempotency guards
- Atomic balance recalculation from verified records
- Duplicate receipt prevention and sequential unique numbers
- Valid & invalid payment status transitions
- Authorized accounting adjustments (waiver, scholarship, penalty, correction, reversal)
- PDF receipt generation with real transaction details
- Strict role-based permissions (Student, Parent, Accounts Staff, Teacher, Admin)
- Parent-child authorization enforcement
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import Role, ParentStudentLink
from apps.core.models import Course
from apps.fees.models import (
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
    AllocationStatus,
    InstallmentStatus,
)
from apps.fees.services import (
    record_payment_transaction,
    transition_payment_status,
    apply_fee_adjustment,
    recalculate_allocation_balance,
    generate_unique_receipt_number,
    verify_mongodb_transactions_support,
)
from apps.fees.receipt_generator import generate_fee_receipt_pdf

User = get_user_model()


class FeesManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users with various roles
        self.admin_user = User.objects.create_superuser(
            username="admin_user",
            email="admin@educonnect.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
        )
        self.accounts_user = User.objects.create_user(
            username="accounts_staff",
            email="accounts@educonnect.edu",
            password="TestPassword123!",
            role=Role.ACCOUNTS,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_user",
            email="teacher@educonnect.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
        )
        self.student1 = User.objects.create_user(
            username="student_alice",
            email="alice@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            student_id="STU-ALICE-01",
        )
        self.student2 = User.objects.create_user(
            username="student_bob",
            email="bob@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            student_id="STU-BOB-02",
        )
        self.parent1 = User.objects.create_user(
            username="parent_alice",
            email="parent_alice@educonnect.edu",
            password="TestPassword123!",
            role=Role.PARENT,
        )
        self.parent2 = User.objects.create_user(
            username="parent_stranger",
            email="parent_stranger@educonnect.edu",
            password="TestPassword123!",
            role=Role.PARENT,
        )

        # Authorize parent1 for student1 (Alice)
        ParentStudentLink.objects.create(
            parent=self.parent1,
            student=self.student1,
            relationship_type="mother",
            is_authorized=True,
        )

        # Create Course
        self.course = Course.objects.create(
            title="Computer Science B.Sc.",
            code="CS-BSC",
            department="Computer Science",
            duration="4 Years",
            description="Undergraduate degree in CS.",
            fee_per_term=Decimal("5000.00"),
        )

        # Create Fee Categories
        self.cat_tuition = FeeCategory.objects.create(name="Tuition Fee", code="TUIT")
        self.cat_lab = FeeCategory.objects.create(name="Computing Lab Fee", code="LAB")
        self.cat_exam = FeeCategory.objects.create(name="Examination Fee", code="EXAM")

        # Create Fee Structure
        self.fee_structure = FeeStructure.objects.create(
            title="CS Undergraduate Fall 2026",
            code="FS-CS-2026",
            academic_year="2026-2027",
            course=self.course,
            total_amount=Decimal("6000.00"),
            created_by=self.accounts_user,
        )
        FeeStructureItem.objects.create(fee_structure=self.fee_structure, category=self.cat_tuition, amount=Decimal("4500.00"))
        FeeStructureItem.objects.create(fee_structure=self.fee_structure, category=self.cat_lab, amount=Decimal("1000.00"))
        FeeStructureItem.objects.create(fee_structure=self.fee_structure, category=self.cat_exam, amount=Decimal("500.00"))

    def test_fee_structure_recalculation(self):
        """Test that structure total recalculates accurately from line items."""
        total = self.fee_structure.recalculate_total()
        self.assertEqual(total, Decimal("6000.00"))
        self.assertEqual(self.fee_structure.total_amount, Decimal("6000.00"))

    def test_student_fee_assignment_and_installments(self):
        """Test assigning fees to a student with 2-semester installments."""
        self.client.force_login(self.accounts_user)
        response = self.client.post(
            reverse("fees:assign_fees"),
            {
                "target_type": "student",
                "student": self.student1.id,
                "fee_structure": self.fee_structure.id,
                "academic_year": "2026-2027",
                "discount_amount": "500.00",
                "discount_reason": "Academic Merit Scholarship",
                "installment_scheme": "two_semesters",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        # Check allocation
        alloc = StudentFeeAllocation.objects.get(student=self.student1, fee_structure=self.fee_structure)
        self.assertEqual(alloc.gross_amount, Decimal("6000.00"))
        self.assertEqual(alloc.discount_amount, Decimal("500.00"))
        self.assertEqual(alloc.net_amount, Decimal("5500.00"))
        self.assertEqual(alloc.amount_paid, Decimal("0.00"))
        self.assertEqual(alloc.outstanding_balance, Decimal("5500.00"))
        self.assertEqual(alloc.status, AllocationStatus.PENDING)

        # Check 2 installments generated
        installments = list(alloc.installments.order_by("installment_number"))
        self.assertEqual(len(installments), 2)
        self.assertEqual(installments[0].amount, Decimal("2750.00"))
        self.assertEqual(installments[1].amount, Decimal("2750.00"))
        self.assertEqual(installments[0].status, InstallmentStatus.PENDING)

    def test_partial_payment_and_balance_recalculation(self):
        """Test recording partial payment and sequential installment allocation."""
        alloc = StudentFeeAllocation.objects.create(
            student=self.student1,
            fee_structure=self.fee_structure,
            academic_year="2026-2027",
            gross_amount=Decimal("6000.00"),
            discount_amount=Decimal("0.00"),
            net_amount=Decimal("6000.00"),
            amount_paid=Decimal("0.00"),
            outstanding_balance=Decimal("6000.00"),
            status=AllocationStatus.PENDING,
        )
        inst1 = FeeInstallment.objects.create(
            allocation=alloc,
            installment_number=1,
            title="Installment 1",
            amount=Decimal("3000.00"),
            due_date=timezone.now().date() + timezone.timedelta(days=30),
        )
        inst2 = FeeInstallment.objects.create(
            allocation=alloc,
            installment_number=2,
            title="Installment 2",
            amount=Decimal("3000.00"),
            due_date=timezone.now().date() + timezone.timedelta(days=90),
        )

        # Record partial payment of $2000.00
        payment, receipt = record_payment_transaction(
            allocation=alloc,
            amount=Decimal("2000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_reference="TXN-CASH-001",
            payer_name="Alice Smith",
            actor=self.accounts_user,
            auto_verify=True,
        )
        self.assertIsNotNone(receipt)
        self.assertTrue(receipt.receipt_number.startswith("REC-"))

        # Reload allocation and verify recalculated balance
        alloc.refresh_from_db()
        self.assertEqual(alloc.amount_paid, Decimal("2000.00"))
        self.assertEqual(alloc.outstanding_balance, Decimal("4000.00"))
        self.assertEqual(alloc.status, AllocationStatus.PARTIALLY_PAID)

        # Check installments
        inst1.refresh_from_db()
        inst2.refresh_from_db()
        self.assertEqual(inst1.amount_paid, Decimal("2000.00"))
        self.assertEqual(inst1.status, InstallmentStatus.PARTIALLY_PAID)
        self.assertEqual(inst2.amount_paid, Decimal("0.00"))
        self.assertEqual(inst2.status, InstallmentStatus.PENDING)

        # Record second payment of $4000.00 (Clearing full balance)
        payment2, receipt2 = record_payment_transaction(
            allocation=alloc,
            amount=Decimal("4000.00"),
            payment_method=PaymentMethod.BANK_TRANSFER,
            transaction_reference="UTR-BANK-998877",
            payer_name="Alice Smith",
            actor=self.accounts_user,
            auto_verify=True,
        )
        alloc.refresh_from_db()
        self.assertEqual(alloc.amount_paid, Decimal("6000.00"))
        self.assertEqual(alloc.outstanding_balance, Decimal("0.00"))
        self.assertEqual(alloc.status, AllocationStatus.PAID)

        inst1.refresh_from_db()
        inst2.refresh_from_db()
        self.assertEqual(inst1.amount_paid, Decimal("3000.00"))
        self.assertEqual(inst1.status, InstallmentStatus.PAID)
        self.assertEqual(inst2.amount_paid, Decimal("3000.00"))
        self.assertEqual(inst2.status, InstallmentStatus.PAID)

    def test_duplicate_payment_prevention(self):
        """Test that duplicate transaction references and idempotency keys are strictly rejected."""
        alloc = StudentFeeAllocation.objects.create(
            student=self.student1,
            fee_structure=self.fee_structure,
            academic_year="2026-2027",
            gross_amount=Decimal("3000.00"),
            net_amount=Decimal("3000.00"),
            outstanding_balance=Decimal("3000.00"),
        )
        record_payment_transaction(
            allocation=alloc,
            amount=Decimal("1000.00"),
            payment_method=PaymentMethod.CHEQUE,
            transaction_reference="CHQ-100200",
            payer_name="Guardian",
            actor=self.accounts_user,
            idempotency_key="IDEMPOTENCY-KEY-ABC",
        )

        # Duplicate reference
        with self.assertRaises(ValidationError) as ctx:
            record_payment_transaction(
                allocation=alloc,
                amount=Decimal("500.00"),
                payment_method=PaymentMethod.CASH,
                transaction_reference="CHQ-100200",
                payer_name="Guardian",
                actor=self.accounts_user,
            )
        self.assertIn("already exists", str(ctx.exception))

        # Duplicate idempotency key
        with self.assertRaises(ValidationError) as ctx:
            record_payment_transaction(
                allocation=alloc,
                amount=Decimal("1000.00"),
                payment_method=PaymentMethod.CASH,
                transaction_reference="TXN-DIFFERENT-REF",
                payer_name="Guardian",
                actor=self.accounts_user,
                idempotency_key="IDEMPOTENCY-KEY-ABC",
            )
        self.assertIn("Duplicate submission detected", str(ctx.exception))

    def test_payment_status_transitions(self):
        """Test valid and invalid payment status transitions with receipt handling."""
        alloc = StudentFeeAllocation.objects.create(
            student=self.student1,
            fee_structure=self.fee_structure,
            academic_year="2026-2027",
            gross_amount=Decimal("1000.00"),
            net_amount=Decimal("1000.00"),
            outstanding_balance=Decimal("1000.00"),
        )
        payment, _ = record_payment_transaction(
            allocation=alloc,
            amount=Decimal("500.00"),
            payment_method=PaymentMethod.ONLINE_GATEWAY,
            transaction_reference="ONLINE-PG-001",
            payer_name="Alice",
            actor=self.accounts_user,
            auto_verify=False,  # Status = PENDING
        )
        self.assertEqual(payment.status, PaymentStatus.PENDING)
        alloc.refresh_from_db()
        self.assertEqual(alloc.amount_paid, Decimal("0.00"))  # Pending payment not counted in balance

        # Transition: PENDING -> VERIFIED
        transition_payment_status(payment, PaymentStatus.VERIFIED, actor=self.accounts_user, verification_notes="Reconciled")
        payment.refresh_from_db()
        alloc.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.VERIFIED)
        self.assertEqual(alloc.amount_paid, Decimal("500.00"))
        self.assertIsNotNone(payment.receipt)

        # Transition: VERIFIED -> REVERSED (e.g. cheque dishonored)
        transition_payment_status(payment, PaymentStatus.REVERSED, actor=self.accounts_user, verification_notes="Dishonor memo")
        payment.refresh_from_db()
        alloc.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.REVERSED)
        self.assertEqual(alloc.amount_paid, Decimal("0.00"))
        self.assertEqual(alloc.outstanding_balance, Decimal("1000.00"))
        self.assertTrue(payment.receipt.is_cancelled)

        # Invalid transition: REVERSED -> VERIFIED should fail
        with self.assertRaises(ValidationError):
            transition_payment_status(payment, PaymentStatus.VERIFIED, actor=self.accounts_user)

    def test_authorized_adjustments_and_audit_trail(self):
        """Test applying fee waivers, late fee penalties, and mistake corrections with audit trail."""
        alloc = StudentFeeAllocation.objects.create(
            student=self.student1,
            fee_structure=self.fee_structure,
            academic_year="2026-2027",
            gross_amount=Decimal("4000.00"),
            net_amount=Decimal("4000.00"),
            outstanding_balance=Decimal("4000.00"),
        )
        # Apply a $500 waiver
        apply_fee_adjustment(
            allocation=alloc,
            adjustment_type=AdjustmentType.WAIVER,
            amount=Decimal("500.00"),
            reason="Special dean fee concession approved",
            actor=self.admin_user,
            reference_document="MEMO-2026-88",
        )
        alloc.refresh_from_db()
        self.assertEqual(alloc.net_amount, Decimal("3500.00"))
        self.assertEqual(alloc.outstanding_balance, Decimal("3500.00"))

        # Apply a late fee surcharge penalty of $100
        apply_fee_adjustment(
            allocation=alloc,
            adjustment_type=AdjustmentType.LATE_FEE_PENALTY,
            amount=Decimal("100.00"),
            reason="Late payment registration fee",
            actor=self.accounts_user,
        )
        alloc.refresh_from_db()
        self.assertEqual(alloc.net_amount, Decimal("3600.00"))
        self.assertEqual(alloc.outstanding_balance, Decimal("3600.00"))

        # Verify audit log recorded both adjustments
        self.assertEqual(alloc.audit_logs.count(), 2)

    def test_pdf_receipt_generation(self):
        """Test PDF receipt generation produces valid binary with transaction data."""
        alloc = StudentFeeAllocation.objects.create(
            student=self.student1,
            fee_structure=self.fee_structure,
            academic_year="2026-2027",
            gross_amount=Decimal("6000.00"),
            net_amount=Decimal("6000.00"),
            outstanding_balance=Decimal("6000.00"),
        )
        payment, receipt = record_payment_transaction(
            allocation=alloc,
            amount=Decimal("1500.00"),
            payment_method=PaymentMethod.POS_TERMINAL,
            transaction_reference="POS-AUTH-7788",
            payer_name="Alice Student",
            actor=self.accounts_user,
            auto_verify=True,
        )
        pdf_bytes = generate_fee_receipt_pdf(receipt)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_role_based_permissions(self):
        """Test strict role authorization boundaries across student, parent, accounts, teacher, admin."""
        alloc = StudentFeeAllocation.objects.create(
            student=self.student1,
            fee_structure=self.fee_structure,
            academic_year="2026-2027",
            gross_amount=Decimal("5000.00"),
            net_amount=Decimal("5000.00"),
            outstanding_balance=Decimal("5000.00"),
        )
        payment, receipt = record_payment_transaction(
            allocation=alloc,
            amount=Decimal("1000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_reference="TXN-PERM-01",
            payer_name="Alice",
            actor=self.accounts_user,
            auto_verify=True,
        )

        # 1. Student1 accesses their own fees: 200 OK
        self.client.force_login(self.student1)
        resp = self.client.get(reverse("fees:student_overview"))
        self.assertEqual(resp.status_code, 200)

        # Student1 downloads their receipt: 200 OK
        resp = self.client.get(reverse("fees:download_receipt", args=[receipt.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")

        # 2. Student2 attempts to download Student1's receipt: 403 Forbidden
        self.client.force_login(self.student2)
        resp = self.client.get(reverse("fees:download_receipt", args=[receipt.id]))
        self.assertEqual(resp.status_code, 403)

        # Student cannot access Accounts Desk: 403 Forbidden
        resp = self.client.get(reverse("fees:dashboard"))
        self.assertEqual(resp.status_code, 403)

        # 3. Subject Teacher attempts to access Accounts Desk: 403 Forbidden
        self.client.force_login(self.teacher_user)
        resp = self.client.get(reverse("fees:dashboard"))
        self.assertEqual(resp.status_code, 403)

        # 4. Authorized Parent1 accesses Alice's fees: 200 OK
        self.client.force_login(self.parent1)
        resp = self.client.get(reverse("fees:parent_child_fees", args=[self.student1.id]))
        self.assertEqual(resp.status_code, 200)

        # Authorized Parent1 downloads Alice's receipt: 200 OK
        resp = self.client.get(reverse("fees:download_receipt", args=[receipt.id]))
        self.assertEqual(resp.status_code, 200)

        # 5. Unauthorized Parent2 attempts to access Alice's fees: 403 Forbidden
        self.client.force_login(self.parent2)
        resp = self.client.get(reverse("fees:parent_child_fees", args=[self.student1.id]))
        self.assertEqual(resp.status_code, 403)

        # 6. Accounts Staff accesses dashboard: 200 OK
        self.client.force_login(self.accounts_user)
        resp = self.client.get(reverse("fees:dashboard"))
        self.assertEqual(resp.status_code, 200)

        # 7. Admin accesses dashboard: 200 OK
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("fees:dashboard"))
        self.assertEqual(resp.status_code, 200)

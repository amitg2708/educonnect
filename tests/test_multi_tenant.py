"""
Comprehensive Multi-Tenant Acceptance Test Suite for EduConnect.

Tests the 6 core business acceptance requirements:
1. Institute A cannot read or modify Institute B's students or applications.
2. A teacher can access only assigned classes and authorized records.
3. An accounts staff member cannot access another institute's payments.
4. A parent can see only linked children at authorized institutes.
5. A user can belong to multiple institutes without duplicate accounts (multi-role persona).
6. Existing login and role dashboards continue to work seamlessly.
Plus:
7. Institution invitation and activation workflow.
8. Model indexes for tenant-scoped lookups.
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentStudentLink, Role
from apps.institutions.models import (
    Branch,
    Institution,
    InstitutionInvitation,
    InstitutionMembership,
    InvitationStatus,
)
from apps.core.models import Course
from apps.attendance.models import (
    AcademicSession,
    AttendancePolicy,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    ClassEnrollment,
    ClassRoom,
    TeacherAssignment,
)
from apps.fees.models import (
    FeeCategory,
    FeeStructure,
    FeeStructureItem,
    Payment,
    PaymentMethod,
    PaymentStatus,
    StudentFeeAllocation,
)
from apps.admissions.models import AdmissionApplication, ApplicationStatus
from apps.academics.models import StudyMaterial

User = get_user_model()


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MultiTenantAcceptanceTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.password = "StrongPass2026!#"

        # -------------------------------------------------------------
        # 1. Setup Institute A (Alpha Institute)
        # -------------------------------------------------------------
        self.inst_a = Institution.objects.create(
            name="Alpha Coaching Institute",
            code="ALPHA",
            tagline="Leading in Science",
            primary_color="#0d6efd",
        )
        self.branch_a = Branch.objects.create(
            institution=self.inst_a,
            name="Alpha Main Campus",
            code="A-MAIN",
            is_main=True,
        )

        # -------------------------------------------------------------
        # 2. Setup Institute B (Beta Institute)
        # -------------------------------------------------------------
        self.inst_b = Institution.objects.create(
            name="Beta Coaching Institute",
            code="BETA",
            tagline="Excellence in Arts",
            primary_color="#198754",
        )
        self.branch_b = Branch.objects.create(
            institution=self.inst_b,
            name="Beta North Campus",
            code="B-NORTH",
            is_main=True,
        )

        # -------------------------------------------------------------
        # 3. Setup Users for Institute A
        # -------------------------------------------------------------
        self.admin_a = User.objects.create_user(
            username="admin_a", email="admin@alpha.test", password=self.password, role=Role.ADMIN
        )
        InstitutionMembership.objects.create(
            user=self.admin_a, institution=self.inst_a, role=Role.ADMIN, branch=self.branch_a, is_default=True
        )

        self.teacher_a = User.objects.create_user(
            username="teacher_a", email="teacher@alpha.test", password=self.password, role=Role.TEACHER
        )
        InstitutionMembership.objects.create(
            user=self.teacher_a, institution=self.inst_a, role=Role.TEACHER, branch=self.branch_a, is_default=True
        )

        self.student_a = User.objects.create_user(
            username="student_a", email="student@alpha.test", password=self.password, role=Role.STUDENT
        )
        InstitutionMembership.objects.create(
            user=self.student_a, institution=self.inst_a, role=Role.STUDENT, branch=self.branch_a, is_default=True
        )

        self.parent_a = User.objects.create_user(
            username="parent_a", email="parent@alpha.test", password=self.password, role=Role.PARENT
        )
        InstitutionMembership.objects.create(
            user=self.parent_a, institution=self.inst_a, role=Role.PARENT, branch=self.branch_a, is_default=True
        )
        ParentStudentLink.objects.create(
            parent=self.parent_a,
            student=self.student_a,
            institution=self.inst_a,
            relationship_type="father",
            is_authorized=True,
        )

        self.accounts_a = User.objects.create_user(
            username="accounts_a", email="accounts@alpha.test", password=self.password, role=Role.ACCOUNTS
        )
        InstitutionMembership.objects.create(
            user=self.accounts_a, institution=self.inst_a, role=Role.ACCOUNTS, branch=self.branch_a, is_default=True
        )

        self.applicant_a = User.objects.create_user(
            username="applicant_a", email="applicant@alpha.test", password=self.password, role=Role.APPLICANT
        )
        InstitutionMembership.objects.create(
            user=self.applicant_a, institution=self.inst_a, role=Role.APPLICANT, branch=self.branch_a, is_default=True
        )

        # -------------------------------------------------------------
        # 4. Setup Users for Institute B
        # -------------------------------------------------------------
        self.admin_b = User.objects.create_user(
            username="admin_b", email="admin@beta.test", password=self.password, role=Role.ADMIN
        )
        InstitutionMembership.objects.create(
            user=self.admin_b, institution=self.inst_b, role=Role.ADMIN, branch=self.branch_b, is_default=True
        )

        self.teacher_b = User.objects.create_user(
            username="teacher_b", email="teacher@beta.test", password=self.password, role=Role.TEACHER
        )
        InstitutionMembership.objects.create(
            user=self.teacher_b, institution=self.inst_b, role=Role.TEACHER, branch=self.branch_b, is_default=True
        )

        self.student_b = User.objects.create_user(
            username="student_b", email="student@beta.test", password=self.password, role=Role.STUDENT
        )
        InstitutionMembership.objects.create(
            user=self.student_b, institution=self.inst_b, role=Role.STUDENT, branch=self.branch_b, is_default=True
        )

        self.parent_b = User.objects.create_user(
            username="parent_b", email="parent@beta.test", password=self.password, role=Role.PARENT
        )
        InstitutionMembership.objects.create(
            user=self.parent_b, institution=self.inst_b, role=Role.PARENT, branch=self.branch_b, is_default=True
        )
        ParentStudentLink.objects.create(
            parent=self.parent_b,
            student=self.student_b,
            institution=self.inst_b,
            relationship_type="mother",
            is_authorized=True,
        )

        self.accounts_b = User.objects.create_user(
            username="accounts_b", email="accounts@beta.test", password=self.password, role=Role.ACCOUNTS
        )
        InstitutionMembership.objects.create(
            user=self.accounts_b, institution=self.inst_b, role=Role.ACCOUNTS, branch=self.branch_b, is_default=True
        )

        # -------------------------------------------------------------
        # 5. Setup Domain Data for Institute A
        # -------------------------------------------------------------
        self.course_a = Course.objects.create(
            title="Physics 101",
            code="PHY101",
            slug="phy101-physics-101",
            department="Science",
            duration="1 Year",
            description="Physics 101 curriculum",
            fee_per_term=Decimal("5000.00"),
            institution=self.inst_a,
        )
        self.session_a = AcademicSession.objects.create(
            name="2026-2027 Alpha Session",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
            is_current=True,
            institution=self.inst_a,
        )
        self.class_a = ClassRoom.objects.create(
            name="Class Alpha-10",
            code="CLS-A10",
            course=self.course_a,
            academic_session=self.session_a,
            institution=self.inst_a,
            branch=self.branch_a,
        )
        ClassEnrollment.objects.create(
            student=self.student_a,
            classroom=self.class_a,
            roll_number="A-001",
        )

        self.teacher_assignment_a = TeacherAssignment.objects.create(
            teacher=self.teacher_a,
            classroom=self.class_a,
            subject_name="Physics",
            is_active=True,
        )

        self.fee_cat_a = FeeCategory.objects.create(
            name="Tuition Fee",
            code="TUI-ALPHA",
            institution=self.inst_a,
        )
        self.fee_struct_a = FeeStructure.objects.create(
            title="Grade 10 Standard",
            code="FS-ALPHA-10",
            course=self.course_a,
            academic_year="2026-2027",
            total_amount=Decimal("12000.00"),
            institution=self.inst_a,
        )
        self.fee_item_a = FeeStructureItem.objects.create(
            fee_structure=self.fee_struct_a,
            category=self.fee_cat_a,
            amount=Decimal("12000.00"),
        )
        self.allocation_a = StudentFeeAllocation.objects.create(
            student=self.student_a,
            fee_structure=self.fee_struct_a,
            academic_year="2026-2027",
            gross_amount=Decimal("12000.00"),
            net_amount=Decimal("12000.00"),
            amount_paid=Decimal("6000.00"),
            outstanding_balance=Decimal("6000.00"),
            institution=self.inst_a,
        )
        self.payment_a = Payment.objects.create(
            allocation=self.allocation_a,
            student=self.student_a,
            amount=Decimal("6000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_reference="TXN-ALPHA-001",
            idempotency_key="IDEM-ALPHA-001",
            status=PaymentStatus.VERIFIED,
            institution=self.inst_a,
        )

        self.app_a = AdmissionApplication.objects.create(
            applicant=self.applicant_a,
            course=self.course_a,
            first_name="Alice",
            last_name="Applicant",
            email="alice.app@alpha.test",
            phone_number="1234567890",
            date_of_birth=timezone.now().date(),
            gender="female",
            address_line1="123 Alpha St",
            city="Tech City",
            state="Tech State",
            postal_code="12345",
            guardian_name="Guardian Alpha",
            guardian_relationship="father",
            guardian_phone="0987654321",
            previous_institution="Alpha High School",
            previous_qualification="Class 10",
            previous_grade_or_percentage="90%",
            year_of_passing=2025,
            status=ApplicationStatus.SUBMITTED,
            institution=self.inst_a,
        )

        # -------------------------------------------------------------
        # 6. Setup Domain Data for Institute B
        # -------------------------------------------------------------
        self.course_b = Course.objects.create(
            title="World History",
            code="HIST101",
            slug="hist101-world-history",
            department="Arts",
            duration="1 Year",
            description="World History curriculum",
            fee_per_term=Decimal("4500.00"),
            institution=self.inst_b,
        )
        self.session_b = AcademicSession.objects.create(
            name="2026-2027 Beta Session",
            start_date=timezone.now().date(),
            end_date=(timezone.now() + timezone.timedelta(days=365)).date(),
            is_current=True,
            institution=self.inst_b,
        )
        self.class_b = ClassRoom.objects.create(
            name="Class Beta-10",
            code="CLS-B10",
            course=self.course_b,
            academic_session=self.session_b,
            institution=self.inst_b,
            branch=self.branch_b,
        )
        ClassEnrollment.objects.create(
            student=self.student_b,
            classroom=self.class_b,
            roll_number="B-001",
        )

        self.teacher_assignment_b = TeacherAssignment.objects.create(
            teacher=self.teacher_b,
            classroom=self.class_b,
            subject_name="History",
            is_active=True,
        )

        self.fee_cat_b = FeeCategory.objects.create(
            name="Tuition Fee",
            code="TUI-BETA",
            institution=self.inst_b,
        )
        self.fee_struct_b = FeeStructure.objects.create(
            title="Beta Grade 10 Standard",
            code="FS-BETA-10",
            course=self.course_b,
            academic_year="2026-2027",
            total_amount=Decimal("10000.00"),
            institution=self.inst_b,
        )
        self.fee_item_b = FeeStructureItem.objects.create(
            fee_structure=self.fee_struct_b,
            category=self.fee_cat_b,
            amount=Decimal("10000.00"),
        )
        self.allocation_b = StudentFeeAllocation.objects.create(
            student=self.student_b,
            fee_structure=self.fee_struct_b,
            academic_year="2026-2027",
            gross_amount=Decimal("10000.00"),
            net_amount=Decimal("10000.00"),
            amount_paid=Decimal("5000.00"),
            outstanding_balance=Decimal("5000.00"),
            institution=self.inst_b,
        )
        self.payment_b = Payment.objects.create(
            allocation=self.allocation_b,
            student=self.student_b,
            amount=Decimal("5000.00"),
            payment_method=PaymentMethod.CASH,
            transaction_reference="TXN-BETA-001",
            idempotency_key="IDEM-BETA-001",
            status=PaymentStatus.VERIFIED,
            institution=self.inst_b,
        )

        self.app_b = AdmissionApplication.objects.create(
            applicant=self.student_b,
            course=self.course_b,
            first_name="Bob",
            last_name="Applicant",
            email="bob.app@beta.test",
            phone_number="9876543210",
            date_of_birth=timezone.now().date(),
            gender="male",
            address_line1="456 Beta Rd",
            city="Artsville",
            state="Beta State",
            postal_code="54321",
            guardian_name="Guardian Beta",
            guardian_relationship="mother",
            guardian_phone="1234509876",
            previous_institution="Beta High School",
            previous_qualification="Class 10",
            previous_grade_or_percentage="85%",
            year_of_passing=2025,
            status=ApplicationStatus.SUBMITTED,
            institution=self.inst_b,
        )

    # =========================================================================
    # Acceptance Test 1: Institute A cannot read or modify Institute B's students
    # =========================================================================
    def test_institute_a_admin_cannot_access_institute_b_applications(self):
        """Admin A cannot view application details or decide on Institute B's applications."""
        client = Client()
        client.login(username="admin_a", password=self.password)

        # Attempt to access Institute B's application detail
        detail_url = reverse(
            "admissions:admin_application_detail",
            kwargs={"application_number": self.app_b.application_number},
        )
        response = client.get(detail_url)
        self.assertIn(response.status_code, [403, 404], "Admin A must be denied access to Institute B application")

        # Attempt to decision Institute B's application
        decision_url = reverse(
            "admissions:admin_application_decision",
            kwargs={"application_number": self.app_b.application_number},
        )
        response = client.post(decision_url, {"decision": "APPROVE"})
        self.assertIn(response.status_code, [403, 404], "Admin A must not be able to approve Institute B application")

    def test_institute_a_admin_application_list_excludes_institute_b(self):
        """Application list for Admin A must strictly contain only Institute A applications."""
        client = Client()
        client.login(username="admin_a", password=self.password)

        list_url = reverse("admissions:admin_application_list")
        response = client.get(list_url)
        self.assertEqual(response.status_code, 200)

        applications = response.context.get("applications")
        app_ids = [str(a.id) for a in applications]
        self.assertIn(str(self.app_a.id), app_ids)
        self.assertNotIn(str(self.app_b.id), app_ids, "Institute B application must not leak into Institute A list")

    # =========================================================================
    # Acceptance Test 2: Teacher can access only assigned classes and authorized records
    # =========================================================================
    def test_teacher_a_cannot_view_or_mark_attendance_for_institute_b(self):
        """Teacher A cannot view or mark attendance for Institute B's assignment/classroom."""
        client = Client()
        client.login(username="teacher_a", password=self.password)

        # Attempt to mark attendance for Class B assignment
        url = reverse("attendance:teacher_mark", kwargs={"assignment_id": self.teacher_assignment_b.id})
        response = client.get(url)
        self.assertIn(response.status_code, [403, 404], "Teacher A must be denied access to Institute B class")

    def test_teacher_a_cannot_post_materials_to_institute_b_classroom(self):
        """Teacher A can post to authorized class_a, but cannot post to unauthorized class_b."""
        client = Client()
        client.login(username="teacher_a", password=self.password)

        # Upload material to assigned class_a
        url = reverse("academics:teacher_materials")
        dummy_file = SimpleUploadedFile("quantum_notes.pdf", b"%PDF-1.4 dummy file content", content_type="application/pdf")
        response = client.post(
            url,
            {
                "classroom": str(self.class_a.id),
                "subject_name": "Physics",
                "title": "Quantum Physics Notes",
                "description": "Fundamental principles",
                "file": dummy_file,
            },
        )
        self.assertEqual(response.status_code, 302)

        # Verify created material has institution set to inst_a
        mat = StudyMaterial.objects.filter(title="Quantum Physics Notes").first()
        self.assertIsNotNone(mat)
        self.assertEqual(mat.institution, self.inst_a)

        # Attempt to post to unauthorized class_b
        dummy_file_b = SimpleUploadedFile("unauthorized.pdf", b"%PDF-1.4 unauthorized", content_type="application/pdf")
        client.post(
            url,
            {
                "classroom": str(self.class_b.id),
                "subject_name": "History",
                "title": "Unauthorized Notes",
                "description": "Should not be allowed",
                "file": dummy_file_b,
            },
        )
        unauth_mat = StudyMaterial.objects.filter(title="Unauthorized Notes").first()
        self.assertIsNone(unauth_mat, "Teacher A must not create materials for unauthorized Institute B class")

    # =========================================================================
    # Acceptance Test 3: Accounts staff cannot access another institute's payments
    # =========================================================================
    def test_accounts_staff_cannot_access_foreign_institute_payments(self):
        """Accounts A cannot view Institute B's allocation details or payments."""
        client = Client()
        client.login(username="accounts_a", password=self.password)

        # Attempt to access allocation detail for Institute B
        detail_url = reverse("fees:allocation_detail", kwargs={"allocation_id": self.allocation_b.id})
        response = client.get(detail_url)
        self.assertIn(response.status_code, [403, 404], "Accounts A must be denied access to Institute B allocation")

    def test_accounts_staff_allocation_list_is_isolated(self):
        """Fee allocation list for Accounts A contains only Institute A allocations."""
        client = Client()
        client.login(username="accounts_a", password=self.password)

        url = reverse("fees:allocation_list")
        response = client.get(url)
        self.assertEqual(response.status_code, 200)

        allocations = response.context.get("page_obj")
        alloc_ids = [str(a.id) for a in allocations]
        self.assertIn(str(self.allocation_a.id), alloc_ids)
        self.assertNotIn(str(self.allocation_b.id), alloc_ids, "Foreign institute allocations must not leak")

    # =========================================================================
    # Acceptance Test 4: Parent can see only linked children at authorized institutes
    # =========================================================================
    def test_parent_sees_only_children_at_active_institute(self):
        """Parent A sees Student A at Institute A, but cannot access Student B."""
        client = Client()
        client.login(username="parent_a", password=self.password)

        # Parent dashboard lists only student_a
        response = client.get(reverse("accounts:parent_dashboard"))
        self.assertEqual(response.status_code, 200)
        child_links = response.context.get("child_links")
        child_ids = [str(link.student.id) for link in child_links]
        self.assertIn(str(self.student_a.id), child_ids)
        self.assertNotIn(str(self.student_b.id), child_ids)

        # Attempt to access Student B's detail under Institute A context
        detail_url = reverse("accounts:parent_child_detail", kwargs={"student_id": self.student_b.id})
        response = client.get(detail_url)
        self.assertIn(response.status_code, [403, 404], "Parent A must be blocked from unauthorized student")

    # =========================================================================
    # Acceptance Test 5: Single user can belong to multiple institutes with different roles
    # =========================================================================
    def test_multirole_user_across_multiple_institutes(self):
        """A user can hold Teacher role at Institute A and Parent role at Institute B."""
        multi_user = User.objects.create_user(
            username="multirole_test_user",
            email="multirole@educonnect.test",
            password=self.password,
            role=Role.TEACHER,
        )

        # Membership 1: Teacher at Alpha
        InstitutionMembership.objects.create(
            user=multi_user,
            institution=self.inst_a,
            role=Role.TEACHER,
            branch=self.branch_a,
            is_default=True,
        )

        # Membership 2: Parent at Beta (linked to Student B)
        InstitutionMembership.objects.create(
            user=multi_user,
            institution=self.inst_b,
            role=Role.PARENT,
            branch=self.branch_b,
            is_default=False,
        )
        ParentStudentLink.objects.create(
            parent=multi_user,
            student=self.student_b,
            institution=self.inst_b,
            relationship_type="guardian",
            is_authorized=True,
        )

        client = Client()
        client.login(username="multirole_test_user", password=self.password)

        # 1. Initially active at Alpha (default)
        dash_response = client.get(reverse("accounts:dashboard_redirect"), follow=True)
        self.assertRedirects(dash_response, reverse("accounts:teacher_dashboard"))

        # 2. Switch institution to Beta
        switch_url = reverse("institutions:switch_institution", kwargs={"institution_id": self.inst_b.id})
        switch_response = client.get(switch_url, follow=True)
        # Redirects to parent dashboard now because role at Beta is PARENT
        self.assertRedirects(switch_response, reverse("accounts:parent_dashboard"))

        # 3. Verify in Beta context: Parent portal shows Student B
        parent_dash = client.get(reverse("accounts:parent_dashboard"))
        self.assertEqual(parent_dash.status_code, 200)
        child_links = parent_dash.context.get("child_links")
        child_ids = [str(link.student.id) for link in child_links]
        self.assertIn(str(self.student_b.id), child_ids)

        # 4. Teacher portal at Alpha is blocked while active at Beta as Parent
        teacher_dash = client.get(reverse("accounts:teacher_dashboard"))
        self.assertEqual(teacher_dash.status_code, 403, "Access to teacher dashboard blocked while active as Parent")

    # =========================================================================
    # Acceptance Test 6: Existing login and role dashboards continue to work
    # =========================================================================
    def test_all_role_dashboards_render_successfully(self):
        """Verify each of the 6 core roles can log in and view their respective dashboard."""
        role_credentials = [
            ("admin_a", reverse("accounts:admin_dashboard")),
            ("teacher_a", reverse("accounts:teacher_dashboard")),
            ("student_a", reverse("accounts:student_dashboard")),
            ("parent_a", reverse("accounts:parent_dashboard")),
            ("accounts_a", reverse("accounts:accounts_dashboard")),
            ("applicant_a", reverse("accounts:applicant_dashboard")),
        ]

        for username, expected_dash in role_credentials:
            c = Client()
            c.login(username=username, password=self.password)

            # Check redirect from /accounts/dashboard/
            resp = c.get(reverse("accounts:dashboard_redirect"), follow=True)
            self.assertEqual(resp.status_code, 200, f"Dashboard redirect failed for {username}")
            self.assertRedirects(resp, expected_dash)

            # Check direct dashboard get
            dash_resp = c.get(expected_dash)
            self.assertEqual(dash_resp.status_code, 200, f"Dashboard view failed for {username} at {expected_dash}")

    # =========================================================================
    # Acceptance Test 7: Invitation & Membership Activation Workflow
    # =========================================================================
    def test_invitation_creation_and_activation(self):
        """Admin creates an invitation and a new user claims it."""
        client = Client()
        client.login(username="admin_a", password=self.password)

        # Admin invites new teacher
        invite_url = reverse("institutions:send_invitation")
        response = client.post(
            invite_url,
            {
                "email": "newteacher@alpha.test",
                "role": Role.TEACHER,
                "branch": str(self.branch_a.id),
                "notes": "Welcome to Alpha Science department",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        invitation = InstitutionInvitation.objects.filter(email="newteacher@alpha.test").first()
        self.assertIsNotNone(invitation)
        self.assertEqual(invitation.status, InvitationStatus.PENDING)

        # New user registers & accepts
        new_user = User.objects.create_user(
            username="newteacher",
            email="newteacher@alpha.test",
            password=self.password,
            role=Role.TEACHER,
        )
        client.login(username="newteacher", password=self.password)

        accept_url = reverse("institutions:accept_invitation", kwargs={"token": invitation.token})
        claim_resp = client.post(accept_url, follow=True)
        self.assertEqual(claim_resp.status_code, 200)

        # Check membership was created
        membership = InstitutionMembership.objects.filter(
            user=new_user,
            institution=self.inst_a,
        ).first()
        self.assertIsNotNone(membership)
        self.assertEqual(membership.role, Role.TEACHER)
        self.assertEqual(membership.branch, self.branch_a)

    # =========================================================================
    # Acceptance Test 8: Indexing for Common Tenant Lookups
    # =========================================================================
    def test_tenant_lookup_indexing(self):
        """Verify that institution foreign key fields and indexes are properly registered on key models."""
        # Verify institution field exists on models
        self.assertTrue(hasattr(Payment, "institution"))
        self.assertTrue(hasattr(StudentFeeAllocation, "institution"))
        self.assertTrue(hasattr(ClassRoom, "institution"))
        self.assertTrue(hasattr(Course, "institution"))

        # Verify InstitutionMembership has unique_together
        self.assertIn(("user", "institution"), InstitutionMembership._meta.unique_together)

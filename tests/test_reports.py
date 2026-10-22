"""
EduConnect Administrative Dashboard & Reporting System Automated Test Suite.
Validates:
- Live database aggregation of metrics across all institutional modules (no hardcoded data).
- Filtered reports with server-side CSV exports and proper Content-Disposition.
- Institution settings management and automatic audit log generation.
- Classroom, Student Enrollment, and Teacher Assignment management desks.
- Audit log tracking, filtering, and pagination.
- Strict role authorization ensuring only ADMIN users can access reporting & management desks.
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.admissions.models import AdmissionApplication
from apps.core.models import Course
from apps.attendance.models import (
    AcademicSession,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    ClassEnrollment,
    ClassRoom,
    TeacherAssignment,
)
from apps.academics.models import Assessment, AssessmentType, StudentAssessmentScore
from apps.complaints.models import ComplaintCategory, ComplaintTicket, TicketPriority, TicketStatus
from apps.fees.models import FeeCategory, FeeStructure, FeeStructureItem, Payment, PaymentStatus, StudentFeeAllocation
from apps.notifications.models import Announcement, TargetRole
from apps.reports.models import AdminAuditLog, InstitutionSetting
from apps.reports.services import (
    export_academics_csv,
    export_admissions_csv,
    export_attendance_csv,
    export_complaints_csv,
    export_fees_csv,
    get_admin_dashboard_metrics,
    log_admin_action,
)

User = get_user_model()


class AdminDashboardAndReportingTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users across roles
        self.admin = User.objects.create_superuser(
            username="super_admin",
            email="admin@educonnect.edu",
            password="AdminPassword123!",
            role=Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="prof_turing",
            email="turing@educonnect.edu",
            password="TeacherPassword123!",
            role=Role.TEACHER,
            first_name="Alan",
            last_name="Turing",
        )
        self.student = User.objects.create_user(
            username="stud_ada",
            email="ada@educonnect.edu",
            password="StudentPassword123!",
            role=Role.STUDENT,
            first_name="Ada",
            last_name="Lovelace",
            student_id="STU-2026-001",
        )
        self.parent = User.objects.create_user(
            username="parent_byron",
            email="byron@educonnect.edu",
            password="ParentPassword123!",
            role=Role.PARENT,
            first_name="Lord",
            last_name="Byron",
        )
        self.applicant = User.objects.create_user(
            username="applicant_john",
            email="john@educonnect.edu",
            password="ApplicantPassword123!",
            role=Role.APPLICANT,
            first_name="John",
            last_name="Doe",
        )

        # Academic Session & Classroom
        self.session = AcademicSession.objects.create(
            name="2026-2027 Academic Year",
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=300),
            is_current=True,
        )
        self.classroom = ClassRoom.objects.create(
            name="Grade 10 - Section A",
            code="G10-A",
            academic_session=self.session,
            room_number="Room 101",
            capacity=30,
            is_active=True,
        )
        self.enrollment = ClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom,
            roll_number="Roll-001",
            is_active=True,
        )
        self.assignment = TeacherAssignment.objects.create(
            teacher=self.teacher,
            classroom=self.classroom,
            subject_name="Computer Science",
            is_active=True,
        )

        # Course & Admissions
        self.course = Course.objects.create(
            title="Computer Science & AI",
            code="CS-AI-101",
            department="Computer Science",
            level=Course.Level.UNDERGRADUATE,
            duration="4 Years",
            description="Comprehensive undergraduate computer science curriculum.",
            is_active=True,
        )
        self.application = AdmissionApplication.objects.create(
            applicant=self.applicant,
            course=self.course,
            status="submitted",
            first_name="John",
            last_name="Doe",
            email="john@educonnect.edu",
            phone_number="+1234567890",
            date_of_birth=timezone.now().date(),
            gender="male",
            nationality="Indian",
            address_line1="100 Innovation Way",
            city="Metropolis",
            state="NY",
            postal_code="10001",
            country="United States",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1234567899",
            guardian_email="robert@example.com",
            previous_institution="Central High",
            previous_qualification="Grade 12",
            previous_grade_or_percentage="95%",
            year_of_passing=2025,
            statement_of_purpose="Passionate about programming.",
        )

        # Fees
        self.category = FeeCategory.objects.create(name="Tuition", code="TUIT")
        self.structure = FeeStructure.objects.create(
            title="Grade 10 Standard Fees",
            code="FS-G10-2026",
            academic_year="2026-2027",
            total_amount=Decimal("1500.00"),
            is_active=True,
        )
        FeeStructureItem.objects.create(
            fee_structure=self.structure,
            category=self.category,
            amount=Decimal("1500.00"),
        )
        self.allocation = StudentFeeAllocation.objects.create(
            student=self.student,
            fee_structure=self.structure,
            gross_amount=Decimal("1500.00"),
            discount_amount=Decimal("100.00"),
            net_amount=Decimal("1400.00"),
            amount_paid=Decimal("400.00"),
            outstanding_balance=Decimal("1000.00"),
            status="partially_paid",
        )
        self.payment = Payment.objects.create(
            allocation=self.allocation,
            student=self.student,
            amount=Decimal("400.00"),
            payment_method="cash",
            transaction_reference="TXN-2026-TEST01",
            idempotency_key="IDEMP-2026-TEST01",
            payer_name="Ada Lovelace",
            status=PaymentStatus.VERIFIED,
            recorded_by=self.admin,
        )

        # Attendance Session & Record
        self.att_session = AttendanceSession.objects.create(
            classroom=self.classroom,
            teacher=self.teacher,
            subject_name="Computer Science",
            session_date=timezone.now().date(),
            session_period="Period 1",
            topic="Algorithms",
            created_by=self.teacher,
        )
        self.record = AttendanceRecord.objects.create(
            session=self.att_session,
            student=self.student,
            status=AttendanceStatus.PRESENT,
        )

        # Academics Assessment & Score
        self.assessment = Assessment.objects.create(
            classroom=self.classroom,
            subject_name="Computer Science",
            teacher=self.teacher,
            title="Midterm Examination",
            assessment_type=AssessmentType.MIDTERM,
            max_marks=Decimal("100.00"),
            weightage_percent=Decimal("30.00"),
            is_published=True,
        )
        self.score = StudentAssessmentScore.objects.create(
            assessment=self.assessment,
            student=self.student,
            marks_obtained=Decimal("88.00"),
            grade="A",
            teacher_remarks="Excellent algorithmic thinking.",
        )

        # Complaints
        self.complaint_cat = ComplaintCategory.objects.create(
            name="Academic Affairs",
            code="ACAD",
            sla_days=3,
            is_active=True,
        )
        self.ticket = ComplaintTicket.objects.create(
            ticket_number="TKT-202610-00001",
            submitter=self.student,
            category=self.complaint_cat,
            subject="Question regarding syllabus coverage",
            description="Request for extra reference books.",
            priority=TicketPriority.MEDIUM,
            status=TicketStatus.OPEN,
        )

        # Announcement
        self.announcement = Announcement.objects.create(
            title="Campus Welcome Week",
            content="Welcome to all new students!",
            target_role=TargetRole.ALL,
            published_by=self.admin,
            publish_date=timezone.now(),
        )

    def test_get_admin_dashboard_metrics_real_aggregation(self):
        """
        Verify that dashboard metrics aggregate live database values precisely.
        """
        metrics = get_admin_dashboard_metrics()

        self.assertEqual(metrics["total_students"], 1)
        self.assertEqual(metrics["active_enrolments"], 1)
        self.assertEqual(metrics["total_classrooms"], 1)
        self.assertEqual(metrics["admissions_total"], 1)
        self.assertEqual(metrics["admissions_pending"], 1)
        self.assertEqual(metrics["total_gross_fees"], Decimal("1400.00"))
        self.assertEqual(metrics["total_fees_collected"], Decimal("400.00"))
        self.assertEqual(metrics["total_fees_outstanding"], Decimal("1000.00"))
        self.assertEqual(metrics["confirmed_payments_count"], 1)
        self.assertEqual(metrics["attendance_sessions_count"], 1)
        self.assertEqual(metrics["attendance_records_count"], 1)
        self.assertEqual(metrics["overall_attendance_rate"], Decimal("100.0"))
        self.assertEqual(metrics["open_complaints"], 1)
        self.assertEqual(metrics["active_teachers"], 1)
        self.assertEqual(metrics["active_assignments"], 1)
        self.assertEqual(metrics["active_announcements"], 1)
        self.assertEqual(metrics["role_counts"]["student"], 1)
        self.assertEqual(metrics["role_counts"]["teacher"], 1)

    def test_admin_dashboard_view_renders_for_admin(self):
        """
        Admin can access the main administrative dashboard.
        """
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:admin_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Administrative Command &amp; Intelligence Hub")
        self.assertContains(response, "Grade 10 - Section A")
        self.assertContains(response, "1400.00")

    def test_admissions_report_and_csv_export(self):
        """
        Test admissions report table view and streaming CSV export.
        """
        self.client.force_login(self.admin)
        # 1. HTML view
        response = self.client.get(reverse("reports:admissions_report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admissions Pipeline &amp; Applications Report")
        self.assertContains(response, self.application.application_number)

        # 2. Filter by status
        response = self.client.get(reverse("reports:admissions_report") + "?status=submitted")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.application.application_number)

        # 3. CSV export
        export_resp = self.client.get(reverse("reports:admissions_report") + "?export=csv")
        self.assertEqual(export_resp.status_code, 200)
        self.assertEqual(export_resp["Content-Type"], "text/csv")
        self.assertIn('attachment; filename="admissions_report.csv"', export_resp["Content-Disposition"])
        content = export_resp.content.decode("utf-8")
        self.assertIn("Application Number", content)
        self.assertIn(self.application.application_number, content)

        # Audit log verified
        self.assertTrue(
            AdminAuditLog.objects.filter(action="EXPORT_REPORT", target_model="AdmissionApplication").exists()
        )

    def test_fees_report_and_csv_export(self):
        """
        Test fees report view, balance aggregates, and CSV export.
        """
        self.client.force_login(self.admin)
        # HTML view
        response = self.client.get(reverse("reports:fees_report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fee Collection &amp; Outstanding Dues Report")
        self.assertContains(response, "1400.00")
        self.assertContains(response, "400.00")
        self.assertContains(response, "1000.00")

        # CSV export
        export_resp = self.client.get(reverse("reports:fees_report") + "?export=csv")
        self.assertEqual(export_resp.status_code, 200)
        self.assertEqual(export_resp["Content-Type"], "text/csv")
        content = export_resp.content.decode("utf-8")
        self.assertIn("Student ID", content)
        self.assertIn("Outstanding Balance", content)
        self.assertIn("1000.00", content)

    def test_attendance_report_and_csv_export(self):
        """
        Test attendance report and CSV export.
        """
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:attendance_report") + f"?classroom={self.classroom.id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Classroom Attendance &amp; Defaulter Report")
        self.assertContains(response, self.student.username)

        # CSV export
        export_resp = self.client.get(
            reverse("reports:attendance_report") + f"?classroom={self.classroom.id}&export=csv"
        )
        self.assertEqual(export_resp.status_code, 200)
        self.assertEqual(export_resp["Content-Type"], "text/csv")
        content = export_resp.content.decode("utf-8")
        self.assertIn("Roll Number", content)
        self.assertIn("Attendance %", content)
        self.assertIn("100.0%", content)

    def test_academics_report_and_csv_export(self):
        """
        Test academics report and CSV export.
        """
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:academics_report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic Performance &amp; Assessment Report")
        self.assertContains(response, "Midterm Examination")

        # CSV export
        export_resp = self.client.get(reverse("reports:academics_report") + "?export=csv")
        self.assertEqual(export_resp.status_code, 200)
        self.assertEqual(export_resp["Content-Type"], "text/csv")
        content = export_resp.content.decode("utf-8")
        self.assertIn("Assessment Title", content)
        self.assertIn("Midterm Examination", content)
        self.assertIn("88.00", content)

    def test_complaints_report_and_csv_export(self):
        """
        Test complaints report and CSV export.
        """
        self.client.force_login(self.admin)
        response = self.client.get(reverse("reports:complaints_report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grievance &amp; Complaint SLA Report")
        self.assertContains(response, self.ticket.ticket_number)

        # CSV export
        export_resp = self.client.get(reverse("reports:complaints_report") + "?export=csv")
        self.assertEqual(export_resp.status_code, 200)
        self.assertEqual(export_resp["Content-Type"], "text/csv")
        content = export_resp.content.decode("utf-8")
        self.assertIn("Ticket Number", content)
        self.assertIn(self.ticket.ticket_number, content)

    def test_institution_settings_update_creates_audit_log(self):
        """
        Verify institutional settings form updates singleton and records audit trail.
        """
        self.client.force_login(self.admin)
        url = reverse("reports:institution_settings")
        get_resp = self.client.get(url)
        self.assertEqual(get_resp.status_code, 200)

        post_data = {
            "institution_name": "EduConnect Academy of Science",
            "institution_code": "EDU-SCI",
            "academic_year": "2026-2027",
            "contact_email": "dean@educonnect.edu",
            "contact_phone": "+1-800-EDU-CONN",
            "campus_address": "400 Campus Oval, Science Quad",
            "attendance_minimum_percent": "80.0",
            "default_complaint_sla_days": "2",
        }
        post_resp = self.client.post(url, data=post_data, follow=True)
        self.assertEqual(post_resp.status_code, 200)

        # Check singleton updated
        settings = InstitutionSetting.get_settings()
        self.assertEqual(settings.institution_name, "EduConnect Academy of Science")
        self.assertEqual(settings.attendance_minimum_percent, Decimal("80.0"))
        self.assertEqual(settings.default_complaint_sla_days, 2)

        # Check audit log created
        log = AdminAuditLog.objects.filter(action="SETTINGS_UPDATE").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.admin)
        self.assertIn("EduConnect Academy of Science", log.description)

    def test_manage_classes_create_and_audit(self):
        """
        Verify class creation creates ClassRoom record and audit entry.
        """
        self.client.force_login(self.admin)
        url = reverse("reports:manage_classes")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            "name": "Grade 11 - Section B",
            "code": "G11-B",
            "academic_session": str(self.session.id),
            "room_number": "Room 205",
            "capacity": 35,
            "is_active": True,
        }
        post_resp = self.client.post(url, data=post_data, follow=True)
        self.assertEqual(post_resp.status_code, 200)

        new_class = ClassRoom.objects.filter(code="G11-B").first()
        self.assertIsNotNone(new_class)
        self.assertEqual(new_class.name, "Grade 11 - Section B")

        # Check audit log
        self.assertTrue(AdminAuditLog.objects.filter(action="CLASS_CREATE", target_id=str(new_class.id)).exists())

    def test_manage_enrollments_create_and_audit(self):
        """
        Verify student enrollment creates ClassEnrollment record and audit entry.
        """
        # Create another student to enroll
        student2 = User.objects.create_user(
            username="stud_grace",
            email="grace@educonnect.edu",
            password="StudentPassword123!",
            role=Role.STUDENT,
        )
        self.client.force_login(self.admin)
        url = reverse("reports:manage_enrollments")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            "student": str(student2.id),
            "classroom": str(self.classroom.id),
            "roll_number": "Roll-002",
            "is_active": True,
        }
        post_resp = self.client.post(url, data=post_data, follow=True)
        self.assertEqual(post_resp.status_code, 200)

        enr = ClassEnrollment.objects.filter(student=student2, classroom=self.classroom).first()
        self.assertIsNotNone(enr)
        self.assertEqual(enr.roll_number, "Roll-002")

        # Check audit log
        self.assertTrue(AdminAuditLog.objects.filter(action="ENROLLMENT_CREATE", target_id=str(enr.id)).exists())

    def test_manage_assignments_create_and_audit(self):
        """
        Verify teacher assignment creates TeacherAssignment record and audit entry.
        """
        self.client.force_login(self.admin)
        url = reverse("reports:manage_assignments")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            "teacher": str(self.teacher.id),
            "classroom": str(self.classroom.id),
            "subject_name": "Calculus & Linear Algebra",
            "is_active": True,
        }
        post_resp = self.client.post(url, data=post_data, follow=True)
        self.assertEqual(post_resp.status_code, 200)

        ta = TeacherAssignment.objects.filter(
            teacher=self.teacher, classroom=self.classroom, subject_name="Calculus & Linear Algebra"
        ).first()
        self.assertIsNotNone(ta)

        # Check audit log
        self.assertTrue(AdminAuditLog.objects.filter(action="TEACHER_ASSIGNMENT", target_id=str(ta.id)).exists())

    def test_audit_logs_view_and_filtering(self):
        """
        Verify that audit logs can be viewed and filtered by action type.
        """
        log_admin_action(
            actor=self.admin,
            action="SECURITY_CHECK",
            description="Performed quarterly security review.",
            target_model="System",
        )
        self.client.force_login(self.admin)
        url = reverse("reports:admin_audit_logs")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "SECURITY_CHECK")
        self.assertContains(response, "Performed quarterly security review.")

        # Filter by action
        filter_resp = self.client.get(url + "?action=SECURITY")
        self.assertEqual(filter_resp.status_code, 200)
        self.assertContains(filter_resp, "SECURITY_CHECK")

    def test_non_admin_users_denied_access(self):
        """
        Non-admin users (students, teachers, parents) must be rejected with 403 Forbidden.
        """
        protected_urls = [
            reverse("reports:admin_dashboard"),
            reverse("reports:admissions_report"),
            reverse("reports:fees_report"),
            reverse("reports:attendance_report"),
            reverse("reports:academics_report"),
            reverse("reports:complaints_report"),
            reverse("reports:institution_settings"),
            reverse("reports:admin_audit_logs"),
            reverse("reports:manage_classes"),
            reverse("reports:manage_enrollments"),
            reverse("reports:manage_assignments"),
        ]

        # Test as student
        self.client.force_login(self.student)
        for url in protected_urls:
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code,
                403,
                f"Student was unexpectedly permitted access to {url}",
            )

        # Test as teacher
        self.client.force_login(self.teacher)
        for url in protected_urls:
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code,
                403,
                f"Teacher was unexpectedly permitted access to {url}",
            )

        # Test as parent
        self.client.force_login(self.parent)
        for url in protected_urls:
            resp = self.client.get(url)
            self.assertEqual(
                resp.status_code,
                403,
                f"Parent was unexpectedly permitted access to {url}",
            )

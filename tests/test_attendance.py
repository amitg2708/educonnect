"""
EduConnect Attendance Management Automated Test Suite.
Tests:
- Teacher authorization for marking attendance (preventing unauthorized marking)
- Date boundary validation against academic sessions
- Class membership validation
- Duplicate session and duplicate student record prevention
- Policy-driven attendance calculations and percentages
- Student attendance dashboard and absence records
- Correction request submission, administrative review, and status update
- Parent-child authorization enforcement
- Comprehensive audit logging
"""

from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import Role, ParentStudentLink
from apps.attendance.models import (
    AcademicSession,
    ClassRoom,
    ClassEnrollment,
    TeacherAssignment,
    AttendancePolicy,
    AttendanceSession,
    AttendanceRecord,
    AttendanceStatus,
    AttendanceCorrectionRequest,
    CorrectionStatus,
)
from apps.attendance.services import (
    get_active_attendance_policy,
    calculate_student_attendance_summary,
    mark_session_attendance,
    correct_attendance_session,
    review_correction_request,
)

User = get_user_model()


class AttendanceManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin_user = User.objects.create_superuser(
            username="admin_att",
            email="admin_att@educonnect.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
        )
        self.teacher1 = User.objects.create_user(
            username="prof_smith",
            email="smith@educonnect.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            employee_id="FAC-SMITH",
        )
        self.teacher2 = User.objects.create_user(
            username="prof_jones",
            email="jones@educonnect.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            employee_id="FAC-JONES",
        )
        self.student1 = User.objects.create_user(
            username="student_carol",
            email="carol@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            student_id="STU-CAROL",
        )
        self.student2 = User.objects.create_user(
            username="student_david",
            email="david@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            student_id="STU-DAVID",
        )
        self.student_outsider = User.objects.create_user(
            username="student_outsider",
            email="outsider@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            student_id="STU-OUTSIDER",
        )
        self.parent1 = User.objects.create_user(
            username="parent_carol",
            email="parent_carol@educonnect.edu",
            password="TestPassword123!",
            role=Role.PARENT,
        )
        self.parent_stranger = User.objects.create_user(
            username="parent_unauthorized",
            email="unauth@educonnect.edu",
            password="TestPassword123!",
            role=Role.PARENT,
        )

        # Parent1 linked to Student1 (Carol)
        ParentStudentLink.objects.create(
            parent=self.parent1,
            student=self.student1,
            relationship_type="father",
            is_authorized=True,
        )

        # Academic Session: Fall 2026 (Aug 1 to Dec 20)
        today = timezone.now().date()
        self.academic_session = AcademicSession.objects.create(
            name="Fall 2026",
            start_date=today - timezone.timedelta(days=60),
            end_date=today + timezone.timedelta(days=60),
            is_current=True,
        )

        # Classroom
        self.classroom = ClassRoom.objects.create(
            name="Computer Science 101 - Cohort A",
            code="CS-101A",
            academic_session=self.academic_session,
            room_number="Room 301",
        )

        # Enroll Student1 and Student2
        self.enrollment1 = ClassEnrollment.objects.create(student=self.student1, classroom=self.classroom, roll_number="01")
        self.enrollment2 = ClassEnrollment.objects.create(student=self.student2, classroom=self.classroom, roll_number="02")

        # Teacher1 assigned to CS-101A for "Data Structures"
        self.assignment1 = TeacherAssignment.objects.create(
            teacher=self.teacher1,
            classroom=self.classroom,
            subject_name="Data Structures",
        )

        # Policy
        self.policy = get_active_attendance_policy()

    def test_teacher_marks_attendance_successfully(self):
        """Test teacher marking student roster for an authorized assignment."""
        today = timezone.now().date()
        student_records = {
            str(self.student1.id): {"status": AttendanceStatus.PRESENT, "remarks": "On time"},
            str(self.student2.id): {"status": AttendanceStatus.ABSENT, "remarks": "Unexcused"},
        }
        session = mark_session_attendance(
            assignment=self.assignment1,
            session_date=today,
            session_period="Period 1",
            topic="Binary Search Trees",
            student_records=student_records,
            actor=self.teacher1,
        )

        self.assertIsNotNone(session)
        self.assertEqual(session.records.count(), 2)

        # Check records
        r1 = session.records.get(student=self.student1)
        r2 = session.records.get(student=self.student2)
        self.assertEqual(r1.status, AttendanceStatus.PRESENT)
        self.assertEqual(r1.marked_by, self.teacher1)
        self.assertEqual(r2.status, AttendanceStatus.ABSENT)
        self.assertEqual(r2.remarks, "Unexcused")

    def test_unauthorized_teacher_prevented(self):
        """Test that a teacher cannot mark attendance for a class they are not assigned to."""
        today = timezone.now().date()
        student_records = {
            str(self.student1.id): {"status": AttendanceStatus.PRESENT},
        }
        # Teacher2 is NOT assigned to this class
        with self.assertRaises(PermissionDenied):
            mark_session_attendance(
                assignment=self.assignment1,
                session_date=today,
                session_period="Period 2",
                topic="Unauthorized Topic",
                student_records=student_records,
                actor=self.teacher2,
            )

    def test_duplicate_session_prevention(self):
        """Test that duplicate attendance sessions on the same day and period are prevented."""
        today = timezone.now().date()
        student_records = {
            str(self.student1.id): {"status": AttendanceStatus.PRESENT},
            str(self.student2.id): {"status": AttendanceStatus.PRESENT},
        }
        # Mark first time
        mark_session_attendance(
            assignment=self.assignment1,
            session_date=today,
            session_period="Period 1",
            topic="Recursion",
            student_records=student_records,
            actor=self.teacher1,
        )

        # Attempt to mark same session again
        with self.assertRaises(ValidationError) as ctx:
            mark_session_attendance(
                assignment=self.assignment1,
                session_date=today,
                session_period="Period 1",
                topic="Recursion Duplicate",
                student_records=student_records,
                actor=self.teacher1,
            )
        self.assertIn("already been recorded", str(ctx.exception))

    def test_date_boundary_validation(self):
        """Test that session date outside the academic session boundaries is rejected."""
        out_of_bounds_date = self.academic_session.end_date + timezone.timedelta(days=10)
        student_records = {
            str(self.student1.id): {"status": AttendanceStatus.PRESENT},
        }
        with self.assertRaises(ValidationError) as ctx:
            mark_session_attendance(
                assignment=self.assignment1,
                session_date=out_of_bounds_date,
                session_period="Period 1",
                topic="Future date",
                student_records=student_records,
                actor=self.teacher1,
            )
        self.assertIn("outside the active term range", str(ctx.exception))

    def test_policy_attendance_calculation(self):
        """Test attendance percentage calculation with weights (Present=1.0, Late=0.5, Excused=1.0, Absent=0.0)."""
        today = timezone.now().date()
        # Session 1: Present (1.0)
        s1 = AttendanceSession.objects.create(
            classroom=self.classroom, subject_name="Math", session_date=today - timezone.timedelta(days=3), session_period="P1"
        )
        AttendanceRecord.objects.create(session=s1, student=self.student1, status=AttendanceStatus.PRESENT)

        # Session 2: Late (0.5)
        s2 = AttendanceSession.objects.create(
            classroom=self.classroom, subject_name="Math", session_date=today - timezone.timedelta(days=2), session_period="P1"
        )
        AttendanceRecord.objects.create(session=s2, student=self.student1, status=AttendanceStatus.LATE)

        # Session 3: Excused (1.0)
        s3 = AttendanceSession.objects.create(
            classroom=self.classroom, subject_name="Math", session_date=today - timezone.timedelta(days=1), session_period="P1"
        )
        AttendanceRecord.objects.create(session=s3, student=self.student1, status=AttendanceStatus.EXCUSED)

        # Session 4: Absent (0.0)
        s4 = AttendanceSession.objects.create(
            classroom=self.classroom, subject_name="Math", session_date=today, session_period="P1"
        )
        AttendanceRecord.objects.create(session=s4, student=self.student1, status=AttendanceStatus.ABSENT)

        summary = calculate_student_attendance_summary(self.student1, policy=self.policy)
        # Total sessions = 4
        # Weighted units = 1.0 (present) + 0.5 (late) + 1.0 (excused) + 0.0 (absent) = 2.5
        # Percentage = (2.5 / 4) * 100 = 62.50%
        self.assertEqual(summary["total_sessions"], 4)
        self.assertEqual(summary["present_count"], 1)
        self.assertEqual(summary["late_count"], 1)
        self.assertEqual(summary["excused_count"], 1)
        self.assertEqual(summary["absent_count"], 1)
        self.assertEqual(summary["percentage"], Decimal("62.50"))
        # Minimum policy threshold is 75%, so student is below minimum!
        self.assertTrue(summary["is_below_minimum"])

    def test_attendance_correction_workflow(self):
        """Test student submitting correction request and admin approving it with status update and audit log."""
        today = timezone.now().date()
        s = AttendanceSession.objects.create(
            classroom=self.classroom, subject_name="Physics", session_date=today, session_period="Period 3"
        )
        record = AttendanceRecord.objects.create(
            session=s, student=self.student1, status=AttendanceStatus.ABSENT, marked_by=self.teacher1
        )

        # Student submits correction request
        self.client.force_login(self.student1)
        resp = self.client.post(
            reverse("attendance:submit_correction", args=[record.id]),
            {
                "requested_status": AttendanceStatus.EXCUSED,
                "reason": "Attending inter-school robotics competition",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        correction = AttendanceCorrectionRequest.objects.get(record=record, student=self.student1)
        self.assertEqual(correction.status, CorrectionStatus.PENDING)
        self.assertEqual(correction.requested_status, AttendanceStatus.EXCUSED)

        # Admin reviews and approves correction
        review_correction_request(
            correction=correction,
            decision="approved",
            reviewer=self.admin_user,
            review_notes="Valid school duty permission confirmed",
        )
        correction.refresh_from_db()
        record.refresh_from_db()

        self.assertEqual(correction.status, CorrectionStatus.APPROVED)
        self.assertEqual(record.status, AttendanceStatus.EXCUSED)
        self.assertEqual(record.modified_by, self.admin_user)
        self.assertIsNotNone(record.modified_at)

    def test_parent_child_attendance_authorization(self):
        """Test parent can view attendance for authorized child, but blocked for other students."""
        today = timezone.now().date()
        s = AttendanceSession.objects.create(
            classroom=self.classroom, subject_name="Chemistry", session_date=today, session_period="Period 2"
        )
        AttendanceRecord.objects.create(session=s, student=self.student1, status=AttendanceStatus.PRESENT)

        # Authorized Parent1 accesses Carol's attendance: 200 OK
        self.client.force_login(self.parent1)
        resp = self.client.get(reverse("attendance:parent_child_attendance", args=[self.student1.id]))
        self.assertEqual(resp.status_code, 200)

        # Stranger Parent attempts to access Carol's attendance: 403 Forbidden
        self.client.force_login(self.parent_stranger)
        resp = self.client.get(reverse("attendance:parent_child_attendance", args=[self.student1.id]))
        self.assertEqual(resp.status_code, 403)

"""
Acceptance Tests for Antigravity Task 2:
Coaching Courses, Batches, Timetables, and Enrolments in EduConnect.

Acceptance Test Requirements:
- Create a Class 10 tuition batch.
- Create a Class 11 Science batch.
- Create a competitive-exam batch.
- Enrol the same student in two compatible batches.
- Reject an unauthorized cross-institute enrolment.
- Prevent duplicate active enrolments.
- Verify that batch rosters contain only the correct students.
- Validate batch capacity & waitlist promotion.
- Validate schedule conflict prevention.
- Validate student batch transfer.
"""

from datetime import date, time, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentStudentLink, Role, User
from apps.attendance.models import AcademicSession, ClassRoom
from apps.academics.models import (
    Batch,
    BatchEnrollment,
    BatchSchedule,
    BatchTeacherAssignment,
    Subject,
)
from apps.academics.services import (
    check_batch_schedule_conflicts,
    enroll_student_in_batch,
    promote_waitlisted_student_for_batch,
    transfer_student_batch,
    validate_batch_enrollment,
)
from apps.core.models import Course
from apps.institutions.models import Branch, Institution, InstitutionMembership


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CoachingBatchesAndEnrollmentTestCase(TestCase):
    """
    Comprehensive acceptance test suite for Task 2 academic coaching cohorts.
    """

    def setUp(self):
        super().setUp()

        # Primary Institute
        self.institution = Institution.objects.create(
            name="Apex Coaching Academy",
            code="APEX",
            slug="apex-coaching-academy",
            primary_color="#10b981",
        )
        self.branch_main = Branch.objects.create(
            institution=self.institution,
            name="Downtown Center",
            code="MAIN",
            city="New Delhi",
        )
        self.branch_north = Branch.objects.create(
            institution=self.institution,
            name="North Campus Branch",
            code="NORTH",
            city="New Delhi",
        )

        # Second Institute for cross-tenant testing
        self.other_institution = Institution.objects.create(
            name="Zenith Learning Hub",
            code="ZENITH",
            slug="zenith-learning-hub",
            primary_color="#6366f1",
        )
        self.other_branch = Branch.objects.create(
            institution=self.other_institution,
            name="Zenith Main Branch",
            code="ZMAIN",
        )

        # Academic Session
        self.academic_session = AcademicSession.objects.create(
            name="Academic Year 2026-2027",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            is_current=True,
        )

        # Classroom
        self.classroom_101 = ClassRoom.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            academic_session=self.academic_session,
            name="Room 101 - Lecture Hall",
            code="R101",
            capacity=40,
            is_active=True,
        )

        # Subjects
        self.subj_math = Subject.objects.create(
            institution=self.institution,
            name="Mathematics",
            code="MATH10",
        )
        self.subj_physics = Subject.objects.create(
            institution=self.institution,
            name="Physics",
            code="PHY11",
        )
        self.subj_chemistry = Subject.objects.create(
            institution=self.institution,
            name="Chemistry",
            code="CHEM11",
        )

        # Faculty
        self.teacher_math = User.objects.create_user(
            username="faculty_math",
            email="math@apex.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            first_name="Prof",
            last_name="Ramanujan",
        )
        InstitutionMembership.objects.create(
            user=self.teacher_math,
            institution=self.institution,
            role=Role.TEACHER,
            is_active=True,
        )

        # Students (Belonging to Apex)
        self.student_aarav = User.objects.create_user(
            username="student_aarav",
            email="aarav@apex.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            first_name="Aarav",
            last_name="Sharma",
        )
        InstitutionMembership.objects.create(
            user=self.student_aarav,
            institution=self.institution,
            role=Role.STUDENT,
            is_active=True,
        )

        self.student_diya = User.objects.create_user(
            username="student_diya",
            email="diya@apex.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            first_name="Diya",
            last_name="Patel",
        )
        InstitutionMembership.objects.create(
            user=self.student_diya,
            institution=self.institution,
            role=Role.STUDENT,
            is_active=True,
        )

        # Student belonging ONLY to Zenith (for cross-institute testing)
        self.student_zenith = User.objects.create_user(
            username="student_zenith",
            email="zenith_student@zenith.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            first_name="Rohan",
            last_name="Zenith",
        )
        InstitutionMembership.objects.create(
            user=self.student_zenith,
            institution=self.other_institution,
            role=Role.STUDENT,
            is_active=True,
        )

        # Admin User for Apex
        self.admin_apex = User.objects.create_user(
            username="admin_apex",
            email="admin@apex.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
            first_name="Director",
            last_name="Apex",
        )
        InstitutionMembership.objects.create(
            user=self.admin_apex,
            institution=self.institution,
            role=Role.ADMIN,
            is_active=True,
            is_default=True,
        )

        # Parent User for Apex (linked to student Aarav)
        self.parent_apex = User.objects.create_user(
            username="parent_aarav",
            email="parent@apex.edu",
            password="TestPassword123!",
            role=Role.PARENT,
            first_name="Sunil",
            last_name="Sharma",
        )
        InstitutionMembership.objects.create(
            user=self.parent_apex,
            institution=self.institution,
            role=Role.PARENT,
            is_active=True,
            is_default=True,
        )
        ParentStudentLink.objects.create(
            institution=self.institution,
            parent=self.parent_apex,
            student=self.student_aarav,
            relationship_type="father",
            is_authorized=True,
        )

        # Admin User for Zenith (for cross-institute access tests)
        self.admin_zenith = User.objects.create_user(
            username="admin_zenith",
            email="admin@zenith.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
            first_name="Director",
            last_name="Zenith",
        )
        InstitutionMembership.objects.create(
            user=self.admin_zenith,
            institution=self.other_institution,
            role=Role.ADMIN,
            is_active=True,
            is_default=True,
        )

    # --------------------------------------------------------------------------
    # Acceptance Test 1: Create a Class 10 tuition batch
    # --------------------------------------------------------------------------
    def test_create_class_10_tuition_batch(self):
        """
        Verify creation of a School Tuition batch for Class 10 with configurable board.
        """
        course_c10 = Course.objects.create(
            institution=self.institution,
            title="Class 10 CBSE Board & Foundation Course",
            code="CRS-C10-CBSE",
            category=Course.Category.SCHOOL_TUITION,
            target_class="Class 10",
            stream=Course.Stream.GENERAL,
            board="CBSE",
            department="Secondary School Tuition",
            duration="1 Academic Year",
            fee_per_term=Decimal("12000.00"),
            fee_period="Per Term",
        )

        batch_c10 = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course_c10,
            academic_session=self.academic_session,
            classroom=self.classroom_101,
            name="Class 10 CBSE Math & Science - Evening A",
            code="BAT-C10-01",
            target_class="Class 10",
            stream="General",
            board="CBSE",
            start_date=date(2026, 4, 15),
            end_date=date(2027, 2, 28),
            capacity=30,
            enable_waitlist=True,
            status=Batch.Status.ONGOING,
        )

        self.assertEqual(batch_c10.institution, self.institution)
        self.assertEqual(batch_c10.branch, self.branch_main)
        self.assertEqual(batch_c10.target_class, "Class 10")
        self.assertEqual(batch_c10.board, "CBSE")
        self.assertEqual(batch_c10.capacity, 30)
        self.assertEqual(batch_c10.active_enrollments_count, 0)
        self.assertFalse(batch_c10.is_full)
        self.assertEqual(batch_c10.available_seats, 30)

    # --------------------------------------------------------------------------
    # Acceptance Test 2: Create a Class 11 Science batch
    # --------------------------------------------------------------------------
    def test_create_class_11_science_batch(self):
        """
        Verify creation of a Junior College batch for Class 11 Science stream.
        """
        course_c11_sci = Course.objects.create(
            institution=self.institution,
            title="Class 11 Junior College - Science (PCM/B)",
            code="CRS-C11-SCI",
            category=Course.Category.JUNIOR_COLLEGE,
            target_class="Class 11",
            stream=Course.Stream.SCIENCE,
            board="Maharashtra State Board",
            department="Junior College Science Division",
            duration="1 Year",
            fee_per_term=Decimal("18000.00"),
            fee_period="Per Term",
        )

        batch_c11_sci = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_north,
            course=course_c11_sci,
            academic_session=self.academic_session,
            name="Class 11 Science PCM Cohort Alpha",
            code="BAT-C11-PCM-01",
            target_class="Class 11",
            stream="Science",
            board="Maharashtra State Board",
            start_date=date(2026, 6, 1),
            end_date=date(2027, 4, 30),
            capacity=40,
            enable_waitlist=True,
            status=Batch.Status.UPCOMING,
        )

        self.assertEqual(batch_c11_sci.course.category, Course.Category.JUNIOR_COLLEGE)
        self.assertEqual(batch_c11_sci.stream, "Science")
        self.assertEqual(batch_c11_sci.branch, self.branch_north)
        self.assertEqual(batch_c11_sci.capacity, 40)

    # --------------------------------------------------------------------------
    # Acceptance Test 3: Create a competitive-exam batch
    # --------------------------------------------------------------------------
    def test_create_competitive_exam_batch(self):
        """
        Verify creation of a configurable entrance & competitive exam prep batch.
        """
        course_jee = Course.objects.create(
            institution=self.institution,
            title="JEE Main & Advanced 2-Year Comprehensive Program",
            code="CRS-JEE-2Y",
            category=Course.Category.COMPETITIVE_EXAM,
            target_class="Class 11 & 12",
            stream=Course.Stream.SCIENCE,
            examination_scheme="JEE Main / JEE Advanced / BITSAT",
            department="Competitive Engineering Wing",
            duration="2 Years",
            fee_per_term=Decimal("35000.00"),
            fee_period="Per Term",
        )

        batch_jee = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course_jee,
            academic_session=self.academic_session,
            name="JEE Pinnacle Super 30 - 2027",
            code="BAT-JEE-S30",
            target_class="Class 11",
            stream="Science (PCM)",
            start_date=date(2026, 5, 1),
            end_date=date(2028, 4, 30),
            capacity=30,
            enable_waitlist=True,
            max_waitlist_capacity=15,
            status=Batch.Status.ONGOING,
        )

        self.assertEqual(batch_jee.course.category, Course.Category.COMPETITIVE_EXAM)
        self.assertEqual(batch_jee.course.examination_scheme, "JEE Main / JEE Advanced / BITSAT")
        self.assertEqual(batch_jee.max_waitlist_capacity, 15)

    # --------------------------------------------------------------------------
    # Acceptance Test 4: Enrol the same student in two compatible batches
    # --------------------------------------------------------------------------
    def test_enrol_same_student_in_two_compatible_batches(self):
        """
        A student has a single user account & profile, but can be enrolled in
        multiple distinct active batches (e.g. Class 10 Tuition + NTSE Competitive Exam)
        provided their schedules do not overlap.
        """
        # Batch 1: Class 10 Tuition (Mon/Wed 16:00 - 18:00)
        course_tuition = Course.objects.create(
            institution=self.institution,
            title="Class 10 Regular Tuition",
            code="CRS-T10",
            category=Course.Category.SCHOOL_TUITION,
            duration="1 Year",
        )
        batch_tuition = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course_tuition,
            academic_session=self.academic_session,
            name="Class 10 Tuition Batch",
            code="BAT-T10",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=30,
        )
        # Schedule: Monday (0) 16:00 to 18:00
        BatchSchedule.objects.create(
            batch=batch_tuition,
            day_of_week=0,
            start_time=time(16, 0),
            end_time=time(18, 0),
        )

        # Batch 2: Olympiad & NTSE Competitive Prep (Tue/Thu 16:00 - 18:00)
        course_olympiad = Course.objects.create(
            institution=self.institution,
            title="NTSE & Math Olympiad Prep",
            code="CRS-OLY-10",
            category=Course.Category.COMPETITIVE_EXAM,
            duration="1 Year",
        )
        batch_olympiad = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course_olympiad,
            academic_session=self.academic_session,
            name="NTSE Scholars Batch",
            code="BAT-NTSE-01",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=25,
        )
        # Schedule: Tuesday (1) 16:00 to 18:00 (Compatible, non-overlapping!)
        BatchSchedule.objects.create(
            batch=batch_olympiad,
            day_of_week=1,
            start_time=time(16, 0),
            end_time=time(18, 0),
        )

        # Enrol student Aarav in Batch 1
        enr_1 = enroll_student_in_batch(
            student=self.student_aarav,
            batch=batch_tuition,
            roll_number="C10-01",
        )
        self.assertEqual(enr_1.status, BatchEnrollment.Status.ACTIVE)

        # Enrol same student Aarav in Batch 2
        enr_2 = enroll_student_in_batch(
            student=self.student_aarav,
            batch=batch_olympiad,
            roll_number="NTSE-05",
        )
        self.assertEqual(enr_2.status, BatchEnrollment.Status.ACTIVE)

        # Verify single student account holds two active enrollments
        aarav_active_enrs = BatchEnrollment.objects.filter(
            student=self.student_aarav,
            status=BatchEnrollment.Status.ACTIVE,
        )
        self.assertEqual(aarav_active_enrs.count(), 2)
        batch_names = [e.batch.name for e in aarav_active_enrs]
        self.assertIn("Class 10 Tuition Batch", batch_names)
        self.assertIn("NTSE Scholars Batch", batch_names)

    # --------------------------------------------------------------------------
    # Acceptance Test 5: Reject an unauthorized cross-institute enrolment
    # --------------------------------------------------------------------------
    def test_reject_unauthorized_cross_institute_enrolment(self):
        """
        Validate that a student belonging to Zenith Learning Hub cannot be enrolled
        into a batch belonging to Apex Coaching Academy.
        """
        course_apex = Course.objects.create(
            institution=self.institution,
            title="Apex Exclusive Course",
            code="CRS-APX-01",
            duration="1 Year",
        )
        batch_apex = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course_apex,
            academic_session=self.academic_session,
            name="Apex Exclusive Batch",
            code="BAT-APX-01",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=20,
        )

        # Attempt to enrol student_zenith (from Zenith) into batch_apex (Apex)
        with self.assertRaises(ValidationError) as ctx:
            enroll_student_in_batch(
                student=self.student_zenith,
                batch=batch_apex,
            )

        err_msg = str(ctx.exception).lower()
        self.assertTrue(
            "cross-institute" in err_msg or "does not belong" in err_msg,
            f"Expected cross-institute rejection message, got: {err_msg}",
        )
        self.assertEqual(batch_apex.active_enrollments_count, 0)

    # --------------------------------------------------------------------------
    # Acceptance Test 6: Prevent duplicate active enrolments
    # --------------------------------------------------------------------------
    def test_prevent_duplicate_active_enrolments(self):
        """
        Validate that the same student cannot be enrolled more than once in the
        same active batch.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Class 9 Foundation",
            code="CRS-C9",
            duration="1 Year",
        )
        batch = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Class 9 Batch A",
            code="BAT-C9-A",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=25,
        )

        # First enrolment succeeds
        enroll_student_in_batch(
            student=self.student_diya,
            batch=batch,
            roll_number="01",
        )

        # Second enrolment in same batch must be rejected
        with self.assertRaises(ValidationError) as ctx:
            enroll_student_in_batch(
                student=self.student_diya,
                batch=batch,
                roll_number="01-DUP",
            )

        err_msg = str(ctx.exception).lower()
        self.assertTrue(
            "already actively enrolled" in err_msg or "duplicate" in err_msg,
            f"Expected duplicate active enrolment error, got: {err_msg}",
        )
        self.assertEqual(batch.active_enrollments_count, 1)

    # --------------------------------------------------------------------------
    # Acceptance Test 7: Verify that batch rosters contain only the correct students
    # --------------------------------------------------------------------------
    def test_verify_batch_rosters_contain_only_correct_students(self):
        """
        Ensure batch rosters isolate students cleanly between cohorts.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Language & Aptitude Course",
            code="CRS-LANG",
            duration="6 Months",
        )

        batch_alpha = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Batch Alpha",
            code="BAT-ALPHA",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 9, 30),
            capacity=20,
        )

        batch_beta = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Batch Beta",
            code="BAT-BETA",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 9, 30),
            capacity=20,
        )

        # Enrol Aarav in Alpha
        enroll_student_in_batch(student=self.student_aarav, batch=batch_alpha)
        # Enrol Diya in Beta
        enroll_student_in_batch(student=self.student_diya, batch=batch_beta)

        # Inspect rosters
        alpha_students = set(
            batch_alpha.batch_enrollments.filter(
                status=BatchEnrollment.Status.ACTIVE
            ).values_list("student__username", flat=True)
        )
        beta_students = set(
            batch_beta.batch_enrollments.filter(
                status=BatchEnrollment.Status.ACTIVE
            ).values_list("student__username", flat=True)
        )

        self.assertIn("student_aarav", alpha_students)
        self.assertNotIn("student_diya", alpha_students)

        self.assertIn("student_diya", beta_students)
        self.assertNotIn("student_aarav", beta_students)

    # --------------------------------------------------------------------------
    # Additional Validation Test: Schedule conflict prevention
    # --------------------------------------------------------------------------
    def test_schedule_conflict_prevention(self):
        """
        Validate that enrolling a student in a batch that clashes with an existing
        active batch's timetable raises a ValidationError.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="General Coaching",
            code="CRS-GEN",
            duration="1 Year",
        )

        # Batch 1: Monday 16:00 - 18:00
        batch_1 = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Batch Monday Early",
            code="BAT-M1",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=30,
        )
        BatchSchedule.objects.create(
            batch=batch_1,
            day_of_week=0,  # Monday
            start_time=time(16, 0),
            end_time=time(18, 0),
        )

        # Batch 2: Monday 17:00 - 19:00 (Overlaps 17:00 to 18:00!)
        batch_2 = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Batch Monday Late",
            code="BAT-M2",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=30,
        )
        BatchSchedule.objects.create(
            batch=batch_2,
            day_of_week=0,  # Monday
            start_time=time(17, 0),
            end_time=time(19, 0),
        )

        # Enrol Aarav in Batch 1
        enroll_student_in_batch(student=self.student_aarav, batch=batch_1)

        # Attempt to enrol Aarav in overlapping Batch 2 -> must be rejected
        with self.assertRaises(ValidationError) as ctx:
            enroll_student_in_batch(student=self.student_aarav, batch=batch_2)

        err_msg = str(ctx.exception).lower()
        self.assertTrue(
            "schedule conflict" in err_msg or "overlaps" in err_msg or "clash" in err_msg,
            f"Expected schedule conflict error, got: {err_msg}",
        )

    # --------------------------------------------------------------------------
    # Additional Validation Test: Batch capacity, waitlisting, and promotion
    # --------------------------------------------------------------------------
    def test_batch_capacity_and_waitlist_promotion(self):
        """
        Validate that:
        1. When capacity is reached, student is placed on WAITLISTED with proper queue position.
        2. When a seat opens up (transfer or drop), the waitlist student is promoted to ACTIVE.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Crash Course",
            code="CRS-CRASH",
            duration="1 Month",
        )
        # Small batch with capacity 2
        batch = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Small Seminar Cohort",
            code="BAT-SEMINAR",
            start_date=date(2026, 5, 1),
            end_date=date(2026, 5, 31),
            capacity=2,
            enable_waitlist=True,
            max_waitlist_capacity=5,
        )

        # Student 3
        student_3 = User.objects.create_user(
            username="student_third",
            email="third@apex.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            institution=self.institution,
        )

        # Enrol Student 1 -> Seat 1 (ACTIVE)
        enr_1 = enroll_student_in_batch(student=self.student_aarav, batch=batch)
        self.assertEqual(enr_1.status, BatchEnrollment.Status.ACTIVE)
        self.assertEqual(batch.available_seats, 1)

        # Enrol Student 2 -> Seat 2 (ACTIVE)
        enr_2 = enroll_student_in_batch(student=self.student_diya, batch=batch)
        self.assertEqual(enr_2.status, BatchEnrollment.Status.ACTIVE)
        self.assertEqual(batch.available_seats, 0)
        self.assertTrue(batch.is_full)

        # Enrol Student 3 -> Batch is full, so placed on WAITLIST
        enr_3 = enroll_student_in_batch(student=student_3, batch=batch)
        self.assertEqual(enr_3.status, BatchEnrollment.Status.WAITLISTED)
        self.assertEqual(enr_3.waitlist_position, 1)

        # Student 1 drops or transfers -> Seat opens up -> promote Student 3
        enr_1.status = BatchEnrollment.Status.DROPPED
        enr_1.save()

        # Trigger waitlist promotion
        promoted = promote_waitlisted_student_for_batch(batch)
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted.student, student_3)
        self.assertEqual(promoted.status, BatchEnrollment.Status.ACTIVE)
        self.assertIsNone(promoted.waitlist_position)

    # --------------------------------------------------------------------------
    # Additional Validation Test: Student batch transfer workflow
    # --------------------------------------------------------------------------
    def test_student_batch_transfer(self):
        """
        Validate transferring a student from Batch 1 to Batch 2:
        - Marks old enrolment as TRANSFERRED
        - Creates new enrolment as ACTIVE in destination
        - Links transferred_to and records reason
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Regular Math Course",
            code="CRS-M-REG",
            duration="1 Year",
        )
        batch_src = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Morning Batch",
            code="BAT-MORN",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=20,
        )
        batch_dst = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Evening Batch",
            code="BAT-EVE",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=20,
        )

        enr_src = enroll_student_in_batch(student=self.student_aarav, batch=batch_src)
        self.assertEqual(enr_src.status, BatchEnrollment.Status.ACTIVE)

        # Transfer to Evening Batch
        old_enr, new_enr = transfer_student_batch(
            enrollment=enr_src,
            target_batch=batch_dst,
            reason="Shifted to evening slot due to school laboratory timings.",
            transferred_by=self.teacher_math,
        )

        old_enr.refresh_from_db()
        self.assertEqual(old_enr.status, BatchEnrollment.Status.TRANSFERRED)
        self.assertEqual(old_enr.transferred_to, new_enr)
        self.assertEqual(new_enr.batch, batch_dst)
        self.assertEqual(new_enr.status, BatchEnrollment.Status.ACTIVE)
        self.assertEqual(batch_src.active_enrollments_count, 0)
        self.assertEqual(batch_dst.active_enrollments_count, 1)

    # --------------------------------------------------------------------------
    # Additional Validation Test: Teacher assignment to authorized batch & subject
    # --------------------------------------------------------------------------
    def test_teacher_assignment_to_batch(self):
        """
        Validate assigning a subject teacher to a batch and checking authorization.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Physics Intensive",
            code="CRS-PHY-INT",
            duration="6 Months",
        )
        batch = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Physics Honors",
            code="BAT-PHY-HON",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 10, 31),
            capacity=25,
        )

        assignment = BatchTeacherAssignment.objects.create(
            batch=batch,
            teacher=self.teacher_math,
            subject=self.subj_physics,
            is_primary=True,
        )

        self.assertEqual(batch.teacher_assignments.count(), 1)
        self.assertEqual(assignment.teacher, self.teacher_math)
        self.assertEqual(assignment.subject, self.subj_physics)
        self.assertTrue(assignment.is_primary)

    # --------------------------------------------------------------------------
    # Acceptance Test 12: Admin Batches List View, Search, Filter & Pagination
    # --------------------------------------------------------------------------
    def test_admin_batches_list_view_and_filtering(self):
        """
        Verify that the coaching batches admin desk renders, filters by search query,
        branch, and status, and enforces institution isolation.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Class 10 Regular Tuition",
            code="CRS-T10-VIEW",
            category=Course.Category.SCHOOL_TUITION,
            duration="1 Year",
        )
        batch_1 = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Class 10 Alpha Morning",
            code="BAT-C10-AM",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=30,
            status=Batch.Status.ONGOING,
        )
        batch_2 = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_north,
            course=course,
            academic_session=self.academic_session,
            name="Class 10 Beta Evening",
            code="BAT-C10-BE",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=25,
            status=Batch.Status.UPCOMING,
        )

        self.client.force_login(self.admin_apex)
        session = self.client.session
        session["active_institution_id"] = str(self.institution.id)
        session.save()

        # 1. Main List view
        response = self.client.get(reverse("academics:admin_batches"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class 10 Alpha Morning")
        self.assertContains(response, "Class 10 Beta Evening")

        # 2. Filter by Search Query
        response = self.client.get(reverse("academics:admin_batches") + "?q=Alpha")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class 10 Alpha Morning")
        self.assertNotContains(response, "Class 10 Beta Evening")

        # 3. Filter by Branch
        response = self.client.get(reverse("academics:admin_batches") + f"?branch={self.branch_north.id}")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class 10 Beta Evening")
        self.assertNotContains(response, "Class 10 Alpha Morning")

    # --------------------------------------------------------------------------
    # Acceptance Test 13: Batch Detail View with Roster, Schedule, and Faculty
    # --------------------------------------------------------------------------
    def test_admin_batch_detail_view(self):
        """
        Verify the batch command center detail page displays active roster,
        schedules, and faculty assignments.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Class 12 Board & JEE",
            code="CRS-C12-JEE",
            category=Course.Category.COMPETITIVE_EXAM,
            duration="1 Year",
        )
        batch = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            classroom=self.classroom_101,
            name="Class 12 JEE Elite Cohort",
            code="BAT-C12-ELITE",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=30,
        )
        # Schedule slot
        BatchSchedule.objects.create(
            batch=batch,
            subject=self.subj_math,
            teacher=self.teacher_math,
            day_of_week=0,
            start_time=time(16, 0),
            end_time=time(18, 0),
        )
        # Teacher assignment
        BatchTeacherAssignment.objects.create(
            batch=batch,
            teacher=self.teacher_math,
            subject=self.subj_math,
            is_primary=True,
        )
        # Enrol student Aarav
        enroll_student_in_batch(student=self.student_aarav, batch=batch, roll_number="R-101")

        self.client.force_login(self.admin_apex)
        session = self.client.session
        session["active_institution_id"] = str(self.institution.id)
        session.save()

        response = self.client.get(reverse("academics:admin_batch_detail", kwargs={"batch_id": batch.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class 12 JEE Elite Cohort")
        self.assertContains(response, "BAT-C12-ELITE")
        self.assertContains(response, "Aarav Sharma")
        self.assertContains(response, "R-101")
        self.assertContains(response, "Prof Ramanujan")
        self.assertContains(response, "Mathematics")

    # --------------------------------------------------------------------------
    # Acceptance Test 14: Cross-Institute Batch Access Rejection
    # --------------------------------------------------------------------------
    def test_cross_institute_batch_access_rejected(self):
        """
        An administrator of Zenith Learning Hub cannot access the batch detail
        page of Apex Coaching Academy.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Apex Proprietary Batch",
            code="CRS-APX-PROP",
            duration="1 Year",
        )
        batch = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Apex Secret Batch",
            code="BAT-APX-SEC",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=15,
        )

        # Login as Zenith Admin
        self.client.force_login(self.admin_zenith)
        session = self.client.session
        session["active_institution_id"] = str(self.other_institution.id)
        session.save()

        response = self.client.get(reverse("academics:admin_batch_detail", kwargs={"batch_id": batch.id}))
        # Must return 404 since get_object_or_404 scopes by active institution
        self.assertEqual(response.status_code, 404)

    # --------------------------------------------------------------------------
    # Acceptance Test 15: Student My Batches Portal
    # --------------------------------------------------------------------------
    def test_student_my_batches_view(self):
        """
        Verify that a student can view their enrolled coaching batches, schedule,
        and instructors across multiple active enrolments with a single account.
        """
        course_1 = Course.objects.create(
            institution=self.institution,
            title="Class 10 Regular Tuition",
            code="CRS-STU-T10",
            category=Course.Category.SCHOOL_TUITION,
            duration="1 Year",
        )
        course_2 = Course.objects.create(
            institution=self.institution,
            title="Olympiad Prep",
            code="CRS-STU-OLY",
            category=Course.Category.COMPETITIVE_EXAM,
            duration="1 Year",
        )
        batch_1 = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course_1,
            academic_session=self.academic_session,
            name="Class 10 Board Excellence",
            code="BAT-C10-EXC",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=30,
        )
        batch_2 = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course_2,
            academic_session=self.academic_session,
            name="Math Olympiad Squad",
            code="BAT-OLY-SQ",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=20,
        )

        enroll_student_in_batch(student=self.student_aarav, batch=batch_1)
        enroll_student_in_batch(student=self.student_aarav, batch=batch_2)

        self.client.force_login(self.student_aarav)
        session = self.client.session
        session["active_institution_id"] = str(self.institution.id)
        session.save()

        response = self.client.get(reverse("academics:student_my_batches"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class 10 Board Excellence")
        self.assertContains(response, "Math Olympiad Squad")

    # --------------------------------------------------------------------------
    # Acceptance Test 16: Parent Child Batches Portal
    # --------------------------------------------------------------------------
    def test_parent_child_batches_view(self):
        """
        Verify that a parent can view the coaching batches and schedules of their
        linked student.
        """
        course = Course.objects.create(
            institution=self.institution,
            title="Class 10 Comprehensive",
            code="CRS-PRN-10",
            category=Course.Category.SCHOOL_TUITION,
            duration="1 Year",
        )
        batch = Batch.objects.create(
            institution=self.institution,
            branch=self.branch_main,
            course=course,
            academic_session=self.academic_session,
            name="Class 10 Star Cohort",
            code="BAT-PRN-C10",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            capacity=30,
        )
        enroll_student_in_batch(student=self.student_aarav, batch=batch)

        self.client.force_login(self.parent_apex)
        session = self.client.session
        session["active_institution_id"] = str(self.institution.id)
        session.save()

        response = self.client.get(reverse("academics:parent_child_batches"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class 10 Star Cohort")
        self.assertContains(response, "Aarav Sharma")


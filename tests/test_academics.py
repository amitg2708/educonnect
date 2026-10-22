"""
EduConnect Academics & Subject Teacher Automated Test Suite.
Tests:
- Teacher authorization verification against TeacherAssignment
- Study material upload and file validation
- Coursework assignment creation and deadline tracking
- Student submission workflows and late submission detection
- Submission grading with bounds validation
- Confidential until published assessment scores (draft isolation)
- Assessment publication and student/parent transcript access
- Direct student-faculty doubt clearing threads
- Parent-child link authorization enforcement
"""

from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentStudentLink, Role
from apps.attendance.models import AcademicSession, ClassEnrollment, ClassRoom, TeacherAssignment
from apps.academics.models import (
    Assessment,
    AssessmentType,
    Assignment,
    AssignmentSubmission,
    StudentAssessmentScore,
    StudentDoubt,
    StudyMaterial,
)
from apps.academics.services import (
    answer_student_doubt,
    calculate_letter_grade,
    enter_student_assessment_score,
    grade_assignment_submission,
    is_student_enrolled_in_classroom,
    is_teacher_authorized_for_subject,
    publish_assessment_results,
    submit_student_assignment,
)

User = get_user_model()


class AcademicsManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Admin
        self.admin_user = User.objects.create_superuser(
            username="admin_acad",
            email="admin_acad@educonnect.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
        )

        # Faculty
        self.teacher = User.objects.create_user(
            username="prof_gauss",
            email="gauss@educonnect.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            employee_id="FAC-GAUSS",
            first_name="Carl",
            last_name="Gauss",
        )
        self.other_teacher = User.objects.create_user(
            username="prof_euler",
            email="euler@educonnect.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            employee_id="FAC-EULER",
            first_name="Leonhard",
            last_name="Euler",
        )

        # Students
        self.student = User.objects.create_user(
            username="stud_alice",
            email="alice@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            student_id="STU-ALICE-01",
            first_name="Alice",
            last_name="Smith",
        )
        self.other_student = User.objects.create_user(
            username="stud_bob",
            email="bob@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            student_id="STU-BOB-02",
            first_name="Bob",
            last_name="Jones",
        )

        # Parents
        self.parent = User.objects.create_user(
            username="parent_alice",
            email="parent_alice@gmail.com",
            password="TestPassword123!",
            role=Role.PARENT,
            first_name="Robert",
            last_name="Smith",
        )
        self.other_parent = User.objects.create_user(
            username="parent_unrelated",
            email="unrelated@gmail.com",
            password="TestPassword123!",
            role=Role.PARENT,
        )

        # Link parent to student
        ParentStudentLink.objects.create(
            parent=self.parent,
            student=self.student,
            relationship_type="father",
            is_authorized=True,
        )

        # Academic Session & Classroom
        self.session = AcademicSession.objects.create(
            name="Academic Year 2026-2027",
            start_date=timezone.now().date() - timedelta(days=30),
            end_date=timezone.now().date() + timedelta(days=300),
            is_current=True,
        )
        self.classroom = ClassRoom.objects.create(
            name="Grade 10 - Section A",
            code="G10-A",
            academic_session=self.session,
            room_number="Room 101",
            capacity=35,
        )
        self.other_classroom = ClassRoom.objects.create(
            name="Grade 11 - Section B",
            code="G11-B",
            academic_session=self.session,
            room_number="Room 202",
            capacity=30,
        )

        # Enroll student in classroom
        self.enrollment = ClassEnrollment.objects.create(
            student=self.student,
            classroom=self.classroom,
            roll_number="101-01",
            is_active=True,
        )

        # Assign prof_gauss to teach "Mathematics" in classroom
        self.assignment_math = TeacherAssignment.objects.create(
            teacher=self.teacher,
            classroom=self.classroom,
            subject_name="Mathematics",
            is_active=True,
        )

    def test_grade_calculation(self):
        """Test calculation of institutional letter grades."""
        self.assertEqual(calculate_letter_grade(Decimal("95.00"), Decimal("100.00")), "A+")
        self.assertEqual(calculate_letter_grade(Decimal("85.00"), Decimal("100.00")), "A")
        self.assertEqual(calculate_letter_grade(Decimal("75.00"), Decimal("100.00")), "B")
        self.assertEqual(calculate_letter_grade(Decimal("65.00"), Decimal("100.00")), "C")
        self.assertEqual(calculate_letter_grade(Decimal("52.00"), Decimal("100.00")), "D")
        self.assertEqual(calculate_letter_grade(Decimal("42.00"), Decimal("100.00")), "F")

    def test_teacher_subject_authorization(self):
        """Teacher must be assigned to subject/classroom to perform academic actions."""
        # prof_gauss is assigned to Mathematics in classroom
        self.assertTrue(is_teacher_authorized_for_subject(self.teacher, self.classroom, "Mathematics"))
        # prof_gauss is NOT assigned to Physics
        self.assertFalse(is_teacher_authorized_for_subject(self.teacher, self.classroom, "Physics"))
        # prof_euler is NOT assigned to Mathematics in classroom
        self.assertFalse(is_teacher_authorized_for_subject(self.other_teacher, self.classroom, "Mathematics"))
        # Admin bypasses authorization
        self.assertTrue(is_teacher_authorized_for_subject(self.admin_user, self.classroom, "Physics"))

    def test_study_material_upload_and_access(self):
        """Authorized teacher can upload notes; student can view them."""
        dummy_file = SimpleUploadedFile("lecture1.pdf", b"%PDF-1.4 notes content", content_type="application/pdf")
        material = StudyMaterial.objects.create(
            classroom=self.classroom,
            subject_name="Mathematics",
            teacher=self.teacher,
            title="Algebra Basics",
            description="Introduction to quadratic equations",
            file=dummy_file,
        )
        self.assertEqual(material.subject_name, "Mathematics")
        self.assertEqual(material.classroom, self.classroom)

        # Student enrolled in classroom can view materials
        self.client.force_login(self.student)
        response = self.client.get(reverse("academics:student_materials"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Algebra Basics")

    def test_assignment_submission_and_late_detection(self):
        """Test coursework submission, enrollment restriction, and late tracking."""
        # 1. On-time assignment
        due_future = timezone.now() + timedelta(days=5)
        assignment_ontime = Assignment.objects.create(
            classroom=self.classroom,
            subject_name="Mathematics",
            teacher=self.teacher,
            title="Problem Set 1",
            description="Complete exercises 1 to 10",
            max_score=Decimal("50.00"),
            due_datetime=due_future,
            is_published=True,
        )

        sub_file = SimpleUploadedFile("hw1.pdf", b"%PDF-1.4 student answer", content_type="application/pdf")
        submission = submit_student_assignment(
            assignment=assignment_ontime,
            student=self.student,
            submission_file=sub_file,
            notes="Ready for review",
        )
        self.assertFalse(submission.is_late)
        self.assertEqual(submission.assignment, assignment_ontime)

        # 2. Past due assignment
        due_past = timezone.now() - timedelta(days=1)
        assignment_past = Assignment.objects.create(
            classroom=self.classroom,
            subject_name="Mathematics",
            teacher=self.teacher,
            title="Problem Set 0",
            description="Warmup exercises",
            max_score=Decimal("20.00"),
            due_datetime=due_past,
            is_published=True,
        )
        sub_file_late = SimpleUploadedFile("hw0.pdf", b"%PDF-1.4 late answer", content_type="application/pdf")
        submission_late = submit_student_assignment(
            assignment=assignment_past,
            student=self.student,
            submission_file=sub_file_late,
        )
        self.assertTrue(submission_late.is_late)

        # 3. Unenrolled student cannot submit
        sub_file_other = SimpleUploadedFile("bob.pdf", b"%PDF-1.4 answer", content_type="application/pdf")
        with self.assertRaises(PermissionDenied):
            submit_student_assignment(
                assignment=assignment_ontime,
                student=self.other_student,
                submission_file=sub_file_other,
            )

    def test_assignment_grading_and_score_bounds(self):
        """Test teacher evaluation of coursework with score bounds."""
        due_future = timezone.now() + timedelta(days=3)
        assignment = Assignment.objects.create(
            classroom=self.classroom,
            subject_name="Mathematics",
            teacher=self.teacher,
            title="Geometry Proofs",
            description="Prove theorem 1",
            max_score=Decimal("40.00"),
            due_datetime=due_future,
            is_published=True,
        )
        sub_file = SimpleUploadedFile("proofs.pdf", b"%PDF-1.4 content", content_type="application/pdf")
        submission = submit_student_assignment(assignment, self.student, sub_file)

        # Score exceeding max score fails
        with self.assertRaises(ValidationError):
            grade_assignment_submission(submission, self.teacher, Decimal("45.00"), "Too high")

        # Negative score fails
        with self.assertRaises(ValidationError):
            grade_assignment_submission(submission, self.teacher, Decimal("-5.00"), "Negative")

        # Unauthorized teacher cannot grade
        with self.assertRaises(PermissionDenied):
            grade_assignment_submission(submission, self.other_teacher, Decimal("35.00"))

        # Valid grading
        graded = grade_assignment_submission(submission, self.teacher, Decimal("38.00"), "Excellent proof!")
        self.assertEqual(graded.score, Decimal("38.00"))
        self.assertEqual(graded.graded_by, self.teacher)
        self.assertIsNotNone(graded.graded_at)

    def test_assessment_confidentiality_and_publication(self):
        """
        Confidential assessment marks must remain hidden from students and parents
        until explicitly published by an authorized teacher.
        """
        # Create draft assessment (is_published=False)
        assessment = Assessment.objects.create(
            classroom=self.classroom,
            subject_name="Mathematics",
            teacher=self.teacher,
            title="Midterm Exam 2026",
            assessment_type=AssessmentType.MIDTERM,
            max_marks=Decimal("100.00"),
            weightage_percent=Decimal("30.00"),
            date_conducted=timezone.now().date(),
            is_published=False,
        )

        # Teacher enters student score
        score = enter_student_assessment_score(
            assessment=assessment,
            student=self.student,
            marks_obtained=Decimal("92.50"),
            entered_by=self.teacher,
            teacher_remarks="Outstanding analytical work.",
        )
        self.assertEqual(score.grade, "A+")
        self.assertEqual(score.marks_obtained, Decimal("92.50"))

        # 1. Verify confidential status: Student cannot see unpublished marks
        self.client.force_login(self.student)
        res_stud = self.client.get(reverse("academics:student_results"))
        self.assertEqual(res_stud.status_code, 200)
        self.assertNotContains(res_stud, "Midterm Exam 2026")
        self.assertNotContains(res_stud, "92.50")

        # 2. Verify confidential status: Parent cannot see unpublished marks
        self.client.force_login(self.parent)
        res_par = self.client.get(reverse("academics:parent_child_academics"))
        self.assertEqual(res_par.status_code, 200)
        self.assertNotContains(res_par, "Midterm Exam 2026")
        self.assertNotContains(res_par, "92.50")

        # 3. Publish results
        publish_assessment_results(assessment, self.teacher)
        self.assertTrue(assessment.is_published)

        # 4. Now student can see their official grade
        self.client.force_login(self.student)
        res_stud_pub = self.client.get(reverse("academics:student_results"))
        self.assertContains(res_stud_pub, "Midterm Exam 2026")
        self.assertContains(res_stud_pub, "92.50")
        self.assertContains(res_stud_pub, "A+")

        # 5. Linked parent can also see the official grade
        self.client.force_login(self.parent)
        res_par_pub = self.client.get(reverse("academics:parent_child_academics"))
        self.assertContains(res_par_pub, "Midterm Exam 2026")
        self.assertContains(res_par_pub, "92.50")

        # 6. Unrelated parent cannot see Alice's scores
        self.client.force_login(self.other_parent)
        res_other_par = self.client.get(reverse("academics:parent_child_academics"))
        self.assertNotContains(res_other_par, "92.50")

    def test_student_faculty_doubt_workflow(self):
        """Test real Q&A doubt submission and teacher response."""
        doubt = StudentDoubt.objects.create(
            classroom=self.classroom,
            subject_name="Mathematics",
            student=self.student,
            assigned_teacher=self.teacher,
            question_title="Derivation of Quadratic Formula",
            question_text="Could you explain step 3 where we complete the square?",
        )
        self.assertFalse(doubt.is_resolved)

        # Teacher answers doubt
        answer_student_doubt(
            doubt=doubt,
            answer_text="In step 3, we add (b/2a)^2 to both sides of the equation to form a perfect square trinomial.",
            teacher=self.teacher,
        )
        doubt.refresh_from_db()
        self.assertTrue(doubt.is_resolved)
        self.assertEqual(doubt.answered_by, self.teacher)
        self.assertIn("perfect square trinomial", doubt.answer_text)

        # Student checks doubts page and sees answer
        self.client.force_login(self.student)
        response = self.client.get(reverse("academics:student_doubts"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Derivation of Quadratic Formula")
        self.assertContains(response, "perfect square trinomial")

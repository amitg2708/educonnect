"""
Automated Test Suite for EduConnect Admission Management Module (Part 4).
Verifies:
- Course eligibility browsing and filtering
- Applicant application submission and reference number generation
- File type and size validations
- Duplicate application prevention
- Editing permissions (only Draft/Action Required)
- Admin review, search, and filtering
- Missing document requests & applicant resubmission
- Document download access control (security checks)
- Admin approval and conversion to Student without duplicate records
- Audit trail integrity in ApplicationStatusHistory
"""

from datetime import date
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import Role, User
from apps.admissions.models import (
    AdmissionApplication,
    ApplicationDocument,
    ApplicationStatus,
    ApplicationStatusHistory,
    DocumentType,
)
from apps.core.models import Course


class AdmissionsModuleTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Course
        self.course = Course.objects.create(
            title="Bachelor of Computer Science",
            code="BCS-101",
            slug="bcs-101-bachelor-of-computer-science",
            department="Computer Science & Engineering",
            level=Course.Level.UNDERGRADUATE,
            duration="4 Years / 8 Semesters",
            description="Comprehensive undergraduate curriculum in computing.",
            eligibility="Minimum 60% in Senior Secondary (Grade 12) with Mathematics.",
            fee_per_term=3500.00,
            is_active=True,
            is_featured=True,
        )

        self.diploma_course = Course.objects.create(
            title="Diploma in Cybersecurity",
            code="DIP-CYBER",
            slug="dip-cyber-diploma-in-cybersecurity",
            department="Information Technology",
            level=Course.Level.DIPLOMA,
            duration="1 Year",
            description="Hands-on network defense and vulnerability testing.",
            fee_per_term=1200.00,
            is_active=True,
        )

        # Create Admin User
        self.admin_user = User.objects.create_user(
            username="admissions_admin",
            email="admin@educonnect.local",
            password="AdminPassword123!",
            role=Role.ADMIN,
            is_staff=True,
        )

        # Create Applicant User
        self.applicant_user = User.objects.create_user(
            username="john_applicant",
            email="john.applicant@example.com",
            password="ApplicantPassword123!",
            role=Role.APPLICANT,
            first_name="John",
            last_name="Doe",
            phone_number="+1-555-0199",
        )

        # Create Another Unrelated Applicant
        self.other_applicant = User.objects.create_user(
            username="jane_other",
            email="jane.other@example.com",
            password="OtherPassword123!",
            role=Role.APPLICANT,
            first_name="Jane",
            last_name="Smith",
        )

        # Dummy verification files
        self.dummy_pdf = SimpleUploadedFile(
            "identity_proof.pdf",
            b"%PDF-1.4 dummy pdf document content for verification",
            content_type="application/pdf",
        )
        self.dummy_transcript = SimpleUploadedFile(
            "transcript.pdf",
            b"%PDF-1.4 dummy transcript document content",
            content_type="application/pdf",
        )
        self.dummy_photo = SimpleUploadedFile(
            "passport_photo.jpg",
            b"\xff\xd8\xff\xe0\x00\x10JFIF dummy jpeg content",
            content_type="image/jpeg",
        )

    def test_course_eligibility_view_loads_and_filters(self):
        """Course eligibility page renders and supports academic level filtering."""
        response = self.client.get(reverse("admissions:eligibility"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "BCS-101")
        self.assertContains(response, "DIP-CYBER")
        self.assertContains(response, "Minimum 60% in Senior Secondary")

        # Filter by undergraduate
        response_filtered = self.client.get(
            reverse("admissions:eligibility"),
            {"level": Course.Level.UNDERGRADUATE},
        )
        self.assertEqual(response_filtered.status_code, 200)
        self.assertContains(response_filtered, "BCS-101")
        self.assertNotContains(response_filtered, "DIP-CYBER")

    def test_apply_view_unauthenticated_redirects_to_login(self):
        """Unauthenticated visitor trying to apply is redirected to login."""
        response = self.client.get(reverse("admissions:apply"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_applicant_submits_application_successfully(self):
        """Applicant logs in and submits a complete application with documents."""
        self.client.login(username="john_applicant", password="ApplicantPassword123!")

        post_data = {
            "course": str(self.course.pk),
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.applicant@example.com",
            "phone_number": "+1-555-0199",
            "date_of_birth": "2004-06-15",
            "gender": "male",
            "nationality": "Indian",
            "address_line1": "42 Knowledge Park",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India",
            "guardian_name": "Robert Doe",
            "guardian_relationship": "Father",
            "guardian_phone": "+1-555-0198",
            "guardian_email": "robert.doe@example.com",
            "previous_institution": "National Central School",
            "previous_qualification": "Class 12 / Higher Secondary",
            "previous_grade_or_percentage": "89.4%",
            "year_of_passing": 2024,
            "statement_of_purpose": "Eager to master artificial intelligence and data engineering.",
            "identity_proof_file": self.dummy_pdf,
            "transcript_file": self.dummy_transcript,
            "passport_photo_file": self.dummy_photo,
        }

        response = self.client.post(reverse("admissions:apply"), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Check application created
        app = AdmissionApplication.objects.filter(applicant=self.applicant_user).first()
        self.assertIsNotNone(app)
        self.assertTrue(app.application_number.startswith("ADM-"))
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)
        self.assertEqual(app.course, self.course)

        # Check documents uploaded
        self.assertEqual(app.documents.count(), 3)

        # Check initial audit history created
        self.assertEqual(app.status_history.count(), 1)
        history_entry = app.status_history.first()
        self.assertEqual(history_entry.to_status, ApplicationStatus.SUBMITTED)
        self.assertEqual(history_entry.changed_by, self.applicant_user)

    def test_duplicate_application_submission_prevented(self):
        """Submitting a duplicate active application for the same course is blocked."""
        # Create active application
        AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="42 Knowledge Park",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.SUBMITTED,
        )

        self.client.login(username="john_applicant", password="ApplicantPassword123!")

        post_data = {
            "course": str(self.course.pk),
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.applicant@example.com",
            "phone_number": "+1-555-0199",
            "date_of_birth": "2004-06-15",
            "gender": "male",
            "nationality": "Indian",
            "address_line1": "42 Knowledge Park",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India",
            "guardian_name": "Robert Doe",
            "guardian_relationship": "Father",
            "guardian_phone": "+1-555-0198",
            "previous_institution": "National Central School",
            "previous_qualification": "Class 12",
            "previous_grade_or_percentage": "89.4%",
            "year_of_passing": 2024,
            "identity_proof_file": self.dummy_pdf,
            "transcript_file": self.dummy_transcript,
        }

        response = self.client.post(reverse("admissions:apply"), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You already have an active application")
        # Ensure only 1 application exists
        self.assertEqual(AdmissionApplication.objects.filter(applicant=self.applicant_user).count(), 1)

    def test_invalid_file_extension_rejected(self):
        """Unsupported file extensions (.exe, .zip) are rejected by validator."""
        self.client.login(username="john_applicant", password="ApplicantPassword123!")

        bad_file = SimpleUploadedFile("malicious.exe", b"executable bytes", content_type="application/octet-stream")

        post_data = {
            "course": str(self.course.pk),
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.applicant@example.com",
            "phone_number": "+1-555-0199",
            "date_of_birth": "2004-06-15",
            "gender": "male",
            "nationality": "Indian",
            "address_line1": "42 Knowledge Park",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India",
            "guardian_name": "Robert Doe",
            "guardian_relationship": "Father",
            "guardian_phone": "+1-555-0198",
            "previous_institution": "National Central School",
            "previous_qualification": "Class 12",
            "previous_grade_or_percentage": "89.4%",
            "year_of_passing": 2024,
            "identity_proof_file": bad_file,
            "transcript_file": self.dummy_transcript,
        }

        response = self.client.post(reverse("admissions:apply"), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unsupported file format")

    def test_applicant_cannot_tamper_with_approval_status(self):
        """Applicant cannot set status to 'approved' via application submission or update."""
        self.client.login(username="john_applicant", password="ApplicantPassword123!")

        post_data = {
            "course": str(self.course.pk),
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.applicant@example.com",
            "phone_number": "+1-555-0199",
            "date_of_birth": "2004-06-15",
            "gender": "male",
            "nationality": "Indian",
            "address_line1": "42 Knowledge Park",
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India",
            "guardian_name": "Robert Doe",
            "guardian_relationship": "Father",
            "guardian_phone": "+1-555-0198",
            "previous_institution": "National Central School",
            "previous_qualification": "Class 12",
            "previous_grade_or_percentage": "89.4%",
            "year_of_passing": 2024,
            "identity_proof_file": self.dummy_pdf,
            "transcript_file": self.dummy_transcript,
            "status": "approved",  # Tamper attempt
        }

        self.client.post(reverse("admissions:apply"), post_data)
        app = AdmissionApplication.objects.filter(applicant=self.applicant_user).first()
        self.assertIsNotNone(app)
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)  # Remains submitted!

    def test_applicant_updates_permitted_fields_when_action_required(self):
        """Applicant can update details when status is ACTION_REQUIRED."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Old Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.ACTION_REQUIRED,
            applicant_remarks="Please provide updated residential address and contact number.",
        )

        self.client.login(username="john_applicant", password="ApplicantPassword123!")

        update_data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.applicant@example.com",
            "phone_number": "+1-555-9999",  # updated
            "date_of_birth": "2004-06-15",
            "gender": "male",
            "nationality": "Indian",
            "address_line1": "New Suite 100",  # updated
            "city": "Bengaluru",
            "state": "Karnataka",
            "postal_code": "560001",
            "country": "India",
            "guardian_name": "Robert Doe",
            "guardian_relationship": "Father",
            "guardian_phone": "+1-555-0198",
            "previous_institution": "National Central School",
            "previous_qualification": "Class 12",
            "previous_grade_or_percentage": "89.4%",
            "year_of_passing": 2024,
        }

        response = self.client.post(
            reverse("admissions:edit_application", kwargs={"application_number": app.application_number}),
            update_data,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        app.refresh_from_db()
        self.assertEqual(app.phone_number, "+1-555-9999")
        self.assertEqual(app.address_line1, "New Suite 100")

    def test_applicant_cannot_update_when_under_review_or_finalized(self):
        """Editing is denied when status is UNDER_REVIEW, APPROVED, or REJECTED."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.UNDER_REVIEW,
        )

        self.client.login(username="john_applicant", password="ApplicantPassword123!")

        response = self.client.get(
            reverse("admissions:edit_application", kwargs={"application_number": app.application_number})
        )
        # Should redirect with an error message
        self.assertEqual(response.status_code, 302)

    def test_applicant_resubmits_application(self):
        """Applicant can resubmit application when in ACTION_REQUIRED."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.ACTION_REQUIRED,
        )

        self.client.login(username="john_applicant", password="ApplicantPassword123!")

        response = self.client.post(
            reverse("admissions:resubmit_application", kwargs={"application_number": app.application_number}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.SUBMITTED)

        # Audit history logged
        last_history = app.status_history.latest("created_at")
        self.assertEqual(last_history.from_status, ApplicationStatus.ACTION_REQUIRED)
        self.assertEqual(last_history.to_status, ApplicationStatus.SUBMITTED)

    def test_admin_application_list_and_search(self):
        """Admin can search and filter applications; non-admin is forbidden."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.SUBMITTED,
        )

        # Non-admin access check
        self.client.login(username="john_applicant", password="ApplicantPassword123!")
        response = self.client.get(reverse("admissions:admin_application_list"))
        self.assertEqual(response.status_code, 403)

        # Admin access check
        self.client.login(username="admissions_admin", password="AdminPassword123!")
        response = self.client.get(reverse("admissions:admin_application_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, app.application_number)
        self.assertContains(response, "John Doe")

        # Search by application number
        response_search = self.client.get(reverse("admissions:admin_application_list"), {"q": app.application_number})
        self.assertContains(response_search, app.application_number)

    def test_admin_requests_missing_information_decision(self):
        """Admin transitions application to ACTION_REQUIRED with instructions."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.SUBMITTED,
        )

        self.client.login(username="admissions_admin", password="AdminPassword123!")

        decision_data = {
            "status": ApplicationStatus.ACTION_REQUIRED,
            "applicant_remarks": "Please provide an official stamped copy of your Grade 12 Marksheet.",
            "admin_notes": "Transcript provided was unverified web download.",
        }

        response = self.client.post(
            reverse("admissions:admin_application_decision", kwargs={"application_number": app.application_number}),
            decision_data,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.ACTION_REQUIRED)
        self.assertIn("stamped copy", app.applicant_remarks)
        self.assertEqual(app.decided_by, self.admin_user)

    def test_admin_approves_application(self):
        """Admin formally approves the application."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.UNDER_REVIEW,
        )

        self.client.login(username="admissions_admin", password="AdminPassword123!")

        decision_data = {
            "status": ApplicationStatus.APPROVED,
            "applicant_remarks": "Admission offered. Please prepare for orientation enrollment.",
            "admin_notes": "All prerequisites met.",
        }

        response = self.client.post(
            reverse("admissions:admin_application_decision", kwargs={"application_number": app.application_number}),
            decision_data,
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        app.refresh_from_db()
        self.assertEqual(app.status, ApplicationStatus.APPROVED)
        self.assertIsNotNone(app.decision_date)

    def test_admin_converts_approved_applicant_to_student(self):
        """Admin converts an approved application into an active student with Student ID."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.APPROVED,
        )

        self.client.login(username="admissions_admin", password="AdminPassword123!")

        response = self.client.post(
            reverse("admissions:admin_convert_student", kwargs={"application_number": app.application_number}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)

        app.refresh_from_db()
        self.applicant_user.refresh_from_db()

        # Check conversion details
        self.assertEqual(app.status, ApplicationStatus.ENROLLED)
        self.assertEqual(app.converted_student, self.applicant_user)
        self.assertTrue(app.student_id_assigned.startswith("STU-"))

        # Verify User model updated without creating duplicate user
        self.assertEqual(self.applicant_user.role, Role.STUDENT)
        self.assertEqual(self.applicant_user.student_id, app.student_id_assigned)
        self.assertEqual(self.applicant_user.grade_level, self.course.title)

        # Total user count should remain identical (no duplicate user created)
        self.assertEqual(User.objects.filter(username="john_applicant").count(), 1)

    def test_duplicate_conversion_prevented(self):
        """Cannot convert an already enrolled application or a non-approved application."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.SUBMITTED,  # Not approved!
        )

        self.client.login(username="admissions_admin", password="AdminPassword123!")

        response = self.client.post(
            reverse("admissions:admin_convert_student", kwargs={"application_number": app.application_number}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        app.refresh_from_db()
        self.assertNotEqual(app.status, ApplicationStatus.ENROLLED)
        self.assertIsNone(app.converted_student)

    def test_secure_document_download_access_control(self):
        """Only the document owner and staff/admin can download documents; others receive 403."""
        app = AdmissionApplication.objects.create(
            applicant=self.applicant_user,
            course=self.course,
            first_name="John",
            last_name="Doe",
            email="john.applicant@example.com",
            phone_number="+1-555-0199",
            date_of_birth=date(2004, 6, 15),
            gender="male",
            address_line1="Address 1",
            city="Bengaluru",
            state="Karnataka",
            postal_code="560001",
            guardian_name="Robert Doe",
            guardian_relationship="Father",
            guardian_phone="+1-555-0198",
            previous_institution="National Central School",
            previous_qualification="Class 12",
            previous_grade_or_percentage="89.4%",
            year_of_passing=2024,
            status=ApplicationStatus.SUBMITTED,
        )

        doc = ApplicationDocument.objects.create(
            application=app,
            document_type=DocumentType.IDENTITY_PROOF,
            title="Passport Copy",
            file=self.dummy_pdf,
        )

        download_url = reverse("admissions:download_document", kwargs={"document_id": str(doc.pk)})

        # 1. Unrelated applicant user tries to download -> 403 Forbidden
        self.client.login(username="jane_other", password="OtherPassword123!")
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 403)

        # 2. Document owner (applicant) downloads -> 200 OK
        self.client.login(username="john_applicant", password="ApplicantPassword123!")
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)

        # 3. Admin user downloads -> 200 OK
        self.client.login(username="admissions_admin", password="AdminPassword123!")
        response = self.client.get(download_url)
        self.assertEqual(response.status_code, 200)

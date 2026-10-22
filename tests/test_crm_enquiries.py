"""
Acceptance Tests for Antigravity Task 3:
Coaching Enquiries and Admissions CRM in EduConnect.

Acceptance Test Requirements:
- Submit a website enquiry.
- Assign it to authorized staff.
- Record a follow-up.
- Convert an approved applicant to a student.
- Enrol the student into a batch.
- Verify that duplicate accounts are not created.
- Confirm that another institute cannot access the enquiry.
"""

from datetime import date, time, timedelta
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.attendance.models import AcademicSession, ClassRoom
from apps.academics.models import Batch, BatchEnrollment
from apps.academics.services import enroll_student_in_batch
from apps.admissions.models import (
    AdmissionApplication,
    ApplicationStatus,
    ApplicationStatusHistory,
    Enquiry,
    EnquiryFollowUp,
    EnquirySource,
    EnquiryStatus,
)
from apps.core.models import Course
from apps.institutions.models import Branch, Institution, InstitutionMembership


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CoachingEnquiriesAndAdmissionsCRMTestCase(TestCase):
    """
    Acceptance test suite for Coaching Enquiries CRM, pipeline tracking,
    batch enrolment, account deduplication, and multi-tenant security isolation.
    """

    def setUp(self):
        # 1. Primary Institution (Apex Coaching Academy)
        self.institution = Institution.objects.create(
            name="Apex Coaching Academy",
            code="APEX",
            slug="apex-coaching",
            subdomain="apex",
            is_active=True,
        )
        self.branch = Branch.objects.create(
            institution=self.institution,
            name="Apex North Campus",
            code="APEX-NORTH",
            city="Pune",
            is_active=True,
        )

        # 2. Staff Users for Apex
        self.admin_user = User.objects.create_user(
            username="apex_admin",
            email="admin@apexcoaching.com",
            first_name="Apex",
            last_name="Administrator",
            role=Role.ADMIN,
            institution=self.institution,
        )
        self.admin_user.set_password("adminpass123")
        self.admin_user.save()

        self.counselor_user = User.objects.create_user(
            username="counselor_priya",
            email="priya@apexcoaching.com",
            first_name="Priya",
            last_name="Sharma",
            role=Role.TEACHER,
            institution=self.institution,
        )
        self.counselor_user.set_password("teacherpass123")
        self.counselor_user.save()

        # 3. Second Institution for Cross-Tenant Isolation Tests (Zenith Institute)
        self.other_institution = Institution.objects.create(
            name="Zenith Competitions Institute",
            code="ZENITH",
            slug="zenith-institute",
            subdomain="zenith",
            is_active=True,
        )
        self.other_admin = User.objects.create_user(
            username="zenith_admin",
            email="admin@zenithinstitute.com",
            first_name="Zenith",
            last_name="Admin",
            role=Role.ADMIN,
            institution=self.other_institution,
        )
        self.other_admin.set_password("zenithpass123")
        self.other_admin.save()

        # 4. Academic Setup at Apex
        self.session = AcademicSession.objects.create(
            institution=self.institution,
            name="2026-2027 Academic Session",
            start_date=date(2026, 4, 1),
            end_date=date(2027, 3, 31),
            is_current=True,
        )
        self.classroom = ClassRoom.objects.create(
            institution=self.institution,
            branch=self.branch,
            academic_session=self.session,
            name="Room 101 - Lecture Theatre",
            code="R101",
            capacity=40,
        )
        self.course = Course.objects.create(
            institution=self.institution,
            title="Class 10 Board Intensive & Olympiad",
            code="C10-BOARDS",
            slug="class-10-boards",
            is_active=True,
        )
        self.batch = Batch.objects.create(
            institution=self.institution,
            branch=self.branch,
            academic_session=self.session,
            course=self.course,
            name="Class 10 Morning Star Cohort",
            code="C10-MORN-2026",
            classroom=self.classroom,
            capacity=30,
            status=Batch.Status.ONGOING,
            start_date=date(2026, 4, 15),
            end_date=date(2027, 2, 28),
        )

        self.client = Client()

    def test_01_submit_website_enquiry(self):
        """
        Criteria: Submit a website enquiry.
        Anonymous prospective student/parent submits inquiry on public institute portal.
        """
        url = reverse("admissions:public_enquiry")
        payload = {
            "name": "Arjun Verma",
            "email": "arjun.verma@example.com",
            "phone": "+91 98765 11111",
            "alternate_phone": "+91 98765 22222",
            "city": "Pune",
            "target_class": "Class 10",
            "stream": "Science",
            "course": self.course.pk,
            "batch_interest": self.batch.pk,
            "notes": "Looking for board prep revision and weekend doubt clearing sessions.",
        }

        # Anonymous visitor posts to public enquiry endpoint
        response = self.client.post(f"{url}?inst={self.institution.slug}", data=payload)
        self.assertEqual(response.status_code, 200)

        # Verify Enquiry persisted in database
        enquiry = Enquiry.objects.filter(email="arjun.verma@example.com").first()
        self.assertIsNotNone(enquiry, "Enquiry record should be created in database.")
        self.assertEqual(enquiry.institution, self.institution)
        self.assertEqual(enquiry.source, EnquirySource.WEBSITE)
        self.assertEqual(enquiry.status, EnquiryStatus.NEW)
        self.assertEqual(enquiry.name, "Arjun Verma")
        self.assertEqual(enquiry.phone, "+91 98765 11111")
        self.assertEqual(enquiry.course, self.course)
        self.assertEqual(enquiry.batch_interest, self.batch)
        self.assertTrue(enquiry.enquiry_number.startswith("ENQ-"))

        # Verify initial follow-up interaction logged
        self.assertEqual(enquiry.follow_ups.count(), 1)
        initial_log = enquiry.follow_ups.first()
        self.assertEqual(initial_log.new_status, EnquiryStatus.NEW)
        self.assertIn("website", initial_log.notes.lower())

    def test_02_assign_enquiry_to_authorized_staff(self):
        """
        Criteria: Assign it to authorized staff.
        Enquiry counselor ownership and next follow-up scheduling.
        """
        enquiry = Enquiry.objects.create(
            institution=self.institution,
            branch=self.branch,
            source=EnquirySource.PHONE,
            name="Sneha Patil",
            email="sneha.patil@example.com",
            phone="+91 98765 33333",
            course=self.course,
            status=EnquiryStatus.NEW,
        )

        self.client.login(username="apex_admin", password="adminpass123")
        assign_url = reverse("admissions:admin_enquiry_assign", kwargs={"enquiry_number": enquiry.enquiry_number})

        next_date = (timezone.now() + timedelta(days=2)).date()
        payload = {
            "assigned_to": self.counselor_user.pk,
            "next_follow_up_date": next_date.isoformat(),
            "assignment_note": "Please call parent regarding Science scholarship test.",
        }

        response = self.client.post(assign_url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        enquiry.refresh_from_db()
        self.assertEqual(enquiry.assigned_to, self.counselor_user)
        self.assertEqual(enquiry.next_follow_up_date, next_date)

        # Verify assignment was recorded in follow-up history
        assignment_history = enquiry.follow_ups.filter(notes__icontains="Priya Sharma").first()
        self.assertIsNotNone(assignment_history, "Assignment event must be recorded in follow-up timeline.")
        self.assertEqual(assignment_history.staff, self.admin_user)

    def test_03_record_followup_and_status_progression(self):
        """
        Criteria: Record a follow-up.
        Counselor records telephone interaction, transitions status to Trial Class,
        and schedules next follow-up.
        """
        enquiry = Enquiry.objects.create(
            institution=self.institution,
            source=EnquirySource.WALK_IN,
            name="Rohan Joshi",
            email="rohan.joshi@example.com",
            phone="+91 98765 44444",
            course=self.course,
            batch_interest=self.batch,
            assigned_to=self.counselor_user,
            status=EnquiryStatus.CONTACTED,
        )

        self.client.login(username="counselor_priya", password="teacherpass123")
        followup_url = reverse("admissions:admin_enquiry_followup", kwargs={"enquiry_number": enquiry.enquiry_number})

        next_followup = (timezone.now() + timedelta(days=3)).date()
        payload = {
            "contact_mode": "phone",
            "notes": "Discussed batch timing with father. Student will attend Physics trial class on Saturday.",
            "new_status": EnquiryStatus.TRIAL_CLASS,
            "scheduled_follow_up_date": next_followup.isoformat(),
        }

        response = self.client.post(followup_url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        enquiry.refresh_from_db()
        self.assertEqual(enquiry.status, EnquiryStatus.TRIAL_CLASS)
        self.assertEqual(enquiry.next_follow_up_date, next_followup)

        # Check follow-up model record
        followup_rec = enquiry.follow_ups.latest("created_at")
        self.assertEqual(followup_rec.staff, self.counselor_user)
        self.assertEqual(followup_rec.contact_mode, "phone")
        self.assertEqual(followup_rec.old_status, EnquiryStatus.CONTACTED)
        self.assertEqual(followup_rec.new_status, EnquiryStatus.TRIAL_CLASS)
        self.assertIn("Physics trial class", followup_rec.notes)

    def test_04_convert_approved_applicant_to_student(self):
        """
        Criteria: Convert an approved applicant to a student.
        Verifies student account role change, student ID assignment, and status transition to Enrolled.
        """
        # Create applicant user
        applicant_user = User.objects.create_user(
            username="kavita_applicant",
            email="kavita.deshmukh@example.com",
            first_name="Kavita",
            last_name="Deshmukh",
            role=Role.APPLICANT,
            institution=self.institution,
        )
        applicant_user.set_password("apppass123")
        applicant_user.save()

        # Create approved admission application
        application = AdmissionApplication.objects.create(
            institution=self.institution,
            applicant=applicant_user,
            course=self.course,
            first_name="Kavita",
            last_name="Deshmukh",
            email="kavita.deshmukh@example.com",
            phone_number="+91 98765 55555",
            date_of_birth=date(2010, 5, 20),
            gender="female",
            address_line1="12 Model Colony",
            city="Pune",
            state="Maharashtra",
            postal_code="411016",
            guardian_name="Sanjay Deshmukh",
            guardian_relationship="Father",
            guardian_phone="+91 98765 66666",
            previous_institution="St. Mary School",
            previous_qualification="Class 9",
            previous_grade_or_percentage="92%",
            year_of_passing=2025,
            status=ApplicationStatus.APPROVED,
        )

        self.client.login(username="apex_admin", password="adminpass123")
        convert_url = reverse("admissions:admin_convert_student", kwargs={"application_number": application.application_number})

        response = self.client.post(convert_url, follow=True)
        self.assertEqual(response.status_code, 200)

        application.refresh_from_db()
        applicant_user.refresh_from_db()

        # Check conversion outcomes
        self.assertEqual(application.status, ApplicationStatus.ENROLLED)
        self.assertEqual(application.converted_student, applicant_user)
        self.assertTrue(bool(application.student_id_assigned))
        self.assertTrue(application.student_id_assigned.startswith("STU-"))
        self.assertEqual(applicant_user.role, Role.STUDENT)
        self.assertEqual(applicant_user.student_id, application.student_id_assigned)

        # Verify audit history
        latest_audit = application.status_history.latest("created_at")
        self.assertEqual(latest_audit.to_status, ApplicationStatus.ENROLLED)
        self.assertEqual(latest_audit.changed_by, self.admin_user)

    def test_05_enrol_student_into_batch_during_conversion(self):
        """
        Criteria: Enrol the student into a batch.
        Conversion of approved application automatically registers student into coaching batch.
        """
        applicant_user = User.objects.create_user(
            username="manish_applicant",
            email="manish.nair@example.com",
            first_name="Manish",
            last_name="Nair",
            role=Role.APPLICANT,
            institution=self.institution,
        )

        # Link to originating enquiry
        enquiry = Enquiry.objects.create(
            institution=self.institution,
            source=EnquirySource.REFERRAL,
            name="Manish Nair",
            email="manish.nair@example.com",
            phone="+91 98765 77777",
            course=self.course,
            batch_interest=self.batch,
            status=EnquiryStatus.FOLLOW_UP_REQUIRED,
        )

        application = AdmissionApplication.objects.create(
            institution=self.institution,
            applicant=applicant_user,
            course=self.course,
            target_batch=self.batch,
            source_enquiry=enquiry,
            first_name="Manish",
            last_name="Nair",
            email="manish.nair@example.com",
            phone_number="+91 98765 77777",
            date_of_birth=date(2010, 8, 12),
            gender="male",
            address_line1="45 FC Road",
            city="Pune",
            state="Maharashtra",
            postal_code="411005",
            guardian_name="Gopal Nair",
            guardian_relationship="Father",
            guardian_phone="+91 98765 88888",
            previous_institution="Loyola High School",
            previous_qualification="Class 9",
            previous_grade_or_percentage="88%",
            year_of_passing=2025,
            status=ApplicationStatus.APPROVED,
        )

        self.client.login(username="apex_admin", password="adminpass123")
        convert_url = reverse("admissions:admin_convert_student", kwargs={"application_number": application.application_number})

        payload = {
            "target_batch": self.batch.pk,
            "roll_number": "C10-09",
        }
        response = self.client.post(convert_url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        application.refresh_from_db()
        applicant_user.refresh_from_db()
        enquiry.refresh_from_db()

        # Verify batch enrolment
        enrollment = BatchEnrollment.objects.filter(
            institution=self.institution,
            student=applicant_user,
            batch=self.batch,
        ).first()
        self.assertIsNotNone(enrollment, "Student must be actively enrolled in the selected batch.")
        self.assertEqual(enrollment.status, BatchEnrollment.Status.ACTIVE)
        self.assertEqual(enrollment.roll_number, "C10-09")
        self.assertEqual(application.target_batch, self.batch)

        # Verify linked enquiry is marked CONVERTED
        self.assertEqual(enquiry.status, EnquiryStatus.CONVERTED)
        self.assertEqual(enquiry.converted_student, applicant_user)
        self.assertEqual(enquiry.converted_application, application)
        self.assertIsNotNone(enquiry.converted_at)

    def test_06_prevent_duplicate_accounts_when_converting(self):
        """
        Criteria: Verify that duplicate accounts are not created.
        If an existing person is identified by email, the system uses a verified
        account-linking process instead of provisioning a duplicate User record.
        """
        # Pre-existing student account in system
        existing_student = User.objects.create_user(
            username="existing_tanvi",
            email="tanvi.shah@example.com",
            first_name="Tanvi",
            last_name="Shah",
            role=Role.STUDENT,
            student_id="STU-2025-EXISTING",
            institution=self.institution,
        )

        user_count_before = User.objects.filter(email__iexact="tanvi.shah@example.com").count()
        self.assertEqual(user_count_before, 1)

        # Suppose Tanvi or parent applies for a new course with an applicant proxy account
        proxy_applicant = User.objects.create_user(
            username="tanvi_proxy_applicant",
            email="temp.applicant.handle@example.com",
            first_name="Tanvi",
            last_name="Shah",
            role=Role.APPLICANT,
            institution=self.institution,
        )

        application = AdmissionApplication.objects.create(
            institution=self.institution,
            applicant=proxy_applicant,
            course=self.course,
            first_name="Tanvi",
            last_name="Shah",
            email="tanvi.shah@example.com",  # Matches existing student email!
            phone_number="+91 98765 99999",
            date_of_birth=date(2010, 11, 25),
            gender="female",
            address_line1="77 Bhandarkar Road",
            city="Pune",
            state="Maharashtra",
            postal_code="411004",
            guardian_name="Deepak Shah",
            guardian_relationship="Father",
            guardian_phone="+91 98765 00000",
            previous_institution="Vikhe Patil Memorial",
            previous_qualification="Class 9",
            previous_grade_or_percentage="95%",
            year_of_passing=2025,
            status=ApplicationStatus.APPROVED,
        )

        self.client.login(username="apex_admin", password="adminpass123")
        convert_url = reverse("admissions:admin_convert_student", kwargs={"application_number": application.application_number})

        response = self.client.post(convert_url, data={"target_batch": self.batch.pk}, follow=True)
        self.assertEqual(response.status_code, 200)

        # Critical Assertion: NO duplicate user account created
        user_count_after = User.objects.filter(email__iexact="tanvi.shah@example.com").count()
        self.assertEqual(
            user_count_after,
            1,
            "Prevent duplicate student accounts: User table must not contain duplicate accounts for same email.",
        )

        application.refresh_from_db()
        self.assertEqual(
            application.converted_student,
            existing_student,
            "Existing student user must be linked as converted_student.",
        )
        self.assertEqual(application.student_id_assigned, "STU-2025-EXISTING")

        # Verify existing student has valid institution membership and batch enrollment
        membership = InstitutionMembership.objects.filter(
            institution=self.institution,
            user=existing_student,
            role=Role.STUDENT,
        ).first()
        self.assertIsNotNone(membership)

        enrollment = BatchEnrollment.objects.filter(student=existing_student, batch=self.batch).first()
        self.assertIsNotNone(enrollment, "Existing student must be enrolled into batch.")

    def test_07_cross_institute_enquiry_isolation(self):
        """
        Criteria: Confirm that another institute cannot access the enquiry.
        Strict multi-tenant security verification: Zenith Institute staff is blocked
        from viewing, updating, or listing Apex Institute's enquiries.
        """
        # Create enquiry belonging to Apex Coaching
        apex_enquiry = Enquiry.objects.create(
            institution=self.institution,
            source=EnquirySource.WEBSITE,
            name="Confidential Lead",
            email="secret.lead@example.com",
            phone="+91 91111 22222",
            course=self.course,
            status=EnquiryStatus.NEW,
        )

        # Log in as Zenith Administrator
        self.client.login(username="zenith_admin", password="zenithpass123")

        # 1. Attempt to view Apex enquiry dossier detail -> Expect 403 Forbidden
        detail_url = reverse("admissions:admin_enquiry_detail", kwargs={"enquiry_number": apex_enquiry.enquiry_number})
        response = self.client.get(detail_url)
        self.assertEqual(
            response.status_code,
            403,
            "Cross-institution access violation: Zenith admin must receive 403 Forbidden when accessing Apex enquiry.",
        )

        # 2. Attempt to record a follow-up on Apex enquiry -> Expect 403 Forbidden
        followup_url = reverse("admissions:admin_enquiry_followup", kwargs={"enquiry_number": apex_enquiry.enquiry_number})
        response = self.client.post(followup_url, data={"contact_mode": "phone", "notes": "Hacked follow-up"})
        self.assertEqual(
            response.status_code,
            403,
            "Cross-institution modification violation: Zenith admin must not be able to log follow-up on Apex enquiry.",
        )

        # 3. Attempt to assign counselor on Apex enquiry -> Expect 403 Forbidden
        assign_url = reverse("admissions:admin_enquiry_assign", kwargs={"enquiry_number": apex_enquiry.enquiry_number})
        response = self.client.post(assign_url, data={"assigned_to": self.other_admin.pk})
        self.assertEqual(
            response.status_code,
            403,
            "Cross-institution assignment violation: Zenith admin must not be able to reassign Apex enquiry.",
        )

        # 4. In Zenith's enquiry directory, Apex enquiry MUST NOT appear
        list_url = reverse("admissions:admin_enquiry_list")
        response = self.client.get(list_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, apex_enquiry.enquiry_number)
        self.assertNotContains(response, "Confidential Lead")

    def test_08_source_wise_enquiry_and_conversion_reports(self):
        """
        Criteria: Source-wise enquiry and conversion reports.
        Validates pipeline reporting grouped by Website, Phone, Walk-in, Referral channels.
        """
        # Create sample leads across sources
        # Website: 2 total, 1 converted
        Enquiry.objects.create(
            institution=self.institution,
            source=EnquirySource.WEBSITE,
            name="Web Lead 1",
            email="web1@example.com",
            phone="11111",
            status=EnquiryStatus.CONVERTED,
        )
        Enquiry.objects.create(
            institution=self.institution,
            source=EnquirySource.WEBSITE,
            name="Web Lead 2",
            email="web2@example.com",
            phone="22222",
            status=EnquiryStatus.NEW,
        )
        # Phone: 1 total, 1 converted
        Enquiry.objects.create(
            institution=self.institution,
            source=EnquirySource.PHONE,
            name="Phone Lead 1",
            email="phone1@example.com",
            phone="33333",
            status=EnquiryStatus.CONVERTED,
        )
        # Walk-in: 1 total, 0 converted
        Enquiry.objects.create(
            institution=self.institution,
            source=EnquirySource.WALK_IN,
            name="Walkin Lead 1",
            email="walk1@example.com",
            phone="44444",
            status=EnquiryStatus.CONTACTED,
        )

        self.client.login(username="apex_admin", password="adminpass123")
        report_url = reverse("admissions:admin_enquiry_reports")
        response = self.client.get(report_url)
        self.assertEqual(response.status_code, 200)

        # Context metrics
        self.assertEqual(response.context["total_leads"], 4)
        self.assertEqual(response.context["total_converted"], 2)
        self.assertEqual(response.context["overall_conv_rate"], 50.0)

        # Source breakdown check
        source_stats = {s["code"]: s for s in response.context["source_stats"]}
        self.assertEqual(source_stats["website"]["count"], 2)
        self.assertEqual(source_stats["website"]["converted"], 1)
        self.assertEqual(source_stats["website"]["rate"], 50.0)

        self.assertEqual(source_stats["phone"]["count"], 1)
        self.assertEqual(source_stats["phone"]["converted"], 1)
        self.assertEqual(source_stats["phone"]["rate"], 100.0)

        self.assertEqual(source_stats["walk_in"]["count"], 1)
        self.assertEqual(source_stats["walk_in"]["converted"], 0)
        self.assertEqual(source_stats["walk_in"]["rate"], 0.0)

    def test_09_direct_enquiry_to_student_conversion(self):
        """
        Verify that an enquiry can be converted directly into an active Student
        and enrolled into a batch with deduplication check.
        """
        enquiry = Enquiry.objects.create(
            institution=self.institution,
            source=EnquirySource.PHONE,
            name="Pooja Kulkarni",
            email="pooja.kulkarni@example.com",
            phone="+91 97777 88888",
            course=self.course,
            batch_interest=self.batch,
            status=EnquiryStatus.TRIAL_CLASS,
        )

        self.client.login(username="apex_admin", password="adminpass123")
        convert_url = reverse("admissions:admin_enquiry_convert", kwargs={"enquiry_number": enquiry.enquiry_number})

        payload = {
            "target_batch": self.batch.pk,
            "roll_number": "C10-15",
        }
        response = self.client.post(convert_url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)

        enquiry.refresh_from_db()
        self.assertEqual(enquiry.status, EnquiryStatus.CONVERTED)
        self.assertIsNotNone(enquiry.converted_student)
        self.assertEqual(enquiry.converted_student.email, "pooja.kulkarni@example.com")
        self.assertEqual(enquiry.converted_student.role, Role.STUDENT)

        # Verify batch enrolment
        enrollment = BatchEnrollment.objects.filter(
            student=enquiry.converted_student,
            batch=self.batch,
        ).first()
        self.assertIsNotNone(enrollment)
        self.assertEqual(enrollment.status, BatchEnrollment.Status.ACTIVE)
        self.assertEqual(enrollment.roll_number, "C10-15")

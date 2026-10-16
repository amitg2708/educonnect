"""
Automated Test Suite for EduConnect Public-Facing Website.
Tests all public routes, page contents, course details, category filters,
and form submissions (Contact & Admissions inquiries).
"""

from decimal import Decimal
from django.test import Client, TestCase
from django.urls import reverse
from apps.core.models import (
    Course,
    Achievement,
    GalleryItem,
    Announcement,
    Facility,
    ContactInquiry,
    AdmissionInquiry,
)


class PublicWebsiteTestCase(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client()

        # Seed sample course
        self.course = Course.objects.create(
            title="Introduction to Robotics & Machine Learning",
            code="ROB-101",
            slug="rob-101-robotics-ml",
            department="School of Computing & Engineering",
            level=Course.Level.UNDERGRADUATE,
            duration="4 Years",
            description="Foundational robotics and artificial intelligence course.",
            eligibility="High school mathematics completion.",
            syllabus_overview="Week 1: Kinematics\nWeek 2: Autonomous Navigation",
            fee_per_term=Decimal("2800.00"),
            is_active=True,
            is_featured=True,
        )

        # Seed sample achievement
        self.achievement = Achievement.objects.create(
            title="International Collegiate Programming Regional Champions",
            category=Achievement.Category.ACADEMIC,
            year=2026,
            recipient="EduConnect Coding Team",
            description="Took top honors in algorithmic programming.",
            is_featured=True,
        )

        # Seed sample gallery item
        self.gallery_item = GalleryItem.objects.create(
            title="Cleanroom Nanotechnology Laboratory",
            category=GalleryItem.Category.LABS,
            caption="Research cleanroom for micro-circuitry fabrication.",
            is_active=True,
        )

        # Seed sample announcement
        self.announcement = Announcement.objects.create(
            title="Admissions Orientation Webinar Scheduled",
            category=Announcement.Category.ADMISSIONS,
            priority=Announcement.Priority.HIGH,
            content="Join us online for an overview of academic programs and financial aid.",
            is_published=True,
        )

        # Seed sample facility
        self.facility = Facility.objects.create(
            title="Student Innovation Incubator",
            category="Entrepreneurship",
            description="Co-working hub for student startup founders.",
            icon="bi-lightbulb",
            display_order=1,
        )

    # --------------------------------------------------------------------------
    # 1. Public Route HTTP 200 & Content Verification
    # --------------------------------------------------------------------------

    def test_home_page_renders_successfully(self):
        """
        Verify Home page / returns 200 and displays hero, notices, and programs.
        """
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Empowering Minds")
        self.assertContains(response, "ROB-101")
        self.assertContains(response, "Introduction to Robotics")
        self.assertContains(response, "Admissions Orientation Webinar")

    def test_about_page_renders_successfully(self):
        """
        Verify About Us /about/ returns 200 and displays mission, vision, values.
        """
        response = self.client.get(reverse("core:about"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Our Mission")
        self.assertContains(response, "Our Vision")
        self.assertContains(response, "Academic Rigor")

    def test_courses_catalog_renders_and_filters(self):
        """
        Verify Courses /courses/ lists programs and filters by level and search query.
        """
        response = self.client.get(reverse("core:courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ROB-101")
        self.assertContains(response, "Explore Our")

        # Test search query
        search_resp = self.client.get(reverse("core:courses"), {"q": "Robotics"})
        self.assertEqual(search_resp.status_code, 200)
        self.assertContains(search_resp, "ROB-101")

        # Test search query with no match
        empty_search_resp = self.client.get(reverse("core:courses"), {"q": "NonExistentSubject999"})
        self.assertEqual(empty_search_resp.status_code, 200)
        self.assertContains(empty_search_resp, "No Courses Found")

    def test_course_detail_page_renders(self):
        """
        Verify Course detail /courses/<slug>/ displays syllabus, eligibility, and fee.
        """
        response = self.client.get(
            reverse("core:course_detail", kwargs={"slug": self.course.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ROB-101")
        self.assertContains(response, "Kinematics")
        self.assertContains(response, "2800.00")

    def test_achievements_page_renders_and_filters(self):
        """
        Verify Achievements /achievements/ returns 200 and filters by category.
        """
        response = self.client.get(reverse("core:achievements"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "International Collegiate Programming")
        self.assertContains(response, "2026")

        # Test category filter
        cat_resp = self.client.get(reverse("core:achievements"), {"category": "academic"})
        self.assertEqual(cat_resp.status_code, 200)
        self.assertContains(cat_resp, "International Collegiate Programming")

        # Test empty category filter
        empty_cat_resp = self.client.get(reverse("core:achievements"), {"category": "arts"})
        self.assertEqual(empty_cat_resp.status_code, 200)
        self.assertContains(empty_cat_resp, "No Achievements Found")

    def test_gallery_page_renders_and_filters(self):
        """
        Verify Gallery /gallery/ returns 200 and filters by category.
        """
        response = self.client.get(reverse("core:gallery"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cleanroom Nanotechnology Laboratory")

        # Test category filter
        cat_resp = self.client.get(reverse("core:gallery"), {"category": "labs"})
        self.assertEqual(cat_resp.status_code, 200)
        self.assertContains(cat_resp, "Cleanroom Nanotechnology Laboratory")

    def test_admissions_page_renders(self):
        """
        Verify Admissions /admissions/ returns 200 and displays roadmap & inquiry form.
        """
        response = self.client.get(reverse("core:admissions"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admissions &amp;")
        self.assertContains(response, "Enrollment")
        self.assertContains(response, "1. Online Inquiry")

    def test_contact_page_renders(self):
        """
        Verify Contact Us /contact/ returns 200 and displays form & campus details.
        """
        response = self.client.get(reverse("core:contact"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Campus Information")
        self.assertContains(response, "100 University Avenue")

    # --------------------------------------------------------------------------
    # 2. Public Form Submissions & Validation
    # --------------------------------------------------------------------------

    def test_contact_form_valid_submission(self):
        """
        Verify valid contact form submission creates ContactInquiry record in database.
        """
        payload = {
            "name": "Jane Public",
            "email": "jane.public@example.com",
            "phone": "+1 (555) 321-7654",
            "subject": "Campus Tour Inquiry",
            "message": "I would like to schedule a guided tour of the STEM laboratories.",
        }
        response = self.client.post(reverse("core:contact"), data=payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Thank you for contacting EduConnect")

        inquiry = ContactInquiry.objects.filter(email="jane.public@example.com").first()
        self.assertIsNotNone(inquiry)
        self.assertEqual(inquiry.name, "Jane Public")
        self.assertEqual(inquiry.subject, "Campus Tour Inquiry")
        self.assertFalse(inquiry.is_resolved)

    def test_contact_form_invalid_submission(self):
        """
        Verify invalid contact form displays validation errors and does not save.
        """
        payload = {
            "name": "",
            "email": "not-an-email",
            "subject": "",
            "message": "short",
        }
        response = self.client.post(reverse("core:contact"), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ContactInquiry.objects.filter(message="short").exists())
        self.assertContains(response, "Please correct the errors")

    def test_admission_inquiry_valid_submission(self):
        """
        Verify valid admission inquiry creates AdmissionInquiry record.
        """
        payload = {
            "applicant_name": "Samuel Applicant",
            "email": "samuel.app@example.com",
            "phone": "+1 (555) 987-6543",
            "target_program": "B.Sc. Computer Science",
            "prior_school": "Westside High School",
            "comments": "Interested in robotics and artificial intelligence research.",
        }
        response = self.client.post(reverse("core:admissions"), data=payload, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your admissions inquiry for")
        self.assertContains(response, "has been received")

        app = AdmissionInquiry.objects.filter(email="samuel.app@example.com").first()
        self.assertIsNotNone(app)
        self.assertEqual(app.applicant_name, "Samuel Applicant")
        self.assertEqual(app.status, AdmissionInquiry.Status.SUBMITTED)

    def test_admission_inquiry_invalid_submission(self):
        """
        Verify missing required fields in admission inquiry are caught by validation.
        """
        payload = {
            "applicant_name": "",
            "email": "bad_email",
            "phone": "",
            "target_program": "",
        }
        response = self.client.post(reverse("core:admissions"), data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AdmissionInquiry.objects.filter(email="bad_email").exists())
        self.assertContains(response, "Please correct the errors")

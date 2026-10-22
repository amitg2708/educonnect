"""
Automated Test Suite for Task 8: Multi-Institute Website & Progressive Web App (PWA).

Verifies all 8 Task 8 acceptance criteria:
1. Each institute's public site shows its own branding (logo, colors, name, notices).
2. Admission forms save records to the correct institute.
3. Login works seamlessly from mobile and desktop user agents.
4. The manifest and service worker load correctly with proper headers and icons.
5. The PWA installation criteria (manifest, icons, service worker, display mode).
6. Offline navigation fallback and clear explanation of internet-dependent operations.
7. Private student, financial, and academic records are never cached or exposed in SW.
8. Safe update strategy: old caches purged on activation without stale/broken assets.
"""

from decimal import Decimal
import json
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.academics.models import Batch
from apps.attendance.models import AcademicSession
from apps.core.models import AdmissionInquiry, Course, Facility
from apps.institutions.models import Institution, InstitutionMembership


@override_settings(ALLOWED_HOSTS=["*"])
class MultiInstituteWebsiteAndPWATests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client()

        # 1. Seed two distinct institutions with contrasting brand themes
        self.inst_apex = Institution.objects.create(
            name="Apex Horizon Academy",
            code="APEX",
            slug="apex-horizon",
            subdomain="apex",
            custom_domain="apexacademy.com",
            tagline="Premier STEM & Competitive Entrance Coaching",
            description="Empowering future engineers and doctors through rigorous pedagogy.",
            primary_color="#e11d48",  # Rose Red
            accent_color="#f59e0b",   # Amber
            contact_email="admissions@apexacademy.com",
            contact_phone="+1 (800) 555-APEX",
            address="100 Innovation Boulevard, Cyber City",
            public_notice="APEX Admissions Open: Early Bird 20% Scholarship for JEE / NEET Batches!",
            is_active=True,
        )

        self.inst_beacon = Institution.objects.create(
            name="Beacon International College",
            code="BEACON",
            slug="beacon-intl",
            subdomain="beacon",
            custom_domain="beaconcollege.edu",
            tagline="Liberal Arts, Commerce & Global Leadership",
            description="Fostering critical thinking, civic responsibility, and international commerce.",
            primary_color="#059669",  # Emerald Green
            accent_color="#06b6d4",   # Cyan
            contact_email="info@beaconcollege.edu",
            contact_phone="+1 (800) 555-BEAC",
            address="450 Heritage Avenue, Academic Enclave",
            public_notice="Beacon Admissions: Merit fellowship applications close on Nov 30.",
            is_active=True,
        )

        # 2. Seed faculty for Apex and Beacon
        self.teacher_apex = User.objects.create_user(
            username="teacher_apex",
            email="dr.sharma@apexacademy.com",
            first_name="Rajesh",
            last_name="Sharma",
            role=Role.TEACHER,
            subject_specialization="Advanced Physics & Quantum Mechanics",
            bio="IIT alumnus with 15+ years of JEE coaching mentorship.",
            institution=self.inst_apex,
        )

        self.teacher_beacon = User.objects.create_user(
            username="teacher_beacon",
            email="prof.clara@beaconcollege.edu",
            first_name="Clara",
            last_name="Oswald",
            role=Role.TEACHER,
            subject_specialization="Macroeconomics & World Trade",
            bio="Senior Fellow in International Trade and Monetary Policy.",
            institution=self.inst_beacon,
        )

        # 3. Seed courses scoped to institutions
        self.course_apex = Course.objects.create(
            institution=self.inst_apex,
            title="JEE Advanced Physics Mastery",
            code="APEX-PHY-301",
            slug="apex-jee-physics-mastery",
            department="Department of Physical Sciences",
            level=Course.Level.SECONDARY,
            duration="1 Year",
            description="Deep problem-solving covering rotational dynamics and electrodynamics.",
            fee_per_term=Decimal("3500.00"),
            is_active=True,
            is_featured=True,
        )

        self.course_beacon = Course.objects.create(
            institution=self.inst_beacon,
            title="Global Macroeconomic Policy",
            code="BEAC-ECO-101",
            slug="beacon-global-macroeconomics",
            department="School of Commerce & Economics",
            level=Course.Level.UNDERGRADUATE,
            duration="3 Years",
            description="Comprehensive grounding in monetary economics and fiscal policy.",
            fee_per_term=Decimal("4200.00"),
            is_active=True,
            is_featured=True,
        )

        # 4. Seed academic session and coaching batches
        self.session = AcademicSession.objects.create(
            name="Academic Year 2026-27",
            start_date="2026-04-01",
            end_date="2027-03-31",
            is_current=True,
        )

        self.batch_apex = Batch.objects.create(
            institution=self.inst_apex,
            course=self.course_apex,
            academic_session=self.session,
            name="JEE 2027 Morning Super-30 Batch",
            code="APEX-BAT-M01",
            target_class="Class 11",
            stream="Science (PCM)",
            board="CBSE",
            start_date="2026-06-01",
            end_date="2027-03-31",
            capacity=30,
            status=Batch.Status.ONGOING,
        )

        self.batch_beacon = Batch.objects.create(
            institution=self.inst_beacon,
            course=self.course_beacon,
            academic_session=self.session,
            name="Economics Honours 2026 Cohort A",
            code="BEAC-BAT-ECO",
            target_class="Undergraduate Year 1",
            stream="Commerce & Economics",
            board="University Affiliated",
            start_date="2026-07-15",
            end_date="2027-05-30",
            capacity=45,
            status=Batch.Status.UPCOMING,
        )

    # ==========================================================================
    # 1. Acceptance Test: Each institute's public site shows its own branding
    # ==========================================================================

    def test_acceptance_each_institute_public_site_shows_its_own_branding(self):
        """
        Verify that each institute's public site renders its custom branding,
        colors, notices, courses, faculty, and batches without cross-contamination.
        Tested via slug routing, custom domain mapping, and subdomain mapping.
        """
        # A) Via Slug Routing: /institute/apex-horizon/
        resp_apex = self.client.get(reverse("core:institute_home", kwargs={"slug": self.inst_apex.slug}))
        self.assertEqual(resp_apex.status_code, 200)
        self.assertContains(resp_apex, "Apex Horizon Academy")
        self.assertContains(resp_apex, "#e11d48")  # Apex primary rose color
        self.assertContains(resp_apex, "APEX Admissions Open: Early Bird 20% Scholarship")
        self.assertContains(resp_apex, "JEE Advanced Physics Mastery")
        self.assertNotContains(resp_apex, "Beacon International College")
        self.assertNotContains(resp_apex, "Global Macroeconomic Policy")

        # B) Via Slug Routing: /institute/beacon-intl/
        resp_beacon = self.client.get(reverse("core:institute_home", kwargs={"slug": self.inst_beacon.slug}))
        self.assertEqual(resp_beacon.status_code, 200)
        self.assertContains(resp_beacon, "Beacon International College")
        self.assertContains(resp_beacon, "#059669")  # Beacon primary emerald color
        self.assertContains(resp_beacon, "Beacon Admissions: Merit fellowship applications close")
        self.assertContains(resp_beacon, "Global Macroeconomic Policy")
        self.assertNotContains(resp_beacon, "Apex Horizon Academy")
        self.assertNotContains(resp_beacon, "JEE Advanced Physics Mastery")

        # C) Custom Domain Mapping: Host = apexacademy.com
        resp_domain = self.client.get("/", HTTP_HOST="apexacademy.com")
        self.assertEqual(resp_domain.status_code, 200)
        self.assertContains(resp_domain, "Apex Horizon Academy")
        self.assertContains(resp_domain, "#e11d48")

        # D) Subdomain Mapping: Host = beacon.educonnect.local
        resp_sub = self.client.get("/", HTTP_HOST="beacon.educonnect.local")
        self.assertEqual(resp_sub.status_code, 200)
        self.assertContains(resp_sub, "Beacon International College")
        self.assertContains(resp_sub, "#059669")

        # E) Invalid slug raises 404 (validated institute slug requirement)
        resp_invalid = self.client.get("/institute/non-existent-institute-slug/")
        self.assertEqual(resp_invalid.status_code, 404)

        # F) Faculty & Batches public isolation
        resp_fac_apex = self.client.get(reverse("core:institute_faculty", kwargs={"slug": self.inst_apex.slug}))
        self.assertContains(resp_fac_apex, "Rajesh Sharma")
        self.assertContains(resp_fac_apex, "Advanced Physics & Quantum Mechanics")
        self.assertNotContains(resp_fac_apex, "Clara Oswald")

        resp_bat_apex = self.client.get(reverse("core:institute_batches", kwargs={"slug": self.inst_apex.slug}))
        self.assertContains(resp_bat_apex, "JEE 2027 Morning Super-30 Batch")
        self.assertNotContains(resp_bat_apex, "Economics Honours 2026 Cohort A")

    # ==========================================================================
    # 2. Acceptance Test: Admission forms save records to the correct institute
    # ==========================================================================

    def test_acceptance_admission_forms_save_records_to_the_correct_institute(self):
        """
        Verify that prospective applicants submitting admissions enquiries on an
        institute's public portal have their records strictly bound to that tenant.
        """
        # Submit enquiry on Apex Horizon Academy portal
        apex_enquiry_data = {
            "applicant_name": "Aarav Patel",
            "email": "aarav.patel@example.com",
            "phone": "+1 (555) 777-8899",
            "target_program": "JEE Advanced Physics Mastery",
            "prior_school": "Modern Science High School",
            "comments": "Interested in morning coaching cohort.",
        }
        post_resp_apex = self.client.post(
            reverse("core:institute_admissions", kwargs={"slug": self.inst_apex.slug}),
            data=apex_enquiry_data,
            follow=True,
        )
        self.assertEqual(post_resp_apex.status_code, 200)

        # Verify record in AdmissionInquiry
        inquiry_apex = AdmissionInquiry.objects.filter(email="aarav.patel@example.com").first()
        self.assertIsNotNone(inquiry_apex)
        self.assertEqual(inquiry_apex.institution, self.inst_apex)
        self.assertNotEqual(inquiry_apex.institution, self.inst_beacon)

        # Submit enquiry on Beacon International College portal
        beacon_enquiry_data = {
            "applicant_name": "Sophie Dubois",
            "email": "sophie.dubois@example.com",
            "phone": "+1 (555) 333-4455",
            "target_program": "Global Macroeconomic Policy",
            "prior_school": "International Academy of Geneva",
            "comments": "Applying for foreign exchange consideration.",
        }
        post_resp_beacon = self.client.post(
            reverse("core:institute_admissions", kwargs={"slug": self.inst_beacon.slug}),
            data=beacon_enquiry_data,
            follow=True,
        )
        self.assertEqual(post_resp_beacon.status_code, 200)

        inquiry_beacon = AdmissionInquiry.objects.filter(email="sophie.dubois@example.com").first()
        self.assertIsNotNone(inquiry_beacon)
        self.assertEqual(inquiry_beacon.institution, self.inst_beacon)
        self.assertNotEqual(inquiry_beacon.institution, self.inst_apex)

    # ==========================================================================
    # 3. Acceptance Test: Login works from mobile and desktop
    # ==========================================================================

    def test_acceptance_login_works_from_mobile_and_desktop(self):
        """
        Verify that login endpoints render properly, pre-bind institute context,
        and authenticate users from both desktop and mobile user agents.
        """
        # User credentials
        test_student = User.objects.create_user(
            username="student_mobile",
            email="mobile.student@example.com",
            password="SecurePass2026!",
            role=Role.STUDENT,
            institution=self.inst_apex,
        )
        InstitutionMembership.objects.get_or_create(
            user=test_student,
            institution=self.inst_apex,
            defaults={"role": Role.STUDENT, "is_active": True},
        )

        # Desktop User-Agent
        desktop_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        resp_desktop = self.client.get(
            reverse("core:institute_login", kwargs={"slug": self.inst_apex.slug}),
            HTTP_USER_AGENT=desktop_ua,
            follow=True,
        )
        self.assertEqual(resp_desktop.status_code, 200)
        self.assertEqual(self.client.session.get("active_institution_id"), str(self.inst_apex.id))

        # Perform login from desktop
        login_success_desktop = self.client.login(username="student_mobile", password="SecurePass2026!")
        self.assertTrue(login_success_desktop)
        self.client.logout()

        # Mobile User-Agent (iPhone / Android)
        mobile_ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
        resp_mobile = self.client.get(
            reverse("core:institute_login", kwargs={"slug": self.inst_apex.slug}),
            HTTP_USER_AGENT=mobile_ua,
            follow=True,
        )
        self.assertEqual(resp_mobile.status_code, 200)

        # Perform login from mobile
        login_success_mobile = self.client.login(username="student_mobile", password="SecurePass2026!")
        self.assertTrue(login_success_mobile)

    # ==========================================================================
    # 4. Acceptance Test: Manifest and service worker load correctly
    # ==========================================================================

    def test_acceptance_manifest_and_service_worker_load_correctly(self):
        """
        Verify:
        - /manifest.json returns valid JSON with correct icons, theme colors, and display mode.
        - /sw.js returns HTTP 200 with application/javascript and Service-Worker-Allowed header.
        """
        # A) Manifest check
        manifest_resp = self.client.get(reverse("core:pwa_manifest"))
        self.assertEqual(manifest_resp.status_code, 200)
        self.assertTrue("application/manifest+json" in manifest_resp["Content-Type"])

        manifest_data = json.loads(manifest_resp.content.decode("utf-8"))
        self.assertEqual(manifest_data["display"], "standalone")
        self.assertEqual(manifest_data["scope"], "/")
        self.assertIn("icons", manifest_data)
        self.assertTrue(len(manifest_data["icons"]) >= 6)

        # Check required icon dimensions (192x192 and 512x512)
        icon_sizes = [icon["sizes"] for icon in manifest_data["icons"]]
        self.assertIn("192x192", icon_sizes)
        self.assertIn("512x512", icon_sizes)

        # Dynamic tenant branding in manifest
        manifest_apex = self.client.get("/manifest.json", HTTP_HOST="apexacademy.com")
        apex_data = json.loads(manifest_apex.content.decode("utf-8"))
        self.assertEqual(apex_data["name"], "Apex Horizon Academy")
        self.assertEqual(apex_data["theme_color"], "#e11d48")

        # B) Service worker check
        sw_resp = self.client.get(reverse("core:service_worker"))
        self.assertEqual(sw_resp.status_code, 200)
        self.assertTrue("application/javascript" in sw_resp["Content-Type"])
        self.assertEqual(sw_resp["Service-Worker-Allowed"], "/")
        self.assertEqual(sw_resp["Cache-Control"], "no-cache, no-store, must-revalidate")

        # Verify service worker content contains precache and security controls
        sw_body = sw_resp.content.decode("utf-8")
        self.assertIn("CACHE_VERSION", sw_body)
        self.assertIn("/offline/", sw_body)
        self.assertIn("SENSITIVE_URL_PATTERNS", sw_body)
        self.assertIn("/fees/", sw_body)
        self.assertIn("/attendance/", sw_body)

    # ==========================================================================
    # 5. Acceptance Test: PWA can be installed in a supported browser
    # ==========================================================================

    def test_acceptance_pwa_can_be_installed_in_supported_browser(self):
        """
        Verify all browser installation prerequisites:
        1. Manifest linked in HTML base template.
        2. Viewport meta tag configured.
        3. Apple mobile web app capable tag.
        4. Service worker registration script present in client assets.
        5. Theme color and touch icons defined.
        """
        resp = self.client.get(reverse("core:index"))
        self.assertEqual(resp.status_code, 200)

        # Check manifest linkage in DOM
        self.assertContains(resp, 'rel="manifest"')
        self.assertContains(resp, 'href="/manifest.json"')

        # Check mobile viewport and meta tags
        self.assertContains(resp, 'name="viewport"')
        self.assertContains(resp, 'name="theme-color"')
        self.assertContains(resp, 'name="apple-mobile-web-app-capable"')
        self.assertContains(resp, 'rel="apple-touch-icon"')

        # Check PWA install trigger button present in DOM
        self.assertContains(resp, "pwa-install-trigger")

        # Check service worker registration in static/js/main.js
        with open("static/js/main.js", "r", encoding="utf-8") as f:
            main_js_content = f.read()
        self.assertIn("navigator.serviceWorker.register('/sw.js'", main_js_content)
        self.assertIn("beforeinstallprompt", main_js_content)

    # ==========================================================================
    # 6. Acceptance Test: Offline navigation shows the offline fallback
    # ==========================================================================

    def test_acceptance_offline_navigation_shows_the_offline_fallback(self):
        """
        Verify that /offline/ renders a user-friendly fallback explaining
        which operations require an active internet connection.
        """
        resp = self.client.get(reverse("core:offline"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "You Are Currently Offline")
        self.assertContains(resp, "Features Requiring Live Server Connection")
        self.assertContains(resp, "Fee Payments & Invoices")
        self.assertContains(resp, "Admission Applications")
        self.assertContains(resp, "Attendance & Alerts")
        self.assertContains(resp, "Complaints & Support Tickets")
        self.assertContains(resp, "Check Connection & Retry")

    # ==========================================================================
    # 7. Acceptance Test: Private student and payment data are not cached/exposed
    # ==========================================================================

    def test_acceptance_private_student_and_payment_data_not_cached_or_exposed(self):
        """
        Verify that:
        1. Service worker strictly classifies private paths (/fees/, /attendance/, etc.) as sensitive.
        2. Authenticated HTTP responses automatically include strict no-cache headers:
           Cache-Control: no-cache, no-store, must-revalidate, private
        """
        # Inspect service worker script sensitive paths
        sw_resp = self.client.get(reverse("core:service_worker"))
        sw_code = sw_resp.content.decode("utf-8")

        sensitive_endpoints = ["/accounts/", "/fees/", "/attendance/", "/academics/", "/complaints/"]
        for endpoint in sensitive_endpoints:
            self.assertIn(endpoint, sw_code)

        # Login as student and inspect authenticated response headers
        user = User.objects.create_user(
            username="cache_test_user",
            password="SecurePass2026!",
            role=Role.STUDENT,
            institution=self.inst_apex,
        )
        InstitutionMembership.objects.get_or_create(
            user=user,
            institution=self.inst_apex,
            defaults={"role": Role.STUDENT, "is_active": True},
        )
        self.client.login(username="cache_test_user", password="SecurePass2026!")

        auth_resp = self.client.get(reverse("fees:student_overview"))
        self.assertEqual(auth_resp.status_code, 200)

        # Confirm strict anti-caching headers for private student & payment pages
        cache_header = auth_resp.headers.get("Cache-Control", "")
        self.assertIn("no-store", cache_header)
        self.assertIn("private", cache_header)

    # ==========================================================================
    # 8. Acceptance Test: Updating the app does not leave stale or broken assets
    # ==========================================================================

    def test_acceptance_updating_app_does_not_leave_stale_or_broken_assets(self):
        """
        Verify that:
        1. Service worker implements an activate purge handler deleting outdated caches.
        2. main.js monitors controllerchange for clean atomic updates.
        3. Static cache keys are versioned.
        """
        sw_resp = self.client.get(reverse("core:service_worker"))
        sw_code = sw_resp.content.decode("utf-8")

        self.assertIn("self.addEventListener('activate'", sw_code)
        self.assertIn("caches.delete(cacheName)", sw_code)
        self.assertIn("self.clients.claim()", sw_code)
        self.assertIn("self.skipWaiting()", sw_code)

        with open("static/js/main.js", "r", encoding="utf-8") as f:
            main_js = f.read()
        self.assertIn("controllerchange", main_js)

"""
Comprehensive Test Suite for EduConnect Authentication & Role-Based Access Control.
Tests login, invalid credentials, public registration role restriction,
role-specific redirects, server-side permission checks, and parent-child authorization.
"""

from io import StringIO
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from apps.accounts.models import Role, User, ParentStudentLink


class AuthenticationAndRoleTestCase(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client()

        # Provision one user for each of the six primary roles
        self.password = "StrongPass2026!#"

        self.admin_user = User.objects.create_user(
            username="admin_user",
            email="admin@educonnect.test",
            password=self.password,
            role=Role.ADMIN,
            is_staff=True,
            is_superuser=True,
        )

        self.teacher_user = User.objects.create_user(
            username="teacher_user",
            email="teacher@educonnect.test",
            password=self.password,
            role=Role.TEACHER,
            subject_specialization="Mathematics & Physics",
            employee_id="EMP-T-001",
        )

        self.student_1 = User.objects.create_user(
            username="student_alice",
            email="alice@educonnect.test",
            password=self.password,
            role=Role.STUDENT,
            student_id="STU-2026-001",
            grade_level="Grade 10",
        )

        self.student_2 = User.objects.create_user(
            username="student_bob",
            email="bob@educonnect.test",
            password=self.password,
            role=Role.STUDENT,
            student_id="STU-2026-002",
            grade_level="Grade 11",
        )

        self.parent_user = User.objects.create_user(
            username="parent_carol",
            email="carol@educonnect.test",
            password=self.password,
            role=Role.PARENT,
            phone_number="+1-555-123-4567",
        )

        self.accounts_user = User.objects.create_user(
            username="accounts_dave",
            email="dave@educonnect.test",
            password=self.password,
            role=Role.ACCOUNTS,
            employee_id="EMP-A-001",
        )

        self.applicant_user = User.objects.create_user(
            username="applicant_eve",
            email="eve@educonnect.test",
            password=self.password,
            role=Role.APPLICANT,
        )

        # Authorize parent_carol as guardian for student_1 (Alice) ONLY
        self.link = ParentStudentLink.objects.create(
            parent=self.parent_user,
            student=self.student_1,
            relationship_type="mother",
            is_authorized=True,
        )

    # --------------------------------------------------------------------------
    # 1. Login & Credentials Tests
    # --------------------------------------------------------------------------

    def test_successful_login_and_redirect(self):
        """
        Verify valid credentials log the user in and redirect to dashboard.
        """
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "student_alice", "password": self.password},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["user"].is_authenticated)
        self.assertEqual(response.context["user"].username, "student_alice")
        # Followed redirect to student dashboard
        self.assertContains(response, "Student Academic Workspace")

    def test_invalid_password_rejected(self):
        """
        Verify invalid password fails with error message and does not authenticate.
        """
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "student_alice", "password": "WrongPassword123!"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["user"].is_authenticated)
        self.assertContains(response, "Invalid username or password")

    def test_nonexistent_user_rejected(self):
        """
        Verify non-existent username fails with clear error.
        """
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "ghost_user", "password": self.password},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["user"].is_authenticated)
        self.assertContains(response, "Invalid username or password")

    # --------------------------------------------------------------------------
    # 2. Public Registration Security & Role Restriction
    # --------------------------------------------------------------------------

    def test_public_registration_blocks_admin_role(self):
        """
        CRITICAL SECURITY REQUIREMENT:
        Public registration must NEVER allow creating Admin or Accounts Staff roles.
        """
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "malicious_admin",
                "email": "hacker@test.local",
                "first_name": "Bad",
                "last_name": "Actor",
                "role": "admin",  # Tampered role injection attempt
                "password1": "SecurePass2026!#",
                "password2": "SecurePass2026!#",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="malicious_admin").exists())
        self.assertContains(response, "Select a valid choice")

    def test_public_registration_blocks_accounts_role(self):
        """
        CRITICAL SECURITY REQUIREMENT:
        Public registration must NEVER allow creating Accounts Staff roles.
        """
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "fake_accountant",
                "email": "fake@test.local",
                "first_name": "Fake",
                "last_name": "Accountant",
                "role": "accounts",  # Tampered role injection attempt
                "password1": "SecurePass2026!#",
                "password2": "SecurePass2026!#",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="fake_accountant").exists())
        self.assertContains(response, "Select a valid choice")

    def test_public_registration_succeeds_for_permitted_roles(self):
        """
        Public registration succeeds for legitimate applicant or parent roles.
        """
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "new_applicant",
                "email": "applicant.new@test.local",
                "first_name": "New",
                "last_name": "Applicant",
                "role": Role.APPLICANT,
                "password1": "ValidPass2026!#",
                "password2": "ValidPass2026!#",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        created_user = User.objects.filter(username="new_applicant").first()
        self.assertIsNotNone(created_user)
        self.assertEqual(created_user.role, Role.APPLICANT)
        self.assertFalse(created_user.is_staff)
        self.assertFalse(created_user.is_superuser)

    # --------------------------------------------------------------------------
    # 3. Role-Based Dashboards & Server-Side Permission Checks
    # --------------------------------------------------------------------------

    def test_unauthenticated_user_redirected_to_login(self):
        """
        Unauthenticated requests to any dashboard must redirect to login with ?next=.
        """
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/?next=", response.url)

    def test_student_forbidden_from_admin_dashboard(self):
        """
        A student attempting to access admin dashboard receives HTTP 403 Forbidden.
        """
        self.client.login(username="student_alice", password=self.password)
        response = self.client.get(reverse("accounts:admin_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_student_forbidden_from_accounts_dashboard(self):
        """
        A student attempting to access accounts dashboard receives HTTP 403 Forbidden.
        """
        self.client.login(username="student_alice", password=self.password)
        response = self.client.get(reverse("accounts:accounts_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_teacher_forbidden_from_accounts_dashboard(self):
        """
        A teacher attempting to access accounts dashboard receives HTTP 403 Forbidden.
        """
        self.client.login(username="teacher_user", password=self.password)
        response = self.client.get(reverse("accounts:accounts_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_applicant_forbidden_from_student_dashboard(self):
        """
        An applicant attempting to access enrolled student dashboard receives HTTP 403 Forbidden.
        """
        self.client.login(username="applicant_eve", password=self.password)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_role_dispatchers_route_correctly(self):
        """
        Verify each role routes to its designated dashboard via dashboard_redirect.
        """
        roles_to_expected_substrings = [
            ("admin_user", "Administrative Control Center"),
            ("teacher_user", "Teacher Academic Portal"),
            ("student_alice", "Student Academic Workspace"),
            ("parent_carol", "Parent &amp; Guardian Portal"),
            ("accounts_dave", "Financial &amp; Accounts Management"),
            ("applicant_eve", "Admissions &amp; Application Status"),
        ]

        for username, expected_heading in roles_to_expected_substrings:
            self.client.login(username=username, password=self.password)
            response = self.client.get(reverse("accounts:dashboard_redirect"), follow=True)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, expected_heading)
            self.client.logout()

    # --------------------------------------------------------------------------
    # 4. Parent-Child Linking & Authorization Isolation
    # --------------------------------------------------------------------------

    def test_parent_can_access_authorized_child(self):
        """
        Parent Carol is authorized for Alice and can view Alice's details.
        """
        self.client.login(username="parent_carol", password=self.password)
        response = self.client.get(
            reverse("accounts:parent_child_detail", kwargs={"student_id": str(self.student_1.id)})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "student_alice")
        self.assertContains(response, "Authorized Guardian File")

    def test_parent_forbidden_from_unauthorized_child(self):
        """
        CRITICAL DATA ISOLATION TEST:
        Parent Carol is NOT authorized for Bob (student_2).
        Attempting to access Bob's details MUST yield HTTP 403 Forbidden.
        """
        self.client.login(username="parent_carol", password=self.password)
        response = self.client.get(
            reverse("accounts:parent_child_detail", kwargs={"student_id": str(self.student_2.id)})
        )
        self.assertEqual(response.status_code, 403)

    # --------------------------------------------------------------------------
    # 5. Logout & Session Termination
    # --------------------------------------------------------------------------

    def test_logout_terminates_session(self):
        """
        Verify logging out clears session and redirects to login page.
        """
        self.client.login(username="student_alice", password=self.password)
        response = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(response.status_code, 200)

        # Logout
        logout_resp = self.client.post(reverse("accounts:logout"), follow=True)
        self.assertEqual(logout_resp.status_code, 200)
        self.assertFalse(logout_resp.context["user"].is_authenticated)

        # Subsequent protected dashboard request redirects to login
        protected_resp = self.client.get(reverse("accounts:student_dashboard"))
        self.assertEqual(protected_resp.status_code, 302)

    # --------------------------------------------------------------------------
    # 6. Admin Management Command
    # --------------------------------------------------------------------------

    def test_create_educonnect_admin_command(self):
        """
        Verify management command successfully creates an administrator.
        """
        out = StringIO()
        call_command(
            "create_educonnect_admin",
            username="cli_admin",
            email="cli_admin@educonnect.test",
            password="CmdAdminPass2026!#",
            noinput=True,
            stdout=out,
        )
        self.assertIn("Successfully Created Administrator 'cli_admin'", out.getvalue())

        user = User.objects.get(username="cli_admin")
        self.assertEqual(user.role, Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("CmdAdminPass2026!#"))

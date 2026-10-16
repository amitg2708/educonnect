"""
Test suite validating health check endpoints and credential security.
"""

import json
from django.test import TestCase, Client
from django.urls import reverse


class HealthCheckTestCase(TestCase):
    databases = {"default"}

    def setUp(self):
        self.client = Client()

    def test_health_api_endpoint(self):
        """
        Verify /api/health/ returns 200, status healthy, and includes database stats.
        """
        response = self.client.get(reverse("core:api_health"))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data.get("status"), "healthy")
        self.assertIn("database", data)
        self.assertEqual(data["database"].get("status"), "connected")
        self.assertEqual(data["database"].get("engine"), "django_mongodb_backend")
        self.assertTrue(data["database"].get("ok"))

    def test_health_api_does_not_expose_credentials(self):
        """
        Ensure no passwords, secrets, or full connection strings are in the response.
        """
        response = self.client.get(reverse("core:api_health"))
        content_str = response.content.decode("utf-8")

        forbidden_keys = ["password", "secret", "user:", "mongodb+srv://", "mongodb://"]
        for key in forbidden_keys:
            self.assertNotIn(
                key.lower(),
                content_str.lower(),
                f"Health check response leaked sensitive string or credential token '{key}'!",
            )

    def test_health_html_page(self):
        """
        Verify /health/ renders successfully.
        """
        response = self.client.get(reverse("core:health"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System Health & Diagnostics")
        self.assertContains(response, "django_mongodb_backend")

    def test_index_dashboard_page(self):
        """
        Verify / renders successfully with EduConnect public home branding.
        """
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "EduConnect")
        self.assertContains(response, "Empowering Minds")

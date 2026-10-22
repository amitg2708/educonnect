"""
EduConnect Institutions Application Configuration.
Multi-tenant coaching platform core module.
"""

from django.apps import AppConfig


class InstitutionsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.institutions"
    verbose_name = "Institutions & Multi-Tenancy"

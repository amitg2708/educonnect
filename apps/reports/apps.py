from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.reports"
    verbose_name = "Administration & Reports"

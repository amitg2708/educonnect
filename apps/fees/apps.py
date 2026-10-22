from django.apps import AppConfig


class FeesConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.fees"
    verbose_name = "Fees Management"

from django.apps import AppConfig


class AcademicsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.academics"
    verbose_name = "Academics & Subject Management"

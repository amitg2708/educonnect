from django.apps import AppConfig


class AdmissionsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.admissions"
    verbose_name = "Admissions Management"

from django.apps import AppConfig


class ComplaintsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.complaints"
    verbose_name = "Complaints & Request Management"

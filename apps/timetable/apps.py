from django.apps import AppConfig


class TimetableConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.timetable"
    verbose_name = "Timetable Management"

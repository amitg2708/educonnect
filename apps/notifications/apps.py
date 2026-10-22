from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django_mongodb_backend.fields.ObjectIdAutoField"
    name = "apps.notifications"
    verbose_name = "Notifications & Parent Portal"

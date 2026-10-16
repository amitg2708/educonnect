import os
from django.conf import settings


def app_context(request):
    """
    Context processor providing global variables to templates.
    """
    return {
        "APP_NAME": "EduConnect",
        "APP_VERSION": "1.0.0-dev",
        "ENVIRONMENT": os.getenv("DJANGO_ENV", "development"),
        "DEBUG_MODE": settings.DEBUG,
    }

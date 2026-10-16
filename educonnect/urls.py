"""
Main URL Configuration for EduConnect project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Django Admin site
    path("admin/", admin.site.urls),
    # Accounts & Authentication
    path("accounts/", include("apps.accounts.urls")),
    # Core app (Home, Health Check, API)
    path("", include("apps.core.urls")),
]

# Serve media files in development environment
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

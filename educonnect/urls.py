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
    # Multi-tenant Institutions & Branches
    path("institutions/", include("apps.institutions.urls")),
    # Admissions Management
    path("admissions/", include("apps.admissions.urls")),
    # Fees Management
    path("fees/", include("apps.fees.urls")),
    # Attendance Management
    path("attendance/", include("apps.attendance.urls")),
    # Timetable Management
    path("timetable/", include("apps.timetable.urls")),
    # Academics & Subject Teacher Management
    path("academics/", include("apps.academics.urls")),
    # Complaints & Request Management
    path("complaints/", include("apps.complaints.urls")),
    # Notifications & Parent Portal Hub
    path("notifications/", include("apps.notifications.urls")),
    # Administration & Reports Hub
    path("administration/", include("apps.reports.urls")),
    # Core app (Home, Health Check, API)
    path("", include("apps.core.urls")),
]

# Serve media files in development environment
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

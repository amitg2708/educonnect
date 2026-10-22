"""
URL configurations for EduConnect Administration & Reporting module.
"""

from django.urls import path
from apps.reports import views

app_name = "reports"

urlpatterns = [
    # Main Administrative Hub
    path("dashboard/", views.admin_dashboard_view, name="admin_dashboard"),

    # Filtered Reports & CSV Exports
    path("reports/admissions/", views.admissions_report, name="admissions_report"),
    path("reports/fees/", views.fees_report, name="fees_report"),
    path("reports/attendance/", views.attendance_report, name="attendance_report"),
    path("reports/academics/", views.academics_report, name="academics_report"),
    path("reports/complaints/", views.complaints_report, name="complaints_report"),

    # Institutional Configuration & Operational Desks
    path("settings/", views.institution_settings_view, name="institution_settings"),
    path("audit-logs/", views.admin_audit_logs_view, name="admin_audit_logs"),
    path("manage/classes/", views.manage_classes_view, name="manage_classes"),
    path("manage/enrollments/", views.manage_enrollments_view, name="manage_enrollments"),
    path("manage/teacher-assignments/", views.manage_assignments_view, name="manage_assignments"),
]

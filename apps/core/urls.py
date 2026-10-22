"""
URL patterns for EduConnect Public Portal, Multi-Tenant Routing, and PWA Services.
"""

from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    # --------------------------------------------------------------------------
    # Root Public Website Routes (Default or Host-Resolved Tenant)
    # --------------------------------------------------------------------------
    path("", views.home_view, name="index"),
    path("about/", views.about_view, name="about"),
    path("courses/", views.courses_list_view, name="courses"),
    path("courses/<slug:slug>/", views.course_detail_view, name="course_detail"),
    path("faculty/", views.faculty_view, name="faculty"),
    path("batches/", views.batches_view, name="batches"),
    path("achievements/", views.achievements_view, name="achievements"),
    path("gallery/", views.gallery_view, name="gallery"),
    path("admissions/", views.admissions_view, name="admissions"),
    path("enquiry/", views.admissions_view, name="enquiry"),
    path("contact/", views.contact_view, name="contact"),
    path("login/", views.institute_login_view, name="login"),

    # --------------------------------------------------------------------------
    # Institute-Scoped Public Routes (/institute/<slug>/...)
    # --------------------------------------------------------------------------
    path("institute/<slug:slug>/", views.home_view, name="institute_home"),
    path("institute/<slug:slug>/about/", views.about_view, name="institute_about"),
    path("institute/<slug:slug>/courses/", views.courses_list_view, name="institute_courses"),
    path("institute/<slug:slug>/courses/<slug:course_slug>/", views.course_detail_view, name="institute_course_detail"),
    path("institute/<slug:slug>/faculty/", views.faculty_view, name="institute_faculty"),
    path("institute/<slug:slug>/batches/", views.batches_view, name="institute_batches"),
    path("institute/<slug:slug>/achievements/", views.achievements_view, name="institute_achievements"),
    path("institute/<slug:slug>/gallery/", views.gallery_view, name="institute_gallery"),
    path("institute/<slug:slug>/admissions/", views.admissions_view, name="institute_admissions"),
    path("institute/<slug:slug>/enquiry/", views.admissions_view, name="institute_enquiry"),
    path("institute/<slug:slug>/contact/", views.contact_view, name="institute_contact"),
    path("institute/<slug:slug>/login/", views.institute_login_view, name="institute_login"),

    # --------------------------------------------------------------------------
    # Progressive Web App (PWA) & Offline Services
    # --------------------------------------------------------------------------
    path("manifest.json", views.pwa_manifest, name="pwa_manifest"),
    path("manifest.webmanifest", views.pwa_manifest, name="pwa_webmanifest"),
    path("sw.js", views.service_worker_view, name="service_worker"),
    path("offline/", views.offline_view, name="offline"),

    # --------------------------------------------------------------------------
    # Diagnostics & Probes
    # --------------------------------------------------------------------------
    path("health/", views.health_check_view, name="health"),
    path("api/health/", views.health_check_api, name="api_health"),
]

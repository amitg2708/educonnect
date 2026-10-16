"""
URL patterns for EduConnect Public Portal and System Health.
"""

from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    # Public Website Routes
    path("", views.home_view, name="index"),
    path("about/", views.about_view, name="about"),
    path("courses/", views.courses_list_view, name="courses"),
    path("courses/<slug:slug>/", views.course_detail_view, name="course_detail"),
    path("achievements/", views.achievements_view, name="achievements"),
    path("gallery/", views.gallery_view, name="gallery"),
    path("admissions/", views.admissions_view, name="admissions"),
    path("contact/", views.contact_view, name="contact"),
    # Diagnostics & Probes
    path("health/", views.health_check_view, name="health"),
    path("api/health/", views.health_check_api, name="api_health"),
]

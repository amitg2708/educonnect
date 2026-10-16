"""
Public Website Views for EduConnect.
Provides database-backed pages for Home, About, Courses, Achievements,
Gallery, Admissions, Contact, and System Diagnostics.
"""

from datetime import datetime, timezone
import logging
import time
from django.conf import settings
from django.contrib import messages
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import AdmissionInquiryForm, ContactForm
from .models import (
    Achievement,
    AdmissionInquiry,
    Announcement,
    ContactInquiry,
    Course,
    Facility,
    GalleryItem,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# Health Check Helpers
# ==============================================================================

def check_mongo_health():
    """
    Check MongoDB connectivity and operational status without leaking credentials.
    """
    start_time = time.perf_counter()
    try:
        connection.ensure_connection()
        mongo_client = connection.connection

        if mongo_client is None:
            raise ConnectionError("MongoDB client is not initialized.")

        ping_response = mongo_client.admin.command("ping")
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        db_name = connection.settings_dict.get("NAME", "unknown")
        engine = connection.settings_dict.get("ENGINE", "unknown")
        collections_count = len(mongo_client[db_name].list_collection_names())

        return {
            "status": "connected",
            "ok": ping_response.get("ok", 0) == 1.0,
            "engine": engine,
            "database_name": db_name,
            "collections_count": collections_count,
            "latency_ms": latency_ms,
        }, True

    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(f"MongoDB health check failed: {exc}", exc_info=True)
        return {
            "status": "disconnected",
            "ok": False,
            "engine": connection.settings_dict.get("ENGINE", "django_mongodb_backend"),
            "database_name": connection.settings_dict.get("NAME", "unknown"),
            "error": "Failed to connect to MongoDB server.",
            "latency_ms": latency_ms,
        }, False


def health_check_api(request):
    """
    JSON Health-check endpoint.
    URL: /api/health/
    """
    db_health, is_healthy = check_mongo_health()
    payload = {
        "status": "healthy" if is_healthy else "degraded",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "EduConnect School & College Management Platform",
        "environment": getattr(settings, "ENVIRONMENT", "development"),
        "database": db_health,
    }
    status_code = 200 if is_healthy else 503
    return JsonResponse(payload, status=status_code)


def health_check_view(request):
    """
    User-facing HTML Health and Diagnostics dashboard.
    URL: /health/
    """
    db_health, is_healthy = check_mongo_health()
    context = {
        "page_title": "System Health & Diagnostics",
        "is_healthy": is_healthy,
        "db_health": db_health,
        "current_time": datetime.now(timezone.utc),
    }
    return render(request, "core/health.html", context)


# ==============================================================================
# Public Website Pages
# ==============================================================================

def home_view(request):
    """
    Public Home Page with hero, announcement banner, featured courses,
    achievements, facilities, and admissions CTA.
    URL: /
    """
    db_health, is_healthy = check_mongo_health()

    featured_courses = Course.objects.filter(is_active=True, is_featured=True)[:3]
    if not featured_courses.exists():
        featured_courses = Course.objects.filter(is_active=True)[:3]

    announcements = Announcement.objects.filter(is_published=True)[:4]
    recent_achievements = Achievement.objects.all()[:3]
    facilities = Facility.objects.all()[:6]

    context = {
        "page_title": "Home - Excellence in Education",
        "is_healthy": is_healthy,
        "db_health": db_health,
        "featured_courses": featured_courses,
        "announcements": announcements,
        "recent_achievements": recent_achievements,
        "facilities": facilities,
    }
    return render(request, "core/home.html", context)


def about_view(request):
    """
    About Us page presenting institutional mission, leadership, and infrastructure.
    URL: /about/
    """
    facilities = Facility.objects.all()
    achievements_count = Achievement.objects.count()
    courses_count = Course.objects.filter(is_active=True).count()

    context = {
        "page_title": "About EduConnect - Vision & Heritage",
        "facilities": facilities,
        "achievements_count": achievements_count,
        "courses_count": courses_count,
    }
    return render(request, "core/about.html", context)


def courses_list_view(request):
    """
    Academic Programs and Courses catalog with level filters and search.
    URL: /courses/
    """
    courses = Course.objects.filter(is_active=True)

    level_filter = request.GET.get("level", "")
    query = request.GET.get("q", "").strip()

    if level_filter and level_filter in [c[0] for c in Course.Level.choices]:
        courses = courses.filter(level=level_filter)

    if query:
        courses = courses.filter(title__icontains=query)

    context = {
        "page_title": "Curriculum & Programs",
        "courses": courses,
        "levels": Course.Level.choices,
        "current_level": level_filter,
        "search_query": query,
    }
    return render(request, "core/courses_list.html", context)


def course_detail_view(request, slug):
    """
    Detailed course syllabus, eligibility, and fee view.
    URL: /courses/<slug>/
    """
    course = get_object_or_404(Course, slug=slug, is_active=True)
    related_courses = Course.objects.filter(is_active=True, department=course.department).exclude(id=course.id)[:3]

    context = {
        "page_title": f"{course.title} ({course.code})",
        "course": course,
        "related_courses": related_courses,
    }
    return render(request, "core/course_detail.html", context)


def achievements_view(request):
    """
    Public Institutional & Student Honors page.
    URL: /achievements/
    """
    achievements = Achievement.objects.all()
    category_filter = request.GET.get("category", "")

    if category_filter and category_filter in [c[0] for c in Achievement.Category.choices]:
        achievements = achievements.filter(category=category_filter)

    context = {
        "page_title": "Achievements & Distinctions",
        "achievements": achievements,
        "categories": Achievement.Category.choices,
        "current_category": category_filter,
    }
    return render(request, "core/achievements.html", context)


def gallery_view(request):
    """
    Campus facilities and event photo gallery.
    URL: /gallery/
    """
    gallery_items = GalleryItem.objects.filter(is_active=True)
    category_filter = request.GET.get("category", "")

    if category_filter and category_filter in [c[0] for c in GalleryItem.Category.choices]:
        gallery_items = gallery_items.filter(category=category_filter)

    context = {
        "page_title": "Campus Life & Gallery",
        "gallery_items": gallery_items,
        "categories": GalleryItem.Category.choices,
        "current_category": category_filter,
    }
    return render(request, "core/gallery.html", context)


def admissions_view(request):
    """
    Admissions guide and online inquiry submission.
    URL: /admissions/
    """
    if request.method == "POST":
        form = AdmissionInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save()
            messages.success(
                request,
                f"Thank you, {inquiry.applicant_name}! Your admissions inquiry for '{inquiry.target_program}' has been received. Our admissions counselor will contact you at {inquiry.email}.",
            )
            return redirect("core:admissions")
        messages.error(request, "Please correct the errors below and resubmit.")
    else:
        # Pre-populate program if selected from course page
        initial_data = {}
        program_pref = request.GET.get("program")
        if program_pref:
            initial_data["target_program"] = program_pref
        form = AdmissionInquiryForm(initial=initial_data)

    courses = Course.objects.filter(is_active=True).order_by("level")

    context = {
        "page_title": "Admissions & Enrollment",
        "form": form,
        "courses": courses,
    }
    return render(request, "core/admissions.html", context)


def contact_view(request):
    """
    Contact Us page with interactive inquiry form.
    URL: /contact/
    """
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Thank you for contacting EduConnect. Your message has been routed to our administrative office and we will respond shortly.",
            )
            return redirect("core:contact")
        messages.error(request, "Please correct the errors in the form before submitting.")
    else:
        form = ContactForm()

    context = {
        "page_title": "Contact Administration & Campus Inquiries",
        "form": form,
    }
    return render(request, "core/contact.html", context)

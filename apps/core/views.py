"""
Public Website Views for EduConnect & Multi-Tenant Progressive Web App (PWA).
Provides database-backed pages for Home, About, Courses, Faculty, Batches,
Achievements, Gallery, Admissions, Contact, Login, PWA Manifest, and Service Worker.
"""

from datetime import datetime, timezone
import json
import logging
import os
import time
from django.conf import settings
from django.contrib import messages
from django.db import connection
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import Role, User
from apps.academics.models import Batch
from apps.admissions.models import Enquiry, EnquirySource
from apps.institutions.models import Institution, InstitutionMembership
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
# Multi-Tenant Resolution Helper
# ==============================================================================

def get_resolved_institution(request, slug=None):
    """
    Resolves the Institution tenant:
    - If URL slug provided, validates and retrieves the active institution (raises 404 if invalid).
    - Otherwise, respects middleware resolution, custom domain, or active default.
    """
    if slug:
        return get_object_or_404(Institution, slug=slug, is_active=True)

    inst = getattr(request, "institution", None)
    if not inst:
        from apps.institutions.middleware import resolve_institution_from_request
        inst = resolve_institution_from_request(request)

    if not inst:
        inst = Institution.objects.filter(is_active=True).first()

    return inst


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
# Public Website Multi-Tenant Pages
# ==============================================================================

def home_view(request, slug=None):
    """
    1. Home Page: Configurable hero, brand identity, notices, featured courses,
       achievements, facilities, batches, and admissions CTA.
    """
    inst = get_resolved_institution(request, slug)
    db_health, is_healthy = check_mongo_health()

    # Scope content to active institution
    if inst:
        featured_courses = Course.objects.filter(institution=inst, is_active=True, is_featured=True)[:3]
        if not featured_courses.exists():
            featured_courses = Course.objects.filter(institution=inst, is_active=True)[:3]
        if not featured_courses.exists():
            featured_courses = Course.objects.filter(is_active=True)[:3]

        announcements = Announcement.objects.filter(Q(institution=inst) | Q(institution__isnull=True), is_published=True)[:4]
        recent_achievements = Achievement.objects.filter(Q(institution=inst) | Q(institution__isnull=True))[:3]
        facilities = Facility.objects.filter(Q(institution=inst) | Q(institution__isnull=True))[:6]
        active_batches = Batch.objects.filter(institution=inst, status__in=[Batch.Status.ONGOING, Batch.Status.UPCOMING]).select_related("course")[:3]
    else:
        featured_courses = Course.objects.filter(is_active=True, is_featured=True)[:3]
        if not featured_courses.exists():
            featured_courses = Course.objects.filter(is_active=True)[:3]
        announcements = Announcement.objects.filter(is_published=True)[:4]
        recent_achievements = Achievement.objects.all()[:3]
        facilities = Facility.objects.all()[:6]
        active_batches = Batch.objects.none()

    page_title = f"{inst.name} - Excellence in Education" if inst else "EduConnect - Excellence in Education"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "is_healthy": is_healthy,
        "db_health": db_health,
        "featured_courses": featured_courses,
        "announcements": announcements,
        "recent_achievements": recent_achievements,
        "facilities": facilities,
        "active_batches": active_batches,
    }
    return render(request, "core/home.html", context)


def about_view(request, slug=None):
    """
    2. About Us: Institutional mission, stats, facilities, and academic infrastructure.
    """
    inst = get_resolved_institution(request, slug)

    if inst:
        facilities = Facility.objects.filter(Q(institution=inst) | Q(institution__isnull=True))
        achievements_count = Achievement.objects.filter(Q(institution=inst) | Q(institution__isnull=True)).count()
        courses_count = Course.objects.filter(Q(institution=inst) | Q(institution__isnull=True), is_active=True).count()
        faculty_count = InstitutionMembership.objects.filter(institution=inst, role=Role.TEACHER, is_active=True).count()
        batches_count = Batch.objects.filter(institution=inst, status__in=[Batch.Status.ONGOING, Batch.Status.UPCOMING]).count()
    else:
        facilities = Facility.objects.all()
        achievements_count = Achievement.objects.count()
        courses_count = Course.objects.filter(is_active=True).count()
        faculty_count = User.objects.filter(role=Role.TEACHER).count()
        batches_count = Batch.objects.count()

    page_title = f"About {inst.name} - Vision & Heritage" if inst else "About EduConnect - Vision & Heritage"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "facilities": facilities,
        "achievements_count": achievements_count,
        "courses_count": courses_count,
        "faculty_count": faculty_count,
        "batches_count": batches_count,
    }
    return render(request, "core/about.html", context)


def courses_list_view(request, slug=None):
    """
    3. Courses: Catalog of academic programs scoped to the active institute.
    """
    inst = get_resolved_institution(request, slug)

    if inst:
        courses = Course.objects.filter(Q(institution=inst) | Q(institution__isnull=True), is_active=True)
    else:
        courses = Course.objects.filter(is_active=True)

    level_filter = request.GET.get("level", "")
    query = request.GET.get("q", "").strip()

    if level_filter and level_filter in [c[0] for c in Course.Level.choices]:
        courses = courses.filter(level=level_filter)

    if query:
        courses = courses.filter(title__icontains=query)

    page_title = f"Programs & Courses - {inst.name}" if inst else "Curriculum & Programs"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "courses": courses,
        "levels": Course.Level.choices,
        "current_level": level_filter,
        "search_query": query,
    }
    return render(request, "core/courses_list.html", context)


def course_detail_view(request, slug=None, course_slug=None):
    """
    Course Details: Detailed syllabus, eligibility, and fee structure.
    """
    if course_slug:
        inst = get_resolved_institution(request, slug)
        target_slug = course_slug
    else:
        inst = get_resolved_institution(request)
        target_slug = slug

    if inst:
        course = get_object_or_404(
            Course,
            Q(institution=inst) | Q(institution__isnull=True),
            slug=target_slug,
            is_active=True,
        )
        related_courses = Course.objects.filter(
            Q(institution=inst) | Q(institution__isnull=True),
            is_active=True,
            department=course.department,
        ).exclude(id=course.id)[:3]
    else:
        course = get_object_or_404(Course, slug=target_slug, is_active=True)
        related_courses = Course.objects.filter(is_active=True, department=course.department).exclude(id=course.id)[:3]

    context = {
        "page_title": f"{course.title} ({course.code}) - {inst.name if inst else 'EduConnect'}",
        "institution": inst,
        "current_institution": inst,
        "course": course,
        "related_courses": related_courses,
    }
    return render(request, "core/course_detail.html", context)


def faculty_view(request, slug=None):
    """
    4. Faculty: Verified educators and mentors for the institution.
       Exposes public bios and subjects while keeping private personal contact data hidden.
    """
    inst = get_resolved_institution(request, slug)

    faculty_members = []
    if inst:
        memberships = InstitutionMembership.objects.filter(
            institution=inst,
            role=Role.TEACHER,
            is_active=True,
        ).select_related("user")
        faculty_members = [m.user for m in memberships]

        if not faculty_members:
            faculty_members = list(User.objects.filter(institution=inst, role=Role.TEACHER))
    else:
        faculty_members = list(User.objects.filter(role=Role.TEACHER)[:12])

    page_title = f"Teaching Faculty & Mentors - {inst.name}" if inst else "Faculty & Educators"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "faculty_members": faculty_members,
    }
    return render(request, "core/faculty.html", context)


def batches_view(request, slug=None):
    """
    5. Batches: Public academic cohorts, timings, target grade, and stream schedules.
       Strict confidentiality: Never leaks student enrolments or private billing ledgers.
    """
    inst = get_resolved_institution(request, slug)

    if inst:
        batches = Batch.objects.filter(
            institution=inst,
            status__in=[Batch.Status.ONGOING, Batch.Status.UPCOMING],
        ).select_related("course", "branch").order_by("start_date")
    else:
        batches = Batch.objects.filter(
            status__in=[Batch.Status.ONGOING, Batch.Status.UPCOMING],
        ).select_related("course", "branch").order_by("start_date")[:12]

    page_title = f"Coaching Batches & Cohorts - {inst.name}" if inst else "Batches & Schedules"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "batches": batches,
    }
    return render(request, "core/batches.html", context)


def achievements_view(request, slug=None):
    """
    6. Achievements: Olympiads, athletic honors, and distinctions.
    """
    inst = get_resolved_institution(request, slug)

    if inst:
        achievements = Achievement.objects.filter(Q(institution=inst) | Q(institution__isnull=True))
    else:
        achievements = Achievement.objects.all()

    category_filter = request.GET.get("category", "")
    if category_filter and category_filter in [c[0] for c in Achievement.Category.choices]:
        achievements = achievements.filter(category=category_filter)

    page_title = f"Achievements & Honors - {inst.name}" if inst else "Achievements & Distinctions"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "achievements": achievements,
        "categories": Achievement.Category.choices,
        "current_category": category_filter,
    }
    return render(request, "core/achievements.html", context)


def gallery_view(request, slug=None):
    """
    7. Gallery: Campus facilities, STEM laboratories, and student activities.
    """
    inst = get_resolved_institution(request, slug)

    if inst:
        gallery_items = GalleryItem.objects.filter(Q(institution=inst) | Q(institution__isnull=True), is_active=True)
    else:
        gallery_items = GalleryItem.objects.filter(is_active=True)

    category_filter = request.GET.get("category", "")
    if category_filter and category_filter in [c[0] for c in GalleryItem.Category.choices]:
        gallery_items = gallery_items.filter(category=category_filter)

    page_title = f"Campus Life & Gallery - {inst.name}" if inst else "Campus Life & Gallery"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "gallery_items": gallery_items,
        "categories": GalleryItem.Category.choices,
        "current_category": category_filter,
    }
    return render(request, "core/gallery.html", context)


def admissions_view(request, slug=None):
    """
    8. Admission Enquiry: Prospective student inquiries.
       CRITICAL: Enforces that inquiries are strictly saved to the resolved institute context!
    """
    inst = get_resolved_institution(request, slug)

    if request.method == "POST":
        form = AdmissionInquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save(commit=False)
            if inst:
                inquiry.institution = inst
            inquiry.save()

            # Simultaneously register lead in Admissions CRM if available
            try:
                target_course = None
                if inst:
                    target_course = Course.objects.filter(
                        institution=inst,
                        title__icontains=inquiry.target_program.strip(),
                    ).first()

                if inst:
                    Enquiry.objects.create(
                        institution=inst,
                        name=inquiry.applicant_name,
                        email=inquiry.email,
                        phone=inquiry.phone,
                        target_class=inquiry.target_program[:60],
                        course=target_course,
                        source=EnquirySource.WEBSITE,
                    )
            except Exception as e:
                logger.warning(f"CRM lead creation non-fatal notice: {e}")

            messages.success(
                request,
                f"Thank you, {inquiry.applicant_name}! Your admissions inquiry for '{inquiry.target_program}' has been received. Our admissions counselor will contact you at {inquiry.email}.",
            )
            redirect_url = f"/institute/{inst.slug}/admissions/" if (slug and inst) else "core:admissions"
            return redirect(redirect_url)
        messages.error(request, "Please correct the errors in the form before resubmitting.")
    else:
        initial_data = {}
        program_pref = request.GET.get("program")
        if program_pref:
            initial_data["target_program"] = program_pref
        form = AdmissionInquiryForm(initial=initial_data)

    if inst:
        courses = Course.objects.filter(Q(institution=inst) | Q(institution__isnull=True), is_active=True).order_by("level")
    else:
        courses = Course.objects.filter(is_active=True).order_by("level")

    page_title = f"Admissions & Enrolment - {inst.name}" if inst else "Admissions & Enrollment"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "form": form,
        "courses": courses,
    }
    return render(request, "core/admissions.html", context)


def contact_view(request, slug=None):
    """
    9. Contact: Campus location, phone, email, public alert, and inquiry submission.
       Saves contact message tied directly to the institution.
    """
    inst = get_resolved_institution(request, slug)

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            if inst:
                contact.institution = inst
            contact.save()
            messages.success(
                request,
                f"Thank you for contacting {inst.name if inst else 'EduConnect'}. Your message has been received by our administrative office.",
            )
            redirect_url = f"/institute/{inst.slug}/contact/" if (slug and inst) else "core:contact"
            return redirect(redirect_url)
        messages.error(request, "Please correct the errors in the form before submitting.")
    else:
        form = ContactForm()

    page_title = f"Contact Campus & Administration - {inst.name}" if inst else "Contact Administration"

    context = {
        "page_title": page_title,
        "institution": inst,
        "current_institution": inst,
        "form": form,
    }
    return render(request, "core/contact.html", context)


def institute_login_view(request, slug=None):
    """
    10. Login: Multi-institute login landing.
        Pre-binds active institution in session and renders or redirects to authentication.
    """
    inst = get_resolved_institution(request, slug)
    if inst:
        request.session["active_institution_id"] = str(inst.id)

    # If user already authenticated, redirect to role dashboard
    if request.user.is_authenticated:
        return redirect("accounts:dashboard_redirect")

    return redirect("accounts:login")


# ==============================================================================
# Progressive Web App (PWA) Endpoints
# ==============================================================================

def pwa_manifest(request):
    """
    Dynamic Web App Manifest (manifest.json / manifest.webmanifest).
    Configures app name, short name, start URL, theme colors, and icons
    dynamically per active institution branding.
    """
    inst = get_resolved_institution(request)

    app_name = inst.name if inst else "EduConnect"
    short_name = inst.code if inst else "EduConnect"
    description = inst.tagline if (inst and inst.tagline) else "EduConnect School & College Management Platform"
    theme_color = inst.primary_color if (inst and inst.primary_color) else "#6366f1"
    bg_color = "#0b0f19"

    start_url = f"/institute/{inst.slug}/" if (inst and inst.slug) else "/"

    manifest_data = {
        "name": app_name,
        "short_name": short_name,
        "description": description,
        "start_url": start_url,
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": bg_color,
        "theme_color": theme_color,
        "categories": ["education", "productivity"],
        "icons": [
            {
                "src": "/static/img/icons/icon-72x72.png",
                "sizes": "72x72",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/img/icons/icon-96x96.png",
                "sizes": "96x96",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/img/icons/icon-128x128.png",
                "sizes": "128x128",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/img/icons/icon-144x144.png",
                "sizes": "144x144",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/img/icons/icon-152x152.png",
                "sizes": "152x152",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/img/icons/icon-192x192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/img/icons/icon-384x384.png",
                "sizes": "384x384",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/img/icons/icon-512x512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            }
        ]
    }

    response = HttpResponse(json.dumps(manifest_data, indent=2), content_type="application/manifest+json; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"
    return response


def service_worker_view(request):
    """
    Serves the Progressive Web App Service Worker from root domain /sw.js
    with appropriate Service-Worker-Allowed: / scope headers.
    """
    sw_file_path = os.path.join(settings.BASE_DIR, "static", "js", "sw.js")
    try:
        with open(sw_file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"Error reading service worker file: {e}")
        content = "console.log('EduConnect SW fallback');"

    response = HttpResponse(content, content_type="application/javascript; charset=utf-8")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


def offline_view(request):
    """
    Dedicated Offline Fallback Page for the Progressive Web App.
    Explains which operations require internet and enables connection auto-retry.
    """
    inst = get_resolved_institution(request)
    context = {
        "page_title": "Offline - Connection Required",
        "institution": inst,
        "current_institution": inst,
    }
    return render(request, "core/offline.html", context)

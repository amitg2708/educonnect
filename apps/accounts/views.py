"""
EduConnect Authentication, Profile, and Role Dashboard Views.
Strict server-side enforcement and parent-child authorization checks.
"""

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View

from .decorators import (
    admin_required,
    teacher_required,
    student_required,
    parent_required,
    accounts_required,
    applicant_required,
)
from .forms import (
    EduConnectLoginForm,
    EduConnectRegistrationForm,
    UserProfileForm,
    ParentChildLinkAdminForm,
)
from .models import Role, User, ParentStudentLink


class EduConnectLoginView(LoginView):
    """
    Production-grade login view with custom forms and role routing.
    """

    form_class = EduConnectLoginForm
    template_name = "accounts/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = self.request.GET.get("next") or self.request.POST.get("next")
        if next_url:
            return next_url
        return reverse("accounts:dashboard_redirect")

    def form_valid(self, form):
        messages.success(
            self.request,
            f"Welcome back, {form.get_user().get_full_name() or form.get_user().username}! Successfully logged in.",
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Invalid username or password. Please verify your credentials and try again.",
        )
        return super().form_invalid(form)


class EduConnectLogoutView(View):
    """
    Secure logout view that invalidates user sessions.
    """

    def post(self, request, *args, **kwargs):
        logout(request)
        messages.info(request, "You have been logged out safely.")
        return redirect("accounts:login")

    def get(self, request, *args, **kwargs):
        # Also handle GET safely with confirmation/logout
        logout(request)
        messages.info(request, "You have been logged out safely.")
        return redirect("accounts:login")


class EduConnectRegisterView(View):
    """
    Public registration view with strict role filtering.
    """

    template_name = "accounts/register.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard_redirect")
        form = EduConnectRegistrationForm()
        return render(request, self.template_name, {"form": form})

    def post(self, request):
        if request.user.is_authenticated:
            return redirect("accounts:dashboard_redirect")

        form = EduConnectRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Automatically log in newly registered user
            login(request, user)
            messages.success(
                request,
                f"Account created successfully! Welcome to EduConnect as {user.get_role_display()}.",
            )
            return redirect("accounts:dashboard_redirect")

        messages.error(request, "Please correct the errors in the registration form.")
        return render(request, self.template_name, {"form": form})


@login_required
def dashboard_redirect_view(request):
    """
    Central dispatcher routing users to their specific role dashboard for active institute.
    """
    active_role = getattr(request, "user_role", None) or request.user.role
    url_name = request.user.get_dashboard_url_name(role=active_role)
    return redirect(url_name)


# ==============================================================================
# Role Dashboards (Protected with server-side decorators)
# ==============================================================================

@admin_required
def admin_dashboard(request):
    """
    Role 1: Admin Dashboard with live database metrics scoped to active institution.
    """
    from apps.reports.services import get_admin_dashboard_metrics
    from apps.reports.models import AdminAuditLog
    from apps.institutions.models import InstitutionMembership
    inst = getattr(request, "institution", None)
    metrics = get_admin_dashboard_metrics(institution=inst)

    if inst and not request.user.is_superuser:
        recent_memberships = InstitutionMembership.objects.filter(
            institution=inst,
        ).select_related("user").order_by("-joined_at")[:8]
        recent_users = [m.user for m in recent_memberships]
        active_links = ParentStudentLink.objects.filter(
            models.Q(institution=inst) | models.Q(institution__isnull=True)
        ).select_related("parent", "student").order_by("-created_at")[:6]
        recent_logs = AdminAuditLog.objects.filter(institution=inst).select_related("actor").order_by("-created_at")[:6]
    else:
        recent_users = User.objects.order_by("-date_joined")[:8]
        active_links = ParentStudentLink.objects.select_related("parent", "student").order_by("-created_at")[:6]
        recent_logs = AdminAuditLog.objects.select_related("actor").order_by("-created_at")[:6]

    context = {
        **metrics,
        "page_title": f"Admin Console - {inst.name if inst else 'EduConnect'}",
        "recent_users": recent_users,
        "active_links": active_links,
        "recent_logs": recent_logs,
        "institution": inst,
    }
    return render(request, "reports/admin/dashboard.html", context)


@teacher_required
def teacher_dashboard(request):
    """
    Role 2: Subject Teacher Dashboard scoped to active institution.
    """
    from apps.attendance.models import ClassRoom
    inst = getattr(request, "institution", None)
    students = User.objects.none()

    if inst:
        teacher_classrooms = ClassRoom.objects.filter(
            institution=inst,
            teacher_assignments__teacher=request.user,
            teacher_assignments__is_active=True,
        ).distinct()
        students = User.objects.filter(
            class_enrollments__classroom__in=teacher_classrooms,
            class_enrollments__is_active=True,
        ).distinct().order_by("last_name", "first_name")[:12]

        if not students.exists():
            students = User.objects.filter(
                class_enrollments__classroom__institution=inst,
                class_enrollments__is_active=True,
            ).distinct().order_by("last_name", "first_name")[:12]
    else:
        students = User.objects.filter(role=Role.STUDENT).order_by("last_name", "first_name")[:12]

    context = {
        "page_title": f"Teacher Portal - {inst.name if inst else 'EduConnect'}",
        "teacher": request.user,
        "students": students,
        "institution": inst,
    }
    return render(request, "accounts/dashboards/teacher.html", context)


@student_required
def student_dashboard(request):
    """
    Role 3: Student Dashboard.
    Ensures student can only access their own educational profile and enrolled subjects.
    """
    inst = getattr(request, "institution", None)
    parent_links = ParentStudentLink.objects.filter(student=request.user, is_authorized=True)
    if inst:
        parent_links = parent_links.filter(models.Q(institution=inst) | models.Q(institution__isnull=True))
    parent_links = parent_links.select_related("parent")

    context = {
        "page_title": "Student Academic Portal",
        "student": request.user,
        "parent_links": parent_links,
        "institution": inst,
    }
    return render(request, "accounts/dashboards/student.html", context)


@parent_required
def parent_dashboard(request):
    """
    Role 4: Parent Dashboard.
    Only shows authorized children linked to the requesting parent within the active institute.
    """
    inst = getattr(request, "institution", None)
    child_links = ParentStudentLink.objects.filter(parent=request.user, is_authorized=True)
    if inst:
        child_links = child_links.filter(models.Q(institution=inst) | models.Q(institution__isnull=True))
    child_links = child_links.select_related("student")

    context = {
        "page_title": "Parent / Guardian Portal",
        "parent": request.user,
        "child_links": child_links,
        "institution": inst,
    }
    return render(request, "accounts/dashboards/parent.html", context)


@parent_required
def parent_child_detail(request, student_id):
    """
    View specific details for a linked student.
    Enforces authorization: parent MUST have a verified link to the requested student in this institution.
    """
    inst = getattr(request, "institution", None)
    links = ParentStudentLink.objects.filter(
        parent=request.user,
        student__id=student_id,
        is_authorized=True,
    )
    if inst:
        links = links.filter(models.Q(institution=inst) | models.Q(institution__isnull=True))

    link = links.select_related("student").first()

    if not link:
        raise PermissionDenied("You are not authorized to access records for this student at this institution.")

    context = {
        "page_title": f"Child Profile: {link.student.get_full_name() or link.student.username}",
        "student": link.student,
        "link": link,
        "institution": inst,
    }
    return render(request, "accounts/dashboards/child_detail.html", context)


@accounts_required
def accounts_dashboard(request):
    """
    Role 5: Accounts Staff Dashboard scoped to active institution.
    """
    inst = getattr(request, "institution", None)
    if inst:
        students_count = User.objects.filter(
            class_enrollments__classroom__institution=inst,
            class_enrollments__is_active=True,
        ).distinct().count()
    else:
        students_count = User.objects.filter(role=Role.STUDENT).count()

    context = {
        "page_title": f"Accounts & Billing Portal - {inst.name if inst else 'EduConnect'}",
        "accounts_staff": request.user,
        "students_count": students_count,
        "institution": inst,
    }
    return render(request, "accounts/dashboards/accounts.html", context)


@applicant_required
def applicant_dashboard(request):
    """
    Role 6: Applicant Dashboard with live admissions tracking.
    """
    from apps.admissions.models import AdmissionApplication
    inst = getattr(request, "institution", None)
    applications = AdmissionApplication.objects.filter(applicant=request.user)
    if inst:
        applications = applications.filter(models.Q(institution=inst) | models.Q(institution__isnull=True))
    applications = applications.order_by("-submitted_at")

    context = {
        "page_title": "Admissions & Applicant Portal",
        "applicant": request.user,
        "applications": applications,
        "institution": inst,
    }
    return render(request, "accounts/dashboards/applicant.html", context)


# ==============================================================================
# User Profile View
# ==============================================================================

@login_required
def user_profile_view(request):
    """
    User profile viewing and updating.
    """
    if request.method == "POST":
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully.")
            return redirect("accounts:profile")
        messages.error(request, "Please correct the errors in the profile form.")
    else:
        form = UserProfileForm(instance=request.user)

    context = {
        "page_title": "User Profile",
        "form": form,
        "user": request.user,
    }
    return render(request, "accounts/profile.html", context)


# ==============================================================================
# Admin User & Parent-Student Management
# ==============================================================================

@admin_required
def admin_manage_users(request):
    """
    Administrative overview of all users with role filtering.
    """
    role_filter = request.GET.get("role", "")
    users = User.objects.all().order_by("-date_joined")
    if role_filter and role_filter in [r[0] for r in Role.choices]:
        users = users.filter(role=role_filter)

    context = {
        "page_title": "User Management Directory",
        "users": users,
        "roles": Role.choices,
        "current_role": role_filter,
    }
    return render(request, "accounts/admin_users.html", context)


@admin_required
def admin_link_parent_child(request):
    """
    Create or manage parent-to-student links.
    """
    if request.method == "POST":
        form = ParentChildLinkAdminForm(request.POST)
        if form.is_valid():
            link = form.save(commit=False)
            inst = getattr(request, "institution", None)
            if inst and not link.institution:
                link.institution = inst
            link.save()
            messages.success(
                request,
                f"Successfully linked Parent '{link.parent.get_full_name() or link.parent.username}' to Student '{link.student.get_full_name() or link.student.username}'.",
            )
            return redirect("accounts:admin_dashboard")
        messages.error(request, "Could not create link. Check if the pair is already linked.")
    else:
        form = ParentChildLinkAdminForm()

    context = {
        "page_title": "Authorize Parent-Student Relationship",
        "form": form,
    }
    return render(request, "accounts/link_parent_child.html", context)

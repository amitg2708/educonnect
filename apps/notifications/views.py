"""
Views for EduConnect Notifications, Announcements, and Complete Parent Portal Hub.
Implements in-app notifications, mark-as-read, announcement publication & targeting,
and unified multi-child monitoring for parents.
"""

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.models import ParentStudentLink, Role, User
from apps.attendance.models import AttendancePolicy, AttendanceRecord, ClassEnrollment
from apps.attendance.services import calculate_student_attendance_summary
from apps.academics.models import Assignment, StudentAssessmentScore
from apps.fees.models import FeeInstallment, InstallmentStatus, StudentFeeAllocation
from apps.notifications.forms import AnnouncementForm
from apps.notifications.models import (
    Announcement,
    Notification,
    NotificationCategory,
)
from apps.notifications.services import (
    get_user_announcements,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)
from apps.timetable.models import ScheduleStatus, TimetableSlot


# ==============================================================================
# IN-APP NOTIFICATIONS VIEWS
# ==============================================================================

@login_required
def my_notifications_list(request):
    """
    List chronological in-app notifications for the logged-in user.
    """
    notifications = Notification.objects.filter(recipient=request.user)
    filter_type = request.GET.get("filter")
    if filter_type == "unread":
        notifications = notifications.filter(is_read=False)

    unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()

    context = {
        "notifications": notifications,
        "unread_count": unread_count,
        "selected_filter": filter_type,
    }
    return render(request, "notifications/list.html", context)


@login_required
def mark_read_view(request, notification_id):
    """
    Mark a single notification as read and redirect to its action URL if present.
    """
    notification = get_object_or_404(Notification, id=notification_id)
    if notification.recipient != request.user and request.user.role != Role.ADMIN:
        raise PermissionDenied("You can only update your own notifications.")

    notification.mark_as_read()
    if notification.action_url:
        return redirect(notification.action_url)
    return redirect("notifications:my_notifications")


@login_required
def mark_all_read_view(request):
    """
    Mark all unread notifications as read.
    """
    if request.method == "POST":
        count = mark_all_notifications_as_read(request.user)
        messages.success(request, f"Marked {count} notifications as read.")
    return redirect("notifications:my_notifications")


# ==============================================================================
# CAMPUS ANNOUNCEMENTS VIEWS
# ==============================================================================

@login_required
def announcements_list(request):
    """
    List active campus notices and announcements targeted to current user.
    """
    inst = getattr(request, "institution", None)
    announcements = get_user_announcements(request.user, institution=inst)
    return render(
        request,
        "notifications/announcements_list.html",
        {"announcements": announcements},
    )


@login_required
def announcement_detail(request, announcement_id):
    """
    Full view of an announcement with attachment download.
    """
    announcement = get_object_or_404(Announcement, id=announcement_id)
    inst = getattr(request, "institution", None)
    if inst and announcement.institution and announcement.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to announcement outside your active institution.")

    return render(
        request,
        "notifications/announcement_detail.html",
        {"announcement": announcement},
    )


@login_required
@role_required(Role.ADMIN)
def admin_announcements_desk(request):
    """
    Admin desk to publish, target, and manage campus announcements.
    """
    inst = getattr(request, "institution", None)
    if request.method == "POST":
        form = AnnouncementForm(request.POST, request.FILES)
        if form.is_valid():
            announcement = form.save(commit=False)
            announcement.published_by = request.user
            if inst:
                announcement.institution = inst
            announcement.save()
            messages.success(request, f"Announcement '{announcement.title}' published successfully.")
            return redirect("notifications:admin_announcements")
    else:
        form = AnnouncementForm()

    all_announcements = Announcement.objects.select_related("published_by", "target_classroom", "target_batch").all()
    if inst:
        all_announcements = all_announcements.filter(institution=inst)

    return render(
        request,
        "notifications/admin_announcements.html",
        {"form": form, "announcements": all_announcements},
    )


# ==============================================================================
# COMPLETE PARENT PORTAL HUB (PART 10)
# ==============================================================================

@login_required
@role_required(Role.PARENT)
def parent_portal_hub(request, student_id=None):
    """
    Unified parent command center:
    - Lists authorized linked children
    - Switch seamlessly between children
    - 360-degree overview: attendance %, fee balances, published exam grades,
      coursework assignments, daily timetable, and targeted school notices
    - Single-click deep links to specific child desks and grievance ticketing
    """
    parent = request.user
    inst = getattr(request, "institution", None)
    children_links = ParentStudentLink.objects.filter(
        parent=parent, is_authorized=True
    ).select_related("student")
    if inst:
        children_links = children_links.filter(institution=inst)

    if not children_links.exists():
        messages.warning(request, "No authorized student profiles are linked to your parent account at this institution.")
        return render(
            request,
            "notifications/parent/hub.html",
            {"children_links": [], "selected_student": None},
        )

    # Select child
    if student_id:
        active_link = get_object_or_404(children_links, student_id=student_id)
        selected_student = active_link.student
        relationship_name = active_link.get_relationship_type_display()
    else:
        first_link = children_links.first()
        selected_student = first_link.student
        relationship_name = first_link.get_relationship_type_display()

    # 1. Enrolled Classroom
    enrollment = (
        ClassEnrollment.objects.filter(student=selected_student, is_active=True)
        .select_related("classroom", "classroom__academic_session")
        .first()
    )
    classroom = enrollment.classroom if enrollment else None

    # 2. Attendance Metrics
    attendance_metrics = None
    if classroom:
        attendance_metrics = calculate_student_attendance_summary(
            student=selected_student,
            classroom=classroom,
        )

    # 3. Fees Overview
    allocation = (
        StudentFeeAllocation.objects.filter(student=selected_student)
        .select_related("fee_structure")
        .first()
    )
    upcoming_installments = []
    if allocation:
        upcoming_installments = (
            FeeInstallment.objects.filter(allocation=allocation)
            .exclude(status=InstallmentStatus.PAID)
            .order_by("due_date")[:3]
        )

    # 4. Published Academic Grades (Strictly Published ONLY)
    scores = (
        StudentAssessmentScore.objects.filter(
            student=selected_student,
            assessment__is_published=True,
        )
        .select_related("assessment")
        .order_by("-assessment__date_conducted")[:5]
    )

    # 5. Coursework Assignments
    assignments = []
    if classroom:
        assignments = Assignment.objects.filter(
            classroom=classroom,
            is_published=True,
        ).order_by("due_datetime")[:5]

    # 6. Today's Timetable Routine
    today_code = timezone.now().isoweekday()
    timetable_today = []
    if classroom:
        timetable_today = TimetableSlot.objects.filter(
            classroom=classroom,
            day_of_week=today_code,
            status=ScheduleStatus.ACTIVE,
        ).select_related("teacher").order_by("start_time")

    # 7. Targeted Campus Notices for Child & Parent
    announcements = get_user_announcements(parent, institution=inst)[:5]

    context = {
        "children_links": children_links,
        "selected_student": selected_student,
        "relationship_name": relationship_name,
        "enrollment": enrollment,
        "classroom": classroom,
        "attendance_metrics": attendance_metrics,
        "allocation": allocation,
        "upcoming_installments": upcoming_installments,
        "scores": scores,
        "assignments": assignments,
        "timetable_today": timetable_today,
        "announcements": announcements,
    }
    return render(request, "notifications/parent/hub.html", context)

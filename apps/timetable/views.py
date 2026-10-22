"""
EduConnect Timetable Views.
Implements:
- Student & Parent views (Weekly matrix, daily classes, schedule change notifications)
- Teacher schedule view (Multi-classroom weekly timetable)
- Admin control center (Conflict validation, slot creation, cancellations & broadcasts)
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from apps.accounts.decorators import role_required
from apps.accounts.models import Role, ParentStudentLink
from apps.attendance.models import ClassRoom, ClassEnrollment
from .models import (
    TimetableSlot,
    ScheduleStatus,
    ScheduleNotification,
    DayOfWeek,
)
from .forms import TimetableSlotForm, CancelSlotForm
from .services import (
    build_weekly_matrix,
    save_timetable_slot_with_conflict_check,
)

User = get_user_model()


# ==============================================================================
# STUDENT & PARENT VIEWS
# ==============================================================================

@login_required
@role_required(Role.STUDENT, Role.ADMIN)
def student_timetable_view(request):
    """
    Personal weekly and daily timetable for enrolled student's classroom.
    Shows class schedule, room numbers, teachers, and live change notifications.
    """
    enrollment = ClassEnrollment.objects.filter(student=request.user, is_active=True).select_related("classroom").first()

    if not enrollment:
        return render(
            request,
            "timetable/student/my_timetable.html",
            {"classroom": None, "slots": [], "matrix": {}, "notifications": []},
        )

    classroom = enrollment.classroom
    slots = (
        TimetableSlot.objects.filter(classroom=classroom, is_published=True)
        .select_related("teacher", "classroom")
        .order_by("day_of_week", "start_time")
    )

    matrix = build_weekly_matrix(slots)
    notifications = ScheduleNotification.objects.filter(target_classroom=classroom).order_by("-created_at")[:10]

    context = {
        "classroom": classroom,
        "slots": slots,
        "matrix": matrix,
        "notifications": notifications,
        "day_choices": DayOfWeek.choices,
    }
    return render(request, "timetable/student/my_timetable.html", context)


@login_required
@role_required(Role.PARENT, Role.ADMIN)
def parent_child_timetable_view(request, student_id):
    """
    Timetable view for authorized parents of linked children.
    Strictly verifies parent-child authorization link.
    """
    link_filter = {
        "parent": request.user,
        "student_id": student_id,
        "is_authorized": True,
    }
    inst = getattr(request, "institution", None)
    if inst:
        link_filter["institution"] = inst

    if not request.user.is_superuser and request.user.role == Role.PARENT:
        is_linked = ParentStudentLink.objects.filter(**link_filter).exists()
        if not is_linked:
            raise PermissionDenied("You are not authorized to view timetable records for this student.")

    child = get_object_or_404(User, id=student_id, role=Role.STUDENT)
    enrollment = ClassEnrollment.objects.filter(student=child, is_active=True).select_related("classroom").first()

    if not enrollment:
        return render(
            request,
            "timetable/parent/child_timetable.html",
            {"child": child, "classroom": None, "slots": [], "matrix": {}, "notifications": []},
        )

    classroom = enrollment.classroom
    slots = (
        TimetableSlot.objects.filter(classroom=classroom, is_published=True)
        .select_related("teacher", "classroom")
        .order_by("day_of_week", "start_time")
    )

    matrix = build_weekly_matrix(slots)
    notifications = ScheduleNotification.objects.filter(target_classroom=classroom).order_by("-created_at")[:10]

    context = {
        "child": child,
        "classroom": classroom,
        "slots": slots,
        "matrix": matrix,
        "notifications": notifications,
        "day_choices": DayOfWeek.choices,
    }
    return render(request, "timetable/parent/child_timetable.html", context)


# ==============================================================================
# TEACHER VIEW
# ==============================================================================

@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_timetable_view(request):
    """
    Personal weekly teaching schedule for a subject teacher across all assigned classrooms.
    """
    inst = getattr(request, "institution", None)
    slots = (
        TimetableSlot.objects.filter(teacher=request.user)
        .select_related("classroom", "classroom__academic_session")
        .order_by("day_of_week", "start_time")
    )
    if inst:
        slots = slots.filter(classroom__institution=inst)

    matrix = build_weekly_matrix(slots)

    context = {
        "slots": slots,
        "matrix": matrix,
        "total_slots": slots.count(),
        "day_choices": DayOfWeek.choices,
    }
    return render(request, "timetable/teacher/my_schedule.html", context)


# ==============================================================================
# ADMIN VIEWS
# ==============================================================================

@login_required
@role_required(Role.ADMIN)
def admin_timetable_dashboard(request):
    """
    Administrative Timetable Workspace:
    - Filter by classroom
    - View weekly grid
    - Add, edit, or cancel slots
    - Monitor conflict logs
    """
    inst = getattr(request, "institution", None)
    classrooms = ClassRoom.objects.filter(is_active=True).order_by("name")
    if inst:
        classrooms = classrooms.filter(institution=inst)
    selected_class_id = request.GET.get("classroom", "").strip()

    target_classroom = None
    matrix = {}
    slots = []

    if selected_class_id:
        target_classroom = get_object_or_404(ClassRoom, id=selected_class_id)
        if inst and target_classroom.institution and target_classroom.institution != inst and not request.user.is_superuser:
            raise PermissionDenied("Access denied to classroom outside your active institution.")
        slots = (
            TimetableSlot.objects.filter(classroom=target_classroom)
            .select_related("teacher", "classroom")
            .order_by("day_of_week", "start_time")
        )
        matrix = build_weekly_matrix(slots)

    notifications = ScheduleNotification.objects.select_related("target_classroom", "slot")
    if inst:
        notifications = notifications.filter(target_classroom__institution=inst)
    notifications = notifications.order_by("-created_at")[:10]

    context = {
        "classrooms": classrooms,
        "selected_class_id": selected_class_id,
        "target_classroom": target_classroom,
        "slots": slots,
        "matrix": matrix,
        "notifications": notifications,
        "day_choices": DayOfWeek.choices,
    }
    return render(request, "timetable/admin/dashboard.html", context)


@login_required
@role_required(Role.ADMIN)
def admin_create_slot(request):
    """
    Create a new timetable slot with server-side conflict verification.
    """
    initial_class = request.GET.get("classroom")
    if request.method == "POST":
        form = TimetableSlotForm(request.POST)
        if form.is_valid():
            try:
                slot = save_timetable_slot_with_conflict_check(
                    classroom=form.cleaned_data["classroom"],
                    subject_name=form.cleaned_data["subject_name"],
                    teacher=form.cleaned_data["teacher"],
                    room_number=form.cleaned_data["room_number"],
                    day_of_week=form.cleaned_data["day_of_week"],
                    start_time=form.cleaned_data["start_time"],
                    end_time=form.cleaned_data["end_time"],
                    status=form.cleaned_data["status"],
                    cancellation_reason=form.cleaned_data["cancellation_reason"],
                    is_published=form.cleaned_data["is_published"],
                    actor=request.user,
                )
                messages.success(request, f"Scheduled '{slot.subject_name}' on {slot.get_day_of_week_display()}.")
                return redirect(f"{redirect('timetable:admin_dashboard').url}?classroom={slot.classroom.id}")
            except ValidationError as e:
                messages.error(request, str(e.message if hasattr(e, "message") else e))
    else:
        form = TimetableSlotForm(initial={"classroom": initial_class} if initial_class else None)

    return render(request, "timetable/admin/slot_form.html", {"form": form, "action": "Create"})


@login_required
@role_required(Role.ADMIN)
def admin_edit_slot(request, slot_id):
    """
    Edit timetable slot with conflict verification.
    """
    slot = get_object_or_404(TimetableSlot.objects.select_related("classroom", "teacher"), id=slot_id)
    inst = getattr(request, "institution", None)
    if inst and slot.institution and slot.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to slot outside your active institution.")

    if request.method == "POST":
        form = TimetableSlotForm(request.POST, instance=slot)
        if form.is_valid():
            try:
                updated_slot = save_timetable_slot_with_conflict_check(
                    classroom=form.cleaned_data["classroom"],
                    subject_name=form.cleaned_data["subject_name"],
                    teacher=form.cleaned_data["teacher"],
                    room_number=form.cleaned_data["room_number"],
                    day_of_week=form.cleaned_data["day_of_week"],
                    start_time=form.cleaned_data["start_time"],
                    end_time=form.cleaned_data["end_time"],
                    slot_id=slot.id,
                    status=form.cleaned_data["status"],
                    cancellation_reason=form.cleaned_data["cancellation_reason"],
                    is_published=form.cleaned_data["is_published"],
                    actor=request.user,
                )
                messages.success(request, f"Updated schedule for '{updated_slot.subject_name}'. Notifications broadcast.")
                return redirect(f"{redirect('timetable:admin_dashboard').url}?classroom={slot.classroom.id}")
            except ValidationError as e:
                messages.error(request, str(e.message if hasattr(e, "message") else e))
    else:
        form = TimetableSlotForm(instance=slot)

    return render(request, "timetable/admin/slot_form.html", {"form": form, "action": "Edit", "slot": slot})


@login_required
@role_required(Role.ADMIN)
def admin_cancel_slot(request, slot_id):
    """
    Cancel a timetable slot and broadcast cancellation notifications to students and parents.
    """
    slot = get_object_or_404(TimetableSlot.objects.select_related("classroom", "teacher"), id=slot_id)
    inst = getattr(request, "institution", None)
    if inst and slot.institution and slot.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to slot outside your active institution.")

    if request.method == "POST":
        form = CancelSlotForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data["cancellation_reason"]
            save_timetable_slot_with_conflict_check(
                classroom=slot.classroom,
                subject_name=slot.subject_name,
                teacher=slot.teacher,
                room_number=slot.room_number,
                day_of_week=slot.day_of_week,
                start_time=slot.start_time,
                end_time=slot.end_time,
                slot_id=slot.id,
                status=ScheduleStatus.CANCELLED,
                cancellation_reason=reason,
                is_published=True,
                actor=request.user,
            )
            messages.success(request, f"Cancelled lecture '{slot.subject_name}' and broadcast notice.")
            return redirect(f"{redirect('timetable:admin_dashboard').url}?classroom={slot.classroom.id}")
    else:
        form = CancelSlotForm()

    context = {
        "slot": slot,
        "form": form,
    }
    return render(request, "timetable/admin/cancel_slot.html", context)

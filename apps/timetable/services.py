"""
EduConnect Timetable Services.
Implements:
- Server-side multi-variable conflict detection (Teacher, Classroom, Room)
- Schedule modification and cancellation with automated notifications
- Calendar matrix formatting for daily and weekly views
"""

from datetime import time
from django.core.exceptions import ValidationError
from django.db.models import Q
from .models import (
    TimetableSlot,
    ScheduleStatus,
    ScheduleNotification,
    DayOfWeek,
)


def validate_timetable_conflicts(
    classroom,
    teacher,
    room_number: str,
    day_of_week: int,
    start_time: time,
    end_time: time,
    exclude_slot_id=None,
):
    """
    Validates server-side conflict overlaps:
    Returns None if valid; raises ValidationError if an overlap is identified.
    Overlap condition:
    slot.start_time < end_time AND slot.end_time > start_time
    """
    if start_time >= end_time:
        raise ValidationError("Class end time must be strictly after start time.")

    # Base active slots query on same day of week
    overlapping_query = TimetableSlot.objects.filter(
        day_of_week=day_of_week,
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).exclude(status=ScheduleStatus.CANCELLED)

    if classroom and getattr(classroom, "institution", None):
        overlapping_query = overlapping_query.filter(institution=classroom.institution)

    if exclude_slot_id:
        overlapping_query = overlapping_query.exclude(id=exclude_slot_id)

    # 1. Teacher Conflict Check
    teacher_conflict = overlapping_query.filter(teacher=teacher).first()
    if teacher_conflict:
        t_name = teacher.get_full_name() or teacher.username
        raise ValidationError(
            f"Teacher Conflict: Faculty member {t_name} is already assigned to "
            f"'{teacher_conflict.subject_name}' ({teacher_conflict.classroom.name}) "
            f"from {teacher_conflict.start_time.strftime('%H:%M')} to {teacher_conflict.end_time.strftime('%H:%M')} on {DayOfWeek(day_of_week).label}."
        )

    # 2. Classroom Conflict Check
    class_conflict = overlapping_query.filter(classroom=classroom).first()
    if class_conflict:
        raise ValidationError(
            f"Class Conflict: Class '{classroom.name}' already has a scheduled lecture "
            f"'{class_conflict.subject_name}' from {class_conflict.start_time.strftime('%H:%M')} "
            f"to {class_conflict.end_time.strftime('%H:%M')} on {DayOfWeek(day_of_week).label}."
        )

    # 3. Room Conflict Check
    cleaned_room = room_number.strip()
    if cleaned_room:
        room_conflict = overlapping_query.filter(room_number__iexact=cleaned_room).first()
        if room_conflict:
            raise ValidationError(
                f"Room Conflict: Room '{cleaned_room}' is already booked for "
                f"'{room_conflict.classroom.name}' ({room_conflict.subject_name}) "
                f"from {room_conflict.start_time.strftime('%H:%M')} to {room_conflict.end_time.strftime('%H:%M')}."
            )

    return True


def save_timetable_slot_with_conflict_check(
    classroom,
    subject_name: str,
    teacher,
    room_number: str,
    day_of_week: int,
    start_time: time,
    end_time: time,
    slot_id=None,
    status: str = ScheduleStatus.ACTIVE,
    cancellation_reason: str = "",
    is_published: bool = True,
    actor=None,
):
    """
    Saves a timetable slot after strictly verifying no server conflicts.
    Broadcasts change notifications to students and parents if updated or cancelled.
    """
    # Only validate conflicts if slot is not cancelled
    if status != ScheduleStatus.CANCELLED:
        validate_timetable_conflicts(
            classroom=classroom,
            teacher=teacher,
            room_number=room_number,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            exclude_slot_id=slot_id,
        )

    if slot_id:
        slot = TimetableSlot.objects.get(id=slot_id)
        old_status = slot.status
        old_time = f"{slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}"
        old_room = slot.room_number

        slot.classroom = classroom
        slot.subject_name = subject_name
        slot.teacher = teacher
        slot.room_number = room_number
        slot.day_of_week = day_of_week
        slot.start_time = start_time
        slot.end_time = end_time
        slot.status = status
        slot.cancellation_reason = cancellation_reason
        slot.is_published = is_published
        slot.save()

        # If cancelled, broadcast notification
        if status == ScheduleStatus.CANCELLED and old_status != ScheduleStatus.CANCELLED:
            ScheduleNotification.objects.create(
                slot=slot,
                target_classroom=classroom,
                change_type="CANCELLED",
                title=f"Class Cancelled: {subject_name} on {DayOfWeek(day_of_week).label}",
                message=(
                    f"Notice: The scheduled lecture for {subject_name} on {DayOfWeek(day_of_week).label} "
                    f"({start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}) has been cancelled. "
                    f"Reason: {cancellation_reason or 'Administrative directive'}."
                ),
            )
        elif status == ScheduleStatus.RESCHEDULED or old_time != f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}" or old_room != room_number:
            ScheduleNotification.objects.create(
                slot=slot,
                target_classroom=classroom,
                change_type="RESCHEDULED",
                title=f"Schedule Change: {subject_name} ({DayOfWeek(day_of_week).label})",
                message=(
                    f"The lecture schedule for {subject_name} has been updated: "
                    f"{DayOfWeek(day_of_week).label} from {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')} in {room_number}."
                ),
            )

    else:
        slot = TimetableSlot.objects.create(
            institution=getattr(classroom, "institution", None),
            classroom=classroom,
            subject_name=subject_name,
            teacher=teacher,
            room_number=room_number,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            status=status,
            cancellation_reason=cancellation_reason,
            is_published=is_published,
            created_by=actor,
        )

        ScheduleNotification.objects.create(
            slot=slot,
            target_classroom=classroom,
            change_type="PUBLISHED",
            title=f"New Schedule Added: {subject_name}",
            message=(
                f"A new weekly lecture slot for {subject_name} has been scheduled on "
                f"{DayOfWeek(day_of_week).label} ({start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}) in {room_number}."
            ),
        )

    return slot


def build_weekly_matrix(slots_queryset):
    """
    Transforms a timetable slots queryset into an organized weekly calendar matrix:
    {1: [Monday slots], 2: [Tuesday slots], ..., 6: [Saturday slots]}
    """
    matrix = {day: [] for day in range(1, 7)}  # Mon to Sat
    for slot in slots_queryset.order_by("day_of_week", "start_time"):
        if slot.day_of_week in matrix:
            matrix[slot.day_of_week].append(slot)
    return matrix

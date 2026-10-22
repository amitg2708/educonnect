"""
EduConnect Timetable Management Models.
Supports conflict-validated class schedules, teacher calendars, room bookings,
weekly grid slots, cancellation reasons, and student/parent schedule change notifications.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class DayOfWeek(models.IntegerChoices):
    MONDAY = 1, "Monday"
    TUESDAY = 2, "Tuesday"
    WEDNESDAY = 3, "Wednesday"
    THURSDAY = 4, "Thursday"
    FRIDAY = 5, "Friday"
    SATURDAY = 6, "Saturday"
    SUNDAY = 7, "Sunday"


class ScheduleStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    RESCHEDULED = "rescheduled", "Rescheduled"
    CANCELLED = "cancelled", "Cancelled"


class TimetableSlot(models.Model):
    """
    Scheduled lecture or lab period in an institutional timetable.
    Strictly protected by multi-variable server conflict checks:
    - Teacher conflict
    - Classroom conflict
    - Room number conflict
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="timetable_slots",
        null=True,
        blank=True,
        help_text="Institution context for this schedule slot.",
    )
    classroom = models.ForeignKey(
        "attendance.ClassRoom",
        on_delete=models.CASCADE,
        related_name="timetable_slots",
        help_text="Target classroom cohort.",
    )
    subject_name = models.CharField(max_length=120)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="timetable_slots",
        limit_choices_to={"role": "teacher"},
    )
    room_number = models.CharField(max_length=60, help_text="e.g. Science Lab 102, Main Hall A")
    day_of_week = models.IntegerField(choices=DayOfWeek.choices, default=DayOfWeek.MONDAY)
    start_time = models.TimeField()
    end_time = models.TimeField()
    status = models.CharField(
        max_length=20,
        choices=ScheduleStatus.choices,
        default=ScheduleStatus.ACTIVE,
    )
    cancellation_reason = models.TextField(blank=True)
    is_published = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_timetable_slots",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Timetable Slot"
        verbose_name_plural = "Timetable Slots"
        ordering = ["day_of_week", "start_time"]
        indexes = [
            models.Index(fields=["classroom", "day_of_week"]),
            models.Index(fields=["teacher", "day_of_week"]),
            models.Index(fields=["room_number", "day_of_week"]),
        ]

    def __str__(self):
        day_name = self.get_day_of_week_display()
        return f"{self.subject_name} ({self.classroom.code}) - {day_name} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}"

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "Lecture end time must be after start time."})


class ScheduleNotification(models.Model):
    """
    Notification broadcast to students and parents when a timetable change occurs
    (e.g. class cancellation, room change, or rescheduling).
    """

    slot = models.ForeignKey(
        TimetableSlot,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    target_classroom = models.ForeignKey(
        "attendance.ClassRoom",
        on_delete=models.CASCADE,
        related_name="schedule_notifications",
    )
    change_type = models.CharField(max_length=30)  # e.g., "CANCELLED", "RESCHEDULED", "ROOM_CHANGE"
    title = models.CharField(max_length=220)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Schedule Notification"
        verbose_name_plural = "Schedule Notifications"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.change_type}] {self.title} ({self.created_at:%Y-%m-%d})"

"""
EduConnect Timetable Admin Configuration.
"""

from django.contrib import admin
from .models import TimetableSlot, ScheduleNotification


@admin.register(TimetableSlot)
class TimetableSlotAdmin(admin.ModelAdmin):
    list_display = (
        "subject_name",
        "classroom",
        "teacher",
        "room_number",
        "day_of_week",
        "start_time",
        "end_time",
        "status",
        "is_published",
    )
    list_filter = ("day_of_week", "status", "classroom", "is_published")
    search_fields = ("subject_name", "room_number", "teacher__username")


@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "target_classroom", "change_type", "created_at")
    list_filter = ("change_type", "created_at")

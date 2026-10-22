"""
EduConnect Attendance Admin Configuration.
"""

from django.contrib import admin
from .models import (
    AcademicSession,
    ClassRoom,
    ClassEnrollment,
    TeacherAssignment,
    AttendancePolicy,
    AttendanceSession,
    AttendanceRecord,
    AttendanceCorrectionRequest,
    AttendanceAuditLog,
)


@admin.register(AcademicSession)
class AcademicSessionAdmin(admin.ModelAdmin):
    list_display = ("name", "start_date", "end_date", "is_current")
    list_filter = ("is_current",)


class ClassEnrollmentInline(admin.TabularInline):
    model = ClassEnrollment
    extra = 1


class TeacherAssignmentInline(admin.TabularInline):
    model = TeacherAssignment
    extra = 1


@admin.register(ClassRoom)
class ClassRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "academic_session", "room_number", "is_active")
    list_filter = ("academic_session", "is_active")
    search_fields = ("name", "code")
    inlines = [ClassEnrollmentInline, TeacherAssignmentInline]


@admin.register(ClassEnrollment)
class ClassEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "classroom", "roll_number", "is_active")
    list_filter = ("classroom", "is_active")
    search_fields = ("student__username", "roll_number")


@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(admin.ModelAdmin):
    list_display = ("teacher", "classroom", "subject_name", "is_active")
    list_filter = ("classroom", "is_active")
    search_fields = ("teacher__username", "subject_name")


class AttendanceRecordInline(admin.TabularInline):
    model = AttendanceRecord
    extra = 0
    readonly_fields = ("student", "marked_by", "modified_by", "modified_at")


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ("classroom", "subject_name", "session_date", "session_period", "teacher")
    list_filter = ("session_date", "classroom")
    search_fields = ("subject_name", "topic")
    inlines = [AttendanceRecordInline]


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ("student", "session", "status", "marked_by", "modified_by")
    list_filter = ("status", "session__session_date")
    search_fields = ("student__username", "session__subject_name")


@admin.register(AttendancePolicy)
class AttendancePolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "minimum_required_percentage", "present_weight", "late_weight", "is_active")


@admin.register(AttendanceCorrectionRequest)
class AttendanceCorrectionRequestAdmin(admin.ModelAdmin):
    list_display = ("student", "record", "requested_status", "status", "created_at", "reviewer")
    list_filter = ("status", "requested_status")


@admin.register(AttendanceAuditLog)
class AttendanceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "action", "actor", "session", "record")
    list_filter = ("action", "timestamp")

"""
Django Admin configurations for EduConnect Admissions Management.
"""

from django.contrib import admin
from .models import AdmissionApplication, ApplicationDocument, ApplicationStatusHistory


class ApplicationDocumentInline(admin.TabularInline):
    model = ApplicationDocument
    extra = 0
    fields = ("document_type", "title", "file", "is_verified", "verification_notes", "uploaded_at")
    readonly_fields = ("uploaded_at",)


class ApplicationStatusHistoryInline(admin.TabularInline):
    model = ApplicationStatusHistory
    extra = 0
    fields = ("from_status", "to_status", "changed_by", "notes", "created_at")
    readonly_fields = ("created_at",)


@admin.register(AdmissionApplication)
class AdmissionApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "application_number",
        "full_name",
        "course",
        "status",
        "submitted_at",
        "decision_date",
        "student_id_assigned",
    )
    list_filter = ("status", "course__level", "submitted_at")
    search_fields = (
        "application_number",
        "first_name",
        "last_name",
        "email",
        "phone_number",
        "student_id_assigned",
    )
    readonly_fields = (
        "application_number",
        "submitted_at",
        "created_at",
        "updated_at",
    )
    inlines = [ApplicationDocumentInline, ApplicationStatusHistoryInline]


@admin.register(ApplicationDocument)
class ApplicationDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "application", "document_type", "is_verified", "file_size_bytes", "uploaded_at")
    list_filter = ("document_type", "is_verified")
    search_fields = ("title", "application__application_number")


@admin.register(ApplicationStatusHistory)
class ApplicationStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("application", "from_status", "to_status", "changed_by", "created_at")
    list_filter = ("to_status", "created_at")
    search_fields = ("application__application_number", "notes")

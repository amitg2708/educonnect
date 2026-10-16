"""
Admin configurations for EduConnect Public Portal models.
"""

from django.contrib import admin
from .models import (
    Course,
    Achievement,
    GalleryItem,
    Announcement,
    Facility,
    ContactInquiry,
    AdmissionInquiry,
)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title", "department", "level", "duration", "fee_per_term", "is_featured", "is_active")
    list_filter = ("level", "department", "is_featured", "is_active")
    search_fields = ("title", "code", "department", "description")
    prepopulated_fields = {"slug": ("code", "title")}


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "year", "recipient", "is_featured", "created_at")
    list_filter = ("category", "year", "is_featured")
    search_fields = ("title", "recipient", "description")


@admin.register(GalleryItem)
class GalleryItemAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_active", "created_at")
    list_filter = ("category", "is_active")
    search_fields = ("title", "caption")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "priority", "publish_date", "is_published")
    list_filter = ("category", "priority", "is_published")
    search_fields = ("title", "content")


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "icon", "display_order")
    list_filter = ("category",)
    search_fields = ("title", "description")


@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = ("subject", "name", "email", "phone", "is_resolved", "created_at")
    list_filter = ("is_resolved", "created_at")
    search_fields = ("name", "email", "subject", "message")


@admin.register(AdmissionInquiry)
class AdmissionInquiryAdmin(admin.ModelAdmin):
    list_display = ("applicant_name", "email", "phone", "target_program", "status", "created_at")
    list_filter = ("status", "target_program", "created_at")
    search_fields = ("applicant_name", "email", "target_program", "prior_school")

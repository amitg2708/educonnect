"""
Django Admin integration for EduConnect custom User and Parent-Student models.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ParentStudentLink


@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    """
    MongoDB-compatible Admin interface for EduConnect custom User model.
    """

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            "Personal Info",
            {"fields": ("first_name", "last_name", "email", "phone_number", "address", "bio")},
        ),
        (
            "Institutional Role & Academic Info",
            {
                "fields": (
                    "role",
                    "student_id",
                    "grade_level",
                    "employee_id",
                    "subject_specialization",
                )
            },
        ),
        (
            "Permissions & Access",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "role",
        "is_staff",
        "is_active",
    )
    list_filter = ("role", "is_staff", "is_superuser", "is_active")
    search_fields = (
        "username",
        "email",
        "first_name",
        "last_name",
        "student_id",
        "employee_id",
    )
    ordering = ("username",)


@admin.register(ParentStudentLink)
class ParentStudentLinkAdmin(admin.ModelAdmin):
    """
    Admin management for Parent-to-Student links.
    """

    list_display = (
        "parent",
        "student",
        "relationship_type",
        "is_authorized",
        "created_at",
    )
    list_filter = ("relationship_type", "is_authorized", "created_at")
    search_fields = (
        "parent__username",
        "parent__email",
        "student__username",
        "student__email",
        "student__student_id",
    )

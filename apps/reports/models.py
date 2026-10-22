"""
EduConnect Administration & Reporting Models.
Provides institutional configuration settings and immutable audit trails
for sensitive administrator actions and report exports.
"""

from decimal import Decimal
from django.conf import settings
from django.db import models


class InstitutionSetting(models.Model):
    """
    Global institution configuration and operational parameters.
    """

    institution = models.OneToOneField(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="settings",
        null=True,
        blank=True,
    )
    institution_name = models.CharField(max_length=220, default="EduConnect International Academy")
    institution_code = models.CharField(max_length=50, default="EDU-CONNECT")
    academic_year = models.CharField(max_length=30, default="2026-2027")
    contact_email = models.EmailField(default="admin@educonnect.edu")
    contact_phone = models.CharField(max_length=30, default="+1 (555) 019-2834")
    campus_address = models.TextField(default="100 Innovation Boulevard, Tech Campus")
    attendance_minimum_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("75.00"),
        help_text="Institutional minimum attendance threshold for exam eligibility.",
    )
    default_complaint_sla_days = models.PositiveIntegerField(
        default=3,
        help_text="Default turnaround time in business days for grievance resolution.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_institution_settings",
    )

    class Meta:
        verbose_name = "Institution Setting"
        verbose_name_plural = "Institution Settings"

    def __str__(self):
        return f"{self.institution_name} ({self.academic_year})"

    @classmethod
    def get_settings(cls, institution=None):
        """
        Retrieves institutional settings record for a specific institution, or default.
        """
        if institution:
            obj, _ = cls.objects.get_or_create(
                institution=institution,
                defaults={
                    "institution_name": institution.name,
                    "institution_code": institution.code,
                    "contact_email": institution.contact_email or "admin@educonnect.edu",
                    "contact_phone": institution.contact_phone or "+1 (555) 019-2834",
                    "campus_address": institution.address or "100 Innovation Boulevard, Tech Campus",
                },
            )
            return obj
        obj = cls.objects.first()
        if not obj:
            obj = cls.objects.create()
        return obj


class AdminAuditLog(models.Model):
    """
    Audit log tracking sensitive administrative interventions and report exports.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admin_audit_logs",
    )
    action = models.CharField(max_length=100)  # e.g. "SETTINGS_UPDATE", "REPORT_EXPORT", "ROLE_CHANGE"
    target_model = models.CharField(max_length=100, blank=True)
    target_id = models.CharField(max_length=100, blank=True)
    description = models.TextField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Admin Audit Log"
        verbose_name_plural = "Admin Audit Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.created_at.strftime('%Y-%m-%d %H:%M')}] {self.actor.username} -> {self.action}: {self.target_model}"

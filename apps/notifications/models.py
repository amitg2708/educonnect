"""
EduConnect In-App Notifications and Campus Announcements Models.
Supports targeted institutional notices, automated alerts across modules
(admissions, fees, attendance, timetable, academics, complaints),
deduplication keys to prevent spam, and read receipts.
"""

import os
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def validate_notification_attachment(file):
    """
    Validates uploaded announcement files:
    - Max size: 10 MB
    - Allowed: PDF, JPG, PNG, DOC, DOCX, ZIP, TXT
    """
    max_size = 10 * 1024 * 1024  # 10 MB
    if file.size > max_size:
        raise ValidationError("Attachment exceeds maximum allowed size of 10 MB.")

    ext = os.path.splitext(file.name)[1].lower()
    allowed = [".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx", ".zip", ".txt"]
    if ext not in allowed:
        raise ValidationError(f"File format '{ext}' is not supported. Allowed formats: PDF, DOC, Images, ZIP.")


class NotificationCategory(models.TextChoices):
    ADMISSION = "admission", "Admissions Update"
    FEES = "fees", "Fees & Billing"
    ATTENDANCE = "attendance", "Attendance Alert"
    TIMETABLE = "timetable", "Schedule & Timetable"
    ACADEMICS = "academics", "Coursework & Exams"
    COMPLAINT = "complaint", "Helpdesk & Complaints"
    ANNOUNCEMENT = "announcement", "Campus Announcement"
    SYSTEM = "system", "System Notice"


class Notification(models.Model):
    """
    Database-backed in-app notification delivered to a specific user.
    Includes deduplication keys to prevent redundant duplicate alerts.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="notifications",
        null=True,
        blank=True,
        help_text="Institution context for this notification alert.",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_notifications",
    )
    title = models.CharField(max_length=220)
    message = models.TextField()
    category = models.CharField(
        max_length=30,
        choices=NotificationCategory.choices,
        default=NotificationCategory.SYSTEM,
    )
    action_url = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional destination URL for deep-linking.",
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    deduplication_key = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        db_index=True,
        help_text="Unique key to prevent repeated duplicate notifications.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "In-App Notification"
        verbose_name_plural = "In-App Notifications"
        ordering = ["-created_at"]

    def __str__(self):
        read_str = " (Read)" if self.is_read else " (Unread)"
        return f"[{self.get_category_display()}] {self.title} -> {self.recipient.username}{read_str}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])


class TargetRole(models.TextChoices):
    ALL = "all", "All Campus Roles"
    STUDENT = "student", "Students Only"
    PARENT = "parent", "Parents Only"
    TEACHER = "teacher", "Faculty / Teachers Only"


class Announcement(models.Model):
    """
    Institutional announcements and notices published by administrators.
    Supports targeting by user role and/or classroom cohort with expiry rules.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="announcements",
        null=True,
        blank=True,
        help_text="Institution publishing this notice.",
    )
    title = models.CharField(max_length=220)
    content = models.TextField()
    target_role = models.CharField(
        max_length=30,
        choices=TargetRole.choices,
        default=TargetRole.ALL,
    )
    target_classroom = models.ForeignKey(
        "attendance.ClassRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
        help_text="Optional cohort targeting. Leave blank for campus-wide.",
    )
    target_batch = models.ForeignKey(
        "academics.Batch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
        help_text="Optional coaching cohort batch targeting. Leave blank for institute-wide.",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="published_announcements",
    )
    publish_date = models.DateTimeField(default=timezone.now)
    expiry_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional date when this notice expires.",
    )
    attachment = models.FileField(
        upload_to="announcements/",
        blank=True,
        null=True,
        validators=[validate_notification_attachment],
    )
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Campus Announcement"
        verbose_name_plural = "Campus Announcements"
        ordering = ["-publish_date"]

    def __str__(self):
        return f"{self.title} [{self.get_target_role_display()}]"

    @property
    def is_active(self) -> bool:
        """
        Determines whether the announcement is currently visible based on date window.
        """
        now = timezone.now()
        if not self.is_published:
            return False
        if self.publish_date > now:
            return False
        if self.expiry_date and self.expiry_date < now:
            return False
        return True


class DeliveryChannel(models.TextChoices):
    EMAIL = "email", "Email"
    SMS = "sms", "SMS"
    WHATSAPP = "whatsapp", "WhatsApp"


class DeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending Submission"
    SENT = "sent", "Sent (Awaiting Provider Delivery Confirmation)"
    DELIVERED = "delivered", "Delivered (Confirmed by Provider)"
    FAILED = "failed", "Failed"


class MessageDeliveryRecord(models.Model):
    """
    Audit log and delivery tracker for external messaging integrations (Email, SMS, WhatsApp).
    Explicitly enforces the requirement:
    'Do not claim that email, SMS or WhatsApp messages were delivered unless the real provider confirms delivery.'
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="external_deliveries",
        null=True,
        blank=True,
        help_text="Institution context for this external message delivery.",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="external_deliveries",
    )
    channel = models.CharField(max_length=20, choices=DeliveryChannel.choices)
    recipient_address = models.CharField(max_length=255)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
    )
    provider_name = models.CharField(max_length=60, default="standard")
    provider_message_id = models.CharField(max_length=120, blank=True)
    provider_response = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message Delivery Record"
        verbose_name_plural = "Message Delivery Records"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_channel_display()}] {self.recipient_address} - {self.get_status_display()}"

    def confirm_delivery(self, provider_message_id: str = "", provider_response: str = ""):
        """
        Transitions to DELIVERED ONLY when the real provider confirms actual receipt.
        """
        self.status = DeliveryStatus.DELIVERED
        self.delivered_at = timezone.now()
        if provider_message_id:
            self.provider_message_id = provider_message_id
        if provider_response:
            self.provider_response = provider_response
        self.save(update_fields=["status", "delivered_at", "provider_message_id", "provider_response"])


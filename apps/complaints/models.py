"""
EduConnect Complaints & Grievance Request Management Models.
Supports student & parent ticketing, unique ticket numbers, SLA tracking,
valid status transitions, staff internal notes isolation, reopening,
and resolution satisfaction feedback.
"""

from datetime import timedelta
import os
import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def validate_complaint_attachment(file):
    """
    Validates uploaded grievance documentation:
    - Max size: 10 MB
    - Allowed extensions: PDF, PNG, JPG, JPEG, DOC, DOCX, ZIP, TXT
    """
    max_size = 10 * 1024 * 1024  # 10 MB
    if file.size > max_size:
        raise ValidationError("Attachment exceeds maximum allowed size of 10 MB.")

    ext = os.path.splitext(file.name)[1].lower()
    allowed = [".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx", ".zip", ".txt"]
    if ext not in allowed:
        raise ValidationError(f"File format '{ext}' is not supported. Allowed formats: PDF, DOC, Images, ZIP.")


class ComplaintCategory(models.Model):
    """
    Categorization of grievances with Service Level Agreement (SLA) response windows.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="complaint_categories",
        null=True,
        blank=True,
        help_text="Institution context for this complaint category.",
    )
    code = models.CharField(max_length=50)  # e.g., "fees", "attendance", "facilities"
    name = models.CharField(max_length=120)
    sla_days = models.PositiveIntegerField(
        default=3,
        help_text="Expected resolution turnaround time in business days.",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    STANDARD_CATEGORIES = [
        ("fees", "Fee Billing & Payments", 2, "Issues related to tuition fees, receipts, installment schedules, and billing."),
        ("attendance", "Attendance & Absence Requests", 2, "Attendance discrepancies, absence notifications, and leave requests."),
        ("facilities", "Campus Facilities & Infrastructure", 3, "Classroom equipment, library, sports complex, laboratory, and sanitation issues."),
        ("teachers", "Faculty & Academic Instruction", 3, "Course delivery, syllabus queries, teacher communication, and coursework doubts."),
        ("administration", "Administration & Operational Support", 4, "General admissions, student ID cards, transport, and administrative services."),
    ]

    class Meta:
        verbose_name = "Complaint Category"
        verbose_name_plural = "Complaint Categories"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (SLA: {self.sla_days} days)"

    @classmethod
    def ensure_default_categories(cls, institution=None):
        """
        Provisions standard institutional grievance categories for fees, attendance,
        facilities, teachers, and administration with enforced SLAs.
        """
        categories = []
        for code, name, sla_days, desc in cls.STANDARD_CATEGORIES:
            cat, _ = cls.objects.get_or_create(
                code=code,
                institution=institution,
                defaults={
                    "name": name,
                    "sla_days": sla_days,
                    "description": desc,
                    "is_active": True,
                },
            )
            categories.append(cat)
        return categories


class TicketPriority(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    URGENT = "urgent", "Urgent / Escalated"


class TicketStatus(models.TextChoices):
    OPEN = "open", "Open"
    UNDER_REVIEW = "under_review", "Under Review"
    IN_PROGRESS = "in_progress", "In Progress"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"
    REOPENED = "reopened", "Reopened"


def generate_ticket_number() -> str:
    """
    Generates a unique reference ID for grievance tickets: TKT-YYYYMM-XXXXX
    """
    prefix = timezone.now().strftime("TKT-%Y%m")
    unique_suffix = uuid.uuid4().hex[:6].upper()
    return f"{prefix}-{unique_suffix}"


class ComplaintTicket(models.Model):
    """
    End-to-end issue tracking ticket submitted by students or parents.
    """

    ticket_number = models.CharField(
        max_length=32,
        unique=True,
        default=generate_ticket_number,
        editable=False,
    )
    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="complaint_tickets",
        null=True,
        blank=True,
        help_text="Institution context for this grievance ticket.",
    )
    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_complaints",
    )
    category = models.ForeignKey(
        ComplaintCategory,
        on_delete=models.PROTECT,
        related_name="tickets",
    )
    subject = models.CharField(max_length=220)
    description = models.TextField()
    priority = models.CharField(
        max_length=20,
        choices=TicketPriority.choices,
        default=TicketPriority.MEDIUM,
    )
    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.OPEN,
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_complaints",
        limit_choices_to={"role__in": ["admin", "accounts", "teacher"]},
    )
    attachment = models.FileField(
        upload_to="complaint_attachments/",
        blank=True,
        null=True,
        validators=[validate_complaint_attachment],
    )

    # Resolution & Closure
    resolution_details = models.TextField(blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_complaints",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reopen_count = models.PositiveIntegerField(default=0)

    # Post-Resolution Satisfaction Feedback
    satisfaction_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        choices=[
            (1, "1 - Very Dissatisfied"),
            (2, "2 - Dissatisfied"),
            (3, "3 - Neutral"),
            (4, "4 - Satisfied"),
            (5, "5 - Highly Satisfied"),
        ],
    )
    feedback_comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Complaint Ticket"
        verbose_name_plural = "Complaint Tickets"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.ticket_number}] {self.subject} ({self.get_status_display()})"

    @property
    def is_resolved_or_closed(self) -> bool:
        return self.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]

    @property
    def is_overdue(self) -> bool:
        """
        Flags ticket as overdue if unresolved past SLA duration.
        """
        if self.is_resolved_or_closed:
            return False
        sla_limit = self.created_at + timedelta(days=self.category.sla_days)
        return timezone.now() > sla_limit


class TicketComment(models.Model):
    """
    Chronological communication updates and notes on a complaint ticket.
    Strictly isolates internal staff notes from student/parent views.
    """

    ticket = models.ForeignKey(
        ComplaintTicket,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="complaint_comments",
    )
    message = models.TextField()
    attachment = models.FileField(
        upload_to="complaint_replies/",
        blank=True,
        null=True,
        validators=[validate_complaint_attachment],
    )
    is_internal = models.BooleanField(
        default=False,
        help_text="Internal notes are only visible to school administrators and authorized staff.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ticket Comment"
        verbose_name_plural = "Ticket Comments"
        ordering = ["created_at"]

    def __str__(self):
        scope = " [INTERNAL NOTE]" if self.is_internal else ""
        return f"{self.author.username} on {self.ticket.ticket_number}{scope}"


class TicketStatusHistory(models.Model):
    """
    Immutable audit trail for ticket lifecycle transitions.
    """

    ticket = models.ForeignKey(
        ComplaintTicket,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    old_status = models.CharField(max_length=20, choices=TicketStatus.choices)
    new_status = models.CharField(max_length=20, choices=TicketStatus.choices)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Ticket Status History"
        verbose_name_plural = "Ticket Status Histories"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.ticket.ticket_number}: {self.old_status} -> {self.new_status}"

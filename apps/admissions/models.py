"""
EduConnect Admissions Management Models.
Tracks student applications, uploaded documents, status progression,
audit logs, and student conversion.
"""

import os
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def validate_document_file(file):
    """
    Validates uploaded admission documents:
    - Permitted extensions: pdf, jpg, jpeg, png
    - Maximum file size: 5 MB
    """
    max_size = 5 * 1024 * 1024  # 5 MB
    if file.size > max_size:
        raise ValidationError("File size exceeds 5 MB. Please upload a smaller document.")

    ext = os.path.splitext(file.name)[1].lower()
    allowed_extensions = [".pdf", ".jpg", ".jpeg", ".png"]
    if ext not in allowed_extensions:
        raise ValidationError(
            f"Unsupported file format '{ext}'. Allowed formats: PDF, JPG, JPEG, PNG."
        )


class ApplicationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    UNDER_REVIEW = "under_review", "Under Review"
    ACTION_REQUIRED = "action_required", "Action Required (Missing Info/Docs)"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    ENROLLED = "enrolled", "Enrolled (Converted to Student)"


class DocumentType(models.TextChoices):
    PASSPORT_PHOTO = "passport_photo", "Passport Size Photograph"
    IDENTITY_PROOF = "identity_proof", "National ID / Passport / Birth Certificate"
    ACADEMIC_TRANSCRIPT = "academic_transcript", "Prior Academic Transcript / Marksheet"
    TRANSFER_CERTIFICATE = "transfer_certificate", "Transfer / Migration Certificate"
    STATEMENT_OF_PURPOSE = "statement_of_purpose", "Statement of Purpose"
    OTHER = "other", "Other Supporting Document"


class AdmissionApplication(models.Model):
    """
    Comprehensive student admission application.
    """

    # Unique Reference Number
    application_number = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Unique applicant tracking reference number e.g. ADM-2026-XXXXXX",
    )

    # Relationships
    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="admission_applications",
        null=True,
        blank=True,
        help_text="Target coaching institute or school.",
    )
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="admission_applications",
        help_text="Applicant user account owning this application.",
    )
    course = models.ForeignKey(
        "core.Course",
        on_delete=models.PROTECT,
        related_name="admission_applications",
        help_text="Target academic course or program.",
    )
    target_batch = models.ForeignKey(
        "academics.Batch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admission_applications",
        help_text="Target coaching batch for enrolment.",
    )
    source_enquiry = models.ForeignKey(
        "admissions.Enquiry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admission_applications",
        help_text="Originating lead/enquiry if converted.",
    )

    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField()
    phone_number = models.CharField(max_length=25)
    date_of_birth = models.DateField()
    gender = models.CharField(
        max_length=20,
        choices=[
            ("male", "Male"),
            ("female", "Female"),
            ("other", "Other"),
            ("prefer_not_to_say", "Prefer not to say"),
        ],
    )
    nationality = models.CharField(max_length=80, default="Indian")
    address_line1 = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="India")

    # Guardian / Emergency Contact
    guardian_name = models.CharField(max_length=150)
    guardian_relationship = models.CharField(
        max_length=50,
        help_text="e.g. Father, Mother, Legal Guardian",
    )
    guardian_phone = models.CharField(max_length=25)
    guardian_email = models.EmailField(blank=True)

    # Academic History
    previous_institution = models.CharField(
        max_length=200,
        help_text="Last school, college, or university attended.",
    )
    previous_qualification = models.CharField(
        max_length=100,
        help_text="e.g. Class 10 / SSC, Class 12 / HSC, Bachelor's Degree",
    )
    previous_grade_or_percentage = models.CharField(
        max_length=40,
        help_text="e.g. 88.5%, 3.9 GPA, First Class with Distinction",
    )
    year_of_passing = models.PositiveIntegerField(help_text="Year of completion")
    statement_of_purpose = models.TextField(
        blank=True,
        help_text="Brief statement describing academic goals and motivation.",
    )

    # Workflow & Decision
    status = models.CharField(
        max_length=30,
        choices=ApplicationStatus.choices,
        default=ApplicationStatus.SUBMITTED,
    )
    admin_notes = models.TextField(
        blank=True,
        help_text="Internal confidential notes for admissions officers.",
    )
    applicant_remarks = models.TextField(
        blank=True,
        help_text="Feedback, decision notes, or missing document instructions to applicant.",
    )
    missing_documents_requested = models.TextField(
        blank=True,
        help_text="Explicit list of missing documentation or details requested from applicant.",
    )
    decision_date = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decided_admissions",
    )

    # Student Conversion Tracking
    converted_student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="converted_admission",
        help_text="Student account created/linked upon official enrollment.",
    )
    student_id_assigned = models.CharField(
        max_length=50,
        blank=True,
        help_text="Enrolled student ID e.g. STU-2026-XXXXX",
    )

    # Timestamps
    submitted_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Admission Application"
        verbose_name_plural = "Admission Applications"
        ordering = ["-submitted_at"]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_editable(self):
        """
        Permits editing by the applicant only when in Draft or Action Required status.
        """
        return self.status in [ApplicationStatus.DRAFT, ApplicationStatus.ACTION_REQUIRED]

    @property
    def can_be_converted(self):
        """
        Can only be converted to Student if Approved and not yet converted.
        """
        return self.status == ApplicationStatus.APPROVED and self.converted_student is None

    @classmethod
    def generate_unique_application_number(cls):
        """
        Generates a unique, collision-resistant application reference number.
        """
        year = timezone.now().year
        while True:
            candidate = f"ADM-{year}-{secrets.token_hex(3).upper()}"
            if not cls.objects.filter(application_number=candidate).exists():
                return candidate

    def save(self, *args, **kwargs):
        if not self.application_number:
            self.application_number = self.generate_unique_application_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.application_number} - {self.full_name} ({self.course.code}) [{self.get_status_display()}]"


class ApplicationDocument(models.Model):
    """
    Supporting documents uploaded for an admission application.
    """

    application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    document_type = models.CharField(
        max_length=40,
        choices=DocumentType.choices,
        default=DocumentType.IDENTITY_PROOF,
    )
    title = models.CharField(max_length=150)
    file = models.FileField(
        upload_to="admissions/documents/%Y/%m/",
        validators=[validate_document_file],
    )
    file_size_bytes = models.PositiveIntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    verification_notes = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Application Document"
        verbose_name_plural = "Application Documents"
        ordering = ["-uploaded_at"]

    def save(self, *args, **kwargs):
        if self.file and hasattr(self.file, "size"):
            self.file_size_bytes = self.file.size
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.title} ({self.application.application_number})"


class ApplicationStatusHistory(models.Model):
    """
    Immutable audit log preserving all state transitions and decision notes.
    """

    application = models.ForeignKey(
        AdmissionApplication,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    from_status = models.CharField(max_length=30)
    to_status = models.CharField(max_length=30)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Application Status History"
        verbose_name_plural = "Application Status Histories"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.application.application_number}: {self.from_status} -> {self.to_status} at {self.created_at}"


# ==============================================================================
# COACHING ENQUIRIES & PROSPECTS CRM
# ==============================================================================

class EnquirySource(models.TextChoices):
    WEBSITE = "website", "Website / Online Portal"
    PHONE = "phone", "Phone Call / Telephonic"
    WALK_IN = "walk_in", "Walk-in / Campus Visit"
    REFERRAL = "referral", "Referral / Word of Mouth"
    OTHER = "other", "Other"


class EnquiryStatus(models.TextChoices):
    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    TRIAL_CLASS = "trial_class", "Trial Class"
    FOLLOW_UP_REQUIRED = "follow_up_required", "Follow-up Required"
    CONVERTED = "converted", "Converted"
    NOT_INTERESTED = "not_interested", "Not Interested"


class Enquiry(models.Model):
    """
    Coaching prospect lead / enquiry received through web, phone, walk-in, or referral.
    Tracks academic interest, assigned counselor, follow-up dates, and conversion to student.
    """

    enquiry_number = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Unique enquiry tracking reference number e.g. ENQ-2026-XXXXXX",
    )
    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="coaching_enquiries",
        help_text="Institution hosting this prospect.",
    )
    branch = models.ForeignKey(
        "institutions.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coaching_enquiries",
        help_text="Preferred campus branch.",
    )
    source = models.CharField(
        max_length=30,
        choices=EnquirySource.choices,
        default=EnquirySource.WEBSITE,
    )
    status = models.CharField(
        max_length=30,
        choices=EnquiryStatus.choices,
        default=EnquiryStatus.NEW,
    )

    # Lead Contact Details
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=25)
    alternate_phone = models.CharField(max_length=25, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # Academic & Cohort Interest
    target_class = models.CharField(max_length=60, blank=True, help_text="e.g. Class 10, Class 11, Class 12")
    stream = models.CharField(max_length=60, blank=True, help_text="e.g. Science, Commerce, Arts")
    course = models.ForeignKey(
        "core.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coaching_enquiries",
        help_text="Target course / curriculum.",
    )
    batch_interest = models.ForeignKey(
        "academics.Batch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coaching_enquiries",
        help_text="Preferred batch timing or cohort.",
    )

    # CRM Ownership & Workflow
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_enquiries",
        help_text="Counselor or staff member responsible for this lead.",
    )
    next_follow_up_date = models.DateField(null=True, blank=True)
    trial_class_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Inquiry details or initial requirements.")

    # Conversion Tracking
    converted_application = models.ForeignKey(
        "admissions.AdmissionApplication",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_enquiries",
    )
    converted_student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_enquiries",
    )
    converted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Coaching Enquiry"
        verbose_name_plural = "Coaching Enquiries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["institution", "status"]),
            models.Index(fields=["institution", "source"]),
            models.Index(fields=["assigned_to", "next_follow_up_date"]),
        ]

    @classmethod
    def generate_unique_enquiry_number(cls):
        year = timezone.now().year
        while True:
            candidate = f"ENQ-{year}-{secrets.token_hex(3).upper()}"
            if not cls.objects.filter(enquiry_number=candidate).exists():
                return candidate

    def save(self, *args, **kwargs):
        if not self.enquiry_number:
            self.enquiry_number = self.generate_unique_enquiry_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.enquiry_number} - {self.name} ({self.get_status_display()})"


class EnquiryFollowUp(models.Model):
    """
    Log of communications, calls, counseling sessions, or trial class feedback.
    """

    enquiry = models.ForeignKey(
        Enquiry,
        on_delete=models.CASCADE,
        related_name="follow_ups",
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recorded_enquiry_follow_ups",
    )
    contact_mode = models.CharField(
        max_length=30,
        choices=[
            ("phone", "Phone Call"),
            ("email", "Email"),
            ("walk_in", "Walk-in Counseling"),
            ("whatsapp", "WhatsApp"),
            ("trial_feedback", "Trial Class Feedback"),
            ("other", "Other"),
        ],
        default="phone",
    )
    notes = models.TextField(help_text="Summary of discussion, parent concerns, or next steps.")
    old_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)
    scheduled_follow_up_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Enquiry Follow-up"
        verbose_name_plural = "Enquiry Follow-ups"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.enquiry.enquiry_number} - {self.get_contact_mode_display()} by {self.staff.username}"


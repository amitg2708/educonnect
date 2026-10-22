"""
EduConnect Attendance Management Models.
Provides institutional academic sessions, classrooms, student enrollments,
teacher assignments, configurable attendance policies, multi-status session rosters,
correction requests, and audit logs.
"""

from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AcademicSession(models.Model):
    """
    Academic term or annual session (e.g., Fall 2026, Spring 2027, 2026-2027).
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="academic_sessions",
        null=True,
        blank=True,
        help_text="Institution managing this academic term.",
    )
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Academic Session"
        verbose_name_plural = "Academic Sessions"
        ordering = ["-start_date"]

    def __str__(self):
        status = " (Current)" if self.is_current else ""
        return f"{self.name} [{self.start_date} to {self.end_date}]{status}"

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({"end_date": "Session end date must be after start date."})


class ClassRoom(models.Model):
    """
    Institutional Class / Section / Cohort.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="classrooms",
        null=True,
        blank=True,
        help_text="Institution hosting this classroom cohort.",
    )
    branch = models.ForeignKey(
        "institutions.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="classrooms",
        help_text="Optional physical branch or campus.",
    )
    name = models.CharField(max_length=120)  # e.g., "Grade 10 - Section A"
    code = models.CharField(max_length=50)  # e.g., "CLS-10A"
    course = models.ForeignKey(
        "core.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="classrooms",
    )
    academic_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.PROTECT,
        related_name="classrooms",
    )
    room_number = models.CharField(max_length=50, blank=True)
    capacity = models.PositiveIntegerField(default=40)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Classroom / Section"
        verbose_name_plural = "Classrooms / Sections"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class ClassEnrollment(models.Model):
    """
    Enrolls a student in a specific classroom / cohort.
    """

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="class_enrollments",
        limit_choices_to={"role": "student"},
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="enrollments",
    )
    roll_number = models.CharField(max_length=30, blank=True)
    enrolled_date = models.DateField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Class Enrollment"
        verbose_name_plural = "Class Enrollments"
        unique_together = ("student", "classroom")
        indexes = [
            models.Index(fields=["classroom", "is_active"]),
        ]

    def __str__(self):
        name = self.student.get_full_name() or self.student.username
        return f"{name} in {self.classroom.name} (Roll: {self.roll_number or 'N/A'})"


class TeacherAssignment(models.Model):
    """
    Authorizes a specific faculty member to teach a designated subject in a classroom.
    Strictly enforced: Subject teachers can only mark attendance for authorized assignments.
    """

    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
        limit_choices_to={"role": "teacher"},
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    subject_name = models.CharField(max_length=120)  # e.g., "Advanced Mathematics"
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Teacher Assignment"
        verbose_name_plural = "Teacher Assignments"
        unique_together = ("teacher", "classroom", "subject_name")

    def __str__(self):
        teacher_name = self.teacher.get_full_name() or self.teacher.username
        return f"{teacher_name} -> {self.subject_name} ({self.classroom.name})"


class AttendancePolicy(models.Model):
    """
    Institutional attendance calculation rules and minimum required attendance thresholds.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="attendance_policies",
        null=True,
        blank=True,
        help_text="Institution owning this attendance policy.",
    )
    name = models.CharField(max_length=120, default="Standard Institution Attendance Policy")
    minimum_required_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("75.00"),
        help_text="Threshold below which a student is flagged for low attendance warning.",
    )
    present_weight = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("1.00"))
    late_weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("0.50"),
        help_text="Weight credited for late attendance (e.g. 0.5 for half credit).",
    )
    excused_weight = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Weight credited for authorized medical/institutional excused absence.",
    )
    absent_weight = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Attendance Policy"
        verbose_name_plural = "Attendance Policies"

    def __str__(self):
        return f"{self.name} (Min: {self.minimum_required_percentage}%)"


class AttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LATE = "late", "Late"
    EXCUSED = "excused", "Excused Absence"


class AttendanceSession(models.Model):
    """
    A specific lecture, seminar, or class meeting session where attendance is recorded.
    Guaranteed unique per classroom, subject, date, and period to prevent duplicate sessions.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
        null=True,
        blank=True,
        help_text="Institution context for this lecture/period meeting.",
    )
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.CASCADE,
        related_name="attendance_sessions",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conducted_attendance_sessions",
    )
    subject_name = models.CharField(max_length=120)
    session_date = models.DateField(default=timezone.now)
    session_period = models.CharField(max_length=50, default="Period 1")  # e.g. "Period 1", "Morning"
    topic = models.CharField(max_length=255, blank=True, help_text="Lecture topic or lesson objective.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_attendance_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Attendance Session"
        verbose_name_plural = "Attendance Sessions"
        ordering = ["-session_date", "session_period"]
        unique_together = ("classroom", "subject_name", "session_date", "session_period")
        indexes = [
            models.Index(fields=["classroom", "session_date"]),
            models.Index(fields=["subject_name", "session_date"]),
        ]

    def __str__(self):
        return f"{self.subject_name} ({self.classroom.code}) - {self.session_date} [{self.session_period}]"


class AttendanceRecord(models.Model):
    """
    Individual attendance status for a student in an AttendanceSession.
    Guaranteed strictly unique per session and student to prevent duplicate entries.
    """

    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name="records",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.PRESENT,
    )
    remarks = models.CharField(max_length=255, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_attendance_records",
    )
    modified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="modified_attendance_records",
    )
    modified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Attendance Record"
        verbose_name_plural = "Attendance Records"
        unique_together = ("session", "student")
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["session", "status"]),
        ]

    def __str__(self):
        name = self.student.get_full_name() or self.student.username
        return f"{name} - {self.get_status_display()} on {self.session.session_date}"


class CorrectionStatus(models.TextChoices):
    PENDING = "pending", "Pending Review"
    APPROVED = "approved", "Approved & Applied"
    REJECTED = "rejected", "Rejected"


class AttendanceCorrectionRequest(models.Model):
    """
    Formal request submitted by student or parent to contest or correct an attendance record
    (e.g., medical leave, official school representation, or clerical error).
    """

    record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.CASCADE,
        related_name="correction_requests",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="my_attendance_corrections",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_attendance_corrections",
    )
    requested_status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.EXCUSED,
    )
    reason = models.TextField(help_text="Detailed justification or explanation for the correction.")
    supporting_document = models.FileField(
        upload_to="attendance_excuses/",
        blank=True,
        null=True,
        help_text="Doctor note, sanction letter, or supporting document.",
    )
    status = models.CharField(
        max_length=20,
        choices=CorrectionStatus.choices,
        default=CorrectionStatus.PENDING,
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_attendance_corrections",
    )
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Attendance Correction Request"
        verbose_name_plural = "Attendance Correction Requests"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Correction for {self.student.username} ({self.record.session.session_date}) - {self.get_status_display()}"


class AttendanceAuditLog(models.Model):
    """
    Immutable audit log recording attendance markings, changes, corrections, and approvals.
    """

    session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    record = models.ForeignKey(
        AttendanceRecord,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=60)  # e.g., "MARKED", "CORRECTED", "CORRECTION_APPROVED"
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20, blank=True)
    reason = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Attendance Audit Log"
        verbose_name_plural = "Attendance Audit Logs"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {self.action} by {self.actor}"

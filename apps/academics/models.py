"""
EduConnect Academics & Subject Teacher Models.
Supports study material uploads, assignment creation & submissions,
confidential until published assessments & scores, and real student doubt clearing Q&A.
"""

from decimal import Decimal
import os
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def validate_academic_file(file):
    """
    Validates uploaded notes, submissions, and materials:
    - Allowed extensions: pdf, doc, docx, ppt, pptx, zip, jpg, png, txt
    - Max size: 10 MB
    """
    max_size = 10 * 1024 * 1024  # 10 MB
    if file.size > max_size:
        raise ValidationError("File size exceeds 10 MB. Please upload a smaller file.")

    ext = os.path.splitext(file.name)[1].lower()
    allowed = [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".zip", ".jpg", ".jpeg", ".png", ".txt"]
    if ext not in allowed:
        raise ValidationError(f"File type '{ext}' is not supported. Allowed formats: PDF, DOC, PPT, ZIP, Images.")


class StudyMaterial(models.Model):
    """
    Lecture notes, reference PDFs, and reading materials uploaded by subject faculty.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="study_materials",
        null=True,
        blank=True,
        help_text="Institution repository owning this study material.",
    )
    classroom = models.ForeignKey(
        "attendance.ClassRoom",
        on_delete=models.CASCADE,
        related_name="study_materials",
    )
    subject_name = models.CharField(max_length=120)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="uploaded_study_materials",
        limit_choices_to={"role": "teacher"},
    )
    title = models.CharField(max_length=220)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="study_materials/", validators=[validate_academic_file])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Study Material"
        verbose_name_plural = "Study Materials"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.subject_name} - {self.classroom.name})"


class Assignment(models.Model):
    """
    Academic coursework assignment with deadline and attachment support.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="academic_assignments",
        null=True,
        blank=True,
        help_text="Institution context for this coursework assignment.",
    )
    classroom = models.ForeignKey(
        "attendance.ClassRoom",
        on_delete=models.CASCADE,
        related_name="academic_assignments",
    )
    subject_name = models.CharField(max_length=120)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="created_assignments",
        limit_choices_to={"role": "teacher"},
    )
    title = models.CharField(max_length=220)
    description = models.TextField()
    attachment = models.FileField(
        upload_to="assignment_briefs/",
        blank=True,
        null=True,
        validators=[validate_academic_file],
    )
    max_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100.00"))
    due_datetime = models.DateTimeField()
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"
        ordering = ["-due_datetime"]

    def __str__(self):
        return f"{self.title} - {self.subject_name} ({self.classroom.code})"

    @property
    def is_past_due(self):
        return timezone.now() > self.due_datetime


class AssignmentSubmission(models.Model):
    """
    Student coursework submission with timestamp, late tracking, and faculty grading.
    """

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assignment_submissions",
        limit_choices_to={"role": "student"},
    )
    submission_file = models.FileField(upload_to="student_submissions/", validators=[validate_academic_file])
    notes = models.TextField(blank=True, help_text="Student comments or submission summary.")
    submitted_at = models.DateTimeField(auto_now_add=True)
    is_late = models.BooleanField(default=False)

    # Grading & Feedback
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graded_assignment_submissions",
    )
    graded_at = models.DateTimeField(null=True, blank=True)
    feedback = models.TextField(blank=True)

    class Meta:
        verbose_name = "Assignment Submission"
        verbose_name_plural = "Assignment Submissions"
        unique_together = ("assignment", "student")
        ordering = ["-submitted_at"]

    def __str__(self):
        name = self.student.get_full_name() or self.student.username
        return f"{name} -> {self.assignment.title}"

    def clean(self):
        if self.score is not None:
            if self.score < Decimal("0.00"):
                raise ValidationError({"score": "Score cannot be negative."})
            if self.score > self.assignment.max_score:
                raise ValidationError({"score": f"Score cannot exceed max score ({self.assignment.max_score})."})


class AssessmentType(models.TextChoices):
    MIDTERM = "midterm", "Midterm Examination"
    FINAL = "final", "Final Term Examination"
    QUIZ = "quiz", "Quiz / Class Test"
    PRACTICAL = "practical", "Lab / Practical Assessment"
    ASSIGNMENT_AGGREGATE = "assignment_agg", "Assignment Portfolio"


class Assessment(models.Model):
    """
    Graded academic examination or test.
    Unpublished marks are kept strictly confidential from students and parents.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="academic_assessments",
        null=True,
        blank=True,
        help_text="Institution context for this examination/quiz.",
    )
    classroom = models.ForeignKey(
        "attendance.ClassRoom",
        on_delete=models.CASCADE,
        related_name="assessments",
    )
    subject_name = models.CharField(max_length=120)
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="managed_assessments",
        limit_choices_to={"role": "teacher"},
    )
    title = models.CharField(max_length=220)
    assessment_type = models.CharField(max_length=30, choices=AssessmentType.choices, default=AssessmentType.QUIZ)
    max_marks = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100.00"))
    weightage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        help_text="Weight percentage towards final term grade.",
    )
    date_conducted = models.DateField(default=timezone.now)

    # Publication Control
    is_published = models.BooleanField(
        default=False,
        help_text="When False, entered marks are confidential and invisible to students/parents.",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_assessments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Assessment"
        verbose_name_plural = "Assessments"
        ordering = ["-date_conducted", "-created_at"]

    def __str__(self):
        pub = " (Published)" if self.is_published else " (Draft / Unpublished)"
        return f"{self.title} - {self.subject_name} ({self.classroom.code}){pub}"


class StudentAssessmentScore(models.Model):
    """
    Marks obtained by an enrolled student in an Assessment.
    """

    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="scores",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assessment_scores",
        limit_choices_to={"role": "student"},
    )
    marks_obtained = models.DecimalField(max_digits=5, decimal_places=2)
    grade = models.CharField(max_length=10, blank=True)  # e.g. "A+", "A", "B", "C", "F"
    teacher_remarks = models.CharField(max_length=255, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Student Assessment Score"
        verbose_name_plural = "Student Assessment Scores"
        unique_together = ("assessment", "student")

    def __str__(self):
        name = self.student.get_full_name() or self.student.username
        return f"{name}: {self.marks_obtained}/{self.assessment.max_marks} ({self.assessment.title})"

    def clean(self):
        if self.marks_obtained < Decimal("0.00"):
            raise ValidationError({"marks_obtained": "Marks cannot be negative."})
        if self.marks_obtained > self.assessment.max_marks:
            raise ValidationError({"marks_obtained": f"Marks cannot exceed maximum marks ({self.assessment.max_marks})."})


class StudentDoubt(models.Model):
    """
    Direct Q&A thread between an enrolled student and their subject faculty.
    Real questions answered by real assigned teachers.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="student_doubts",
        null=True,
        blank=True,
        help_text="Institution context for this student doubt thread.",
    )
    classroom = models.ForeignKey(
        "attendance.ClassRoom",
        on_delete=models.CASCADE,
        related_name="student_doubts",
    )
    subject_name = models.CharField(max_length=120)
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submitted_doubts",
    )
    assigned_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assigned_doubts",
    )
    question_title = models.CharField(max_length=220)
    question_text = models.TextField()
    answer_text = models.TextField(blank=True)
    answered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="answered_doubts",
    )
    answered_at = models.DateTimeField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Student Doubt / Q&A"
        verbose_name_plural = "Student Doubts / Q&A"
        ordering = ["-created_at"]

    def __str__(self):
        status = " (Resolved)" if self.is_resolved else " (Pending Answer)"
        return f"Q: {self.question_title} - {self.subject_name}{status}"


class Subject(models.Model):
    """
    Configurable academic subject/discipline per coaching institute.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="academic_subjects",
        null=True,
        blank=True,
        help_text="Institution offering this subject.",
    )
    name = models.CharField(max_length=120)  # e.g. "Physics", "Mathematics", "Accountancy"
    code = models.CharField(max_length=50)   # e.g. "PHY", "MATH", "ACC"
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        ordering = ["name"]
        unique_together = ("institution", "code")
        indexes = [
            models.Index(fields=["institution", "is_active"]),
            models.Index(fields=["code"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Batch(models.Model):
    """
    Academic coaching batch for a course, session, and campus branch.
    Enforces capacity limits, optional waitlisting, and time schedules.
    """

    class Status(models.TextChoices):
        UPCOMING = "upcoming", "Upcoming"
        ONGOING = "ongoing", "Ongoing / Active"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="coaching_batches",
        help_text="Institution hosting this batch.",
    )
    branch = models.ForeignKey(
        "institutions.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coaching_batches",
        help_text="Branch/Campus location for this batch.",
    )
    course = models.ForeignKey(
        "core.Course",
        on_delete=models.CASCADE,
        related_name="coaching_batches",
        help_text="Target course curriculum.",
    )
    academic_session = models.ForeignKey(
        "attendance.AcademicSession",
        on_delete=models.CASCADE,
        related_name="coaching_batches",
        help_text="Academic term/year.",
    )
    classroom = models.ForeignKey(
        "attendance.ClassRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coaching_batches",
        help_text="Physical classroom or room assignment.",
    )
    name = models.CharField(max_length=150)  # e.g. "Class 10 CBSE Math & Science - Evening Batch A"
    code = models.CharField(max_length=60)   # e.g. "BAT-C10-01"
    target_class = models.CharField(max_length=60, blank=True, default="", help_text="e.g. Class 10, Class 11, Class 12")
    stream = models.CharField(max_length=60, blank=True, default="", help_text="e.g. Science, Commerce, Arts, General")
    board = models.CharField(max_length=120, blank=True, default="", help_text="e.g. CBSE, ICSE, State Board, etc.")
    start_date = models.DateField()
    end_date = models.DateField()
    capacity = models.PositiveIntegerField(default=30)
    enable_waitlist = models.BooleanField(default=True)
    max_waitlist_capacity = models.PositiveIntegerField(default=10)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ONGOING)
    fee_override = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Optional fee override if different from Course fee.")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Coaching Batch"
        verbose_name_plural = "Coaching Batches"
        ordering = ["-start_date", "name"]
        unique_together = ("institution", "code")
        indexes = [
            models.Index(fields=["institution", "status"]),
            models.Index(fields=["course", "status"]),
            models.Index(fields=["branch", "status"]),
        ]

    def clean(self):
        super().clean()
        if self.branch and self.institution and self.branch.institution_id != self.institution_id:
            raise ValidationError({"branch": "Assigned branch must belong to the selected institution."})
        if self.course and self.course.institution_id and self.institution and self.course.institution_id != self.institution_id:
            raise ValidationError({"course": "Assigned course curriculum must belong to the selected institution."})
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "Batch end date cannot be earlier than start date."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def active_enrollments_count(self):
        return self.batch_enrollments.filter(status=BatchEnrollment.Status.ACTIVE).count()

    @property
    def waitlisted_enrollments_count(self):
        return self.batch_enrollments.filter(status=BatchEnrollment.Status.WAITLISTED).count()

    @property
    def is_full(self):
        return self.active_enrollments_count >= self.capacity

    @property
    def available_seats(self):
        return max(0, self.capacity - self.active_enrollments_count)

    @property
    def can_waitlist(self):
        return self.enable_waitlist and self.waitlisted_enrollments_count < self.max_waitlist_capacity


class BatchSchedule(models.Model):
    """
    Weekly timetable slot for a coaching batch.
    """

    DAYS_OF_WEEK = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name="schedules",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batch_schedules",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="batch_schedules",
        limit_choices_to={"role": "teacher"},
    )
    day_of_week = models.PositiveSmallIntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    room_number = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Batch Schedule"
        verbose_name_plural = "Batch Schedules"
        ordering = ["day_of_week", "start_time"]
        indexes = [
            models.Index(fields=["batch", "day_of_week"]),
        ]

    def __str__(self):
        subj = f" - {self.subject.name}" if self.subject else ""
        return f"{self.batch.name}: {self.get_day_of_week_display()} {self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')}{subj}"

    def conflicts_with(self, other):
        if self.day_of_week != other.day_of_week:
            return False
        return self.start_time < other.end_time and self.end_time > other.start_time


    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({"end_time": "Schedule slot end time must be later than start time."})
        if self.teacher and self.batch:
            teacher_inst_match = (
                (getattr(self.teacher, "institution_id", None) and self.teacher.institution_id == self.batch.institution_id) or
                (hasattr(self.teacher, "memberships") and self.teacher.memberships.filter(institution_id=self.batch.institution_id, is_active=True).exists()) or
                (hasattr(self.teacher, "institution_memberships") and self.teacher.institution_memberships.filter(institution_id=self.batch.institution_id, is_active=True).exists())
            )
            if not teacher_inst_match:
                raise ValidationError({"teacher": "Teacher does not belong to the batch's institution."})
        if self.subject and self.batch and self.subject.institution_id and self.subject.institution_id != self.batch.institution_id:
            raise ValidationError({"subject": "Subject does not belong to the batch's institution."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class BatchTeacherAssignment(models.Model):
    """
    Assigns and authorizes a Subject Teacher for a specific Batch and Subject.
    """

    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name="teacher_assignments",
    )
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="batch_teacher_assignments",
        limit_choices_to={"role": "teacher"},
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="batch_teacher_assignments",
    )
    is_primary = models.BooleanField(default=True, help_text="Lead faculty for this subject in the batch.")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Batch Teacher Assignment"
        verbose_name_plural = "Batch Teacher Assignments"
        unique_together = ("batch", "teacher", "subject")

    def __str__(self):
        teacher_name = self.teacher.get_full_name() or self.teacher.username
        return f"{teacher_name} -> {self.subject.name} in {self.batch.name}"

    def clean(self):
        super().clean()
        if self.teacher and self.batch:
            teacher_inst_match = (
                (getattr(self.teacher, "institution_id", None) and self.teacher.institution_id == self.batch.institution_id) or
                (hasattr(self.teacher, "memberships") and self.teacher.memberships.filter(institution_id=self.batch.institution_id, is_active=True).exists()) or
                (hasattr(self.teacher, "institution_memberships") and self.teacher.institution_memberships.filter(institution_id=self.batch.institution_id, is_active=True).exists())
            )
            if not teacher_inst_match:
                raise ValidationError({"teacher": "Teacher does not belong to the batch's institution."})
        if self.subject and self.batch and self.subject.institution_id and self.subject.institution_id != self.batch.institution_id:
            raise ValidationError({"subject": "Subject does not belong to the batch's institution."})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class BatchEnrollment(models.Model):
    """
    Enrolls a student in a coaching batch.
    Supports:
    - Multiple active enrollments for one student
    - Preventing duplicate active enrollments in the same batch
    - Enforcing institution boundary
    - Enforcing capacity and waitlisting
    - Schedule conflict checking
    - Student transfer between batches
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WAITLISTED = "waitlisted", "Waitlisted"
        TRANSFERRED = "transferred", "Transferred"
        COMPLETED = "completed", "Completed"
        DROPPED = "dropped", "Dropped / Withdrawn"
        SUSPENDED = "suspended", "Suspended"

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="student_batch_enrollments",
        help_text="Tenant institution context.",
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coaching_batch_enrollments",
        limit_choices_to={"role": "student"},
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name="batch_enrollments",
    )
    enrollment_number = models.CharField(max_length=60, unique=True, editable=False)
    roll_number = models.CharField(max_length=30, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    waitlist_position = models.PositiveIntegerField(null=True, blank=True)
    transferred_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transferred_from_enrollment",
    )
    transfer_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_enrollments",
    )
    enrolled_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Batch Enrollment"
        verbose_name_plural = "Batch Enrollments"
        ordering = ["-enrolled_at"]
        indexes = [
            models.Index(fields=["institution", "status"]),
            models.Index(fields=["student", "status"]),
            models.Index(fields=["batch", "status"]),
        ]

    def __str__(self):
        student_name = self.student.get_full_name() or self.student.username
        return f"{student_name} -> {self.batch.name} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.batch and self.institution and self.batch.institution_id != self.institution_id:
            raise ValidationError({"batch": "Batch does not belong to the enrolled institution."})

        if self.student and self.batch:
            # Check student belongs to the batch's institution
            student_inst_match = (
                (getattr(self.student, "institution_id", None) and self.student.institution_id == self.batch.institution_id) or
                (hasattr(self.student, "memberships") and self.student.memberships.filter(institution_id=self.batch.institution_id, is_active=True).exists()) or
                (hasattr(self.student, "institution_memberships") and self.student.institution_memberships.filter(institution_id=self.batch.institution_id, is_active=True).exists())
            )
            if not student_inst_match:
                raise ValidationError({"student": "Student does not belong to the batch's institution. Cross-institute enrolment is prohibited."})

        if self.status == BatchEnrollment.Status.ACTIVE and self.student and self.batch:
            existing_active = BatchEnrollment.objects.filter(
                student=self.student,
                batch=self.batch,
                status=BatchEnrollment.Status.ACTIVE,
            )
            if self.pk:
                existing_active = existing_active.exclude(pk=self.pk)
            if existing_active.exists():
                raise ValidationError({"batch": f"Duplicate active enrolment: Student is already actively enrolled in '{self.batch.name}'."})

    def save(self, *args, **kwargs):
        if not self.enrollment_number:
            import secrets
            code = self.batch.code if self.batch else "BATCH"
            self.enrollment_number = f"ENR-{code}-{secrets.token_hex(3).upper()}"
        if not self.institution_id and self.batch:
            self.institution = self.batch.institution
        self.clean()
        super().save(*args, **kwargs)


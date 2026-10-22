"""
Academic Services & Business Logic for EduConnect.
Provides grade computation, teacher authorization verification,
assignment submission & grading workflows, assessment score processing,
and confidential marks publication safeguards.
"""

from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import Role
from apps.attendance.models import ClassEnrollment, TeacherAssignment
from apps.academics.models import (
    Assessment,
    Assignment,
    AssignmentSubmission,
    Batch,
    BatchEnrollment,
    BatchSchedule,
    BatchTeacherAssignment,
    StudentAssessmentScore,
    StudentDoubt,
    Subject,
)


def calculate_letter_grade(marks_obtained: Decimal, max_marks: Decimal) -> str:
    """
    Computes a standard institutional letter grade from score percentage.
    """
    if max_marks <= Decimal("0.00"):
        return "N/A"

    percentage = (Decimal(str(marks_obtained)) / Decimal(str(max_marks))) * Decimal("100.00")

    if percentage >= Decimal("90.00"):
        return "A+"
    elif percentage >= Decimal("80.00"):
        return "A"
    elif percentage >= Decimal("70.00"):
        return "B"
    elif percentage >= Decimal("60.00"):
        return "C"
    elif percentage >= Decimal("50.00"):
        return "D"
    else:
        return "F"


def is_teacher_authorized_for_subject(teacher, classroom, subject_name: str) -> bool:
    """
    Checks if a teacher is actively assigned to teach a subject in the given classroom.
    Admin users bypass subject assignment restrictions.
    """
    if getattr(teacher, "role", None) == Role.ADMIN or teacher.is_superuser:
        return True

    return TeacherAssignment.objects.filter(
        teacher=teacher,
        classroom=classroom,
        subject_name=subject_name,
        is_active=True,
    ).exists()


def is_student_enrolled_in_classroom(student, classroom) -> bool:
    """
    Checks if a student is actively enrolled in the specified classroom.
    """
    return ClassEnrollment.objects.filter(
        student=student,
        classroom=classroom,
        is_active=True,
    ).exists()


def submit_student_assignment(
    assignment: Assignment,
    student,
    submission_file,
    notes: str = "",
) -> AssignmentSubmission:
    """
    Submits coursework for an assignment:
    - Enforces student role and classroom enrollment
    - Automatically detects if the submission is late
    - Replaces prior submission if resubmitted before grading
    """
    if getattr(student, "role", None) != Role.STUDENT:
        raise PermissionDenied("Only registered students can submit coursework.")

    if not is_student_enrolled_in_classroom(student, assignment.classroom):
        raise PermissionDenied(
            f"Student {student.get_full_name()} is not enrolled in classroom '{assignment.classroom.name}'."
        )

    now = timezone.now()
    is_late = now > assignment.due_datetime

    submission, created = AssignmentSubmission.objects.get_or_create(
        assignment=assignment,
        student=student,
        defaults={
            "submission_file": submission_file,
            "notes": notes,
            "is_late": is_late,
        },
    )

    if not created:
        if submission.score is not None:
            raise ValidationError("This assignment submission has already been graded and cannot be modified.")
        submission.submission_file = submission_file
        submission.notes = notes
        submission.is_late = is_late
        submission.submitted_at = now
        submission.save()

    return submission


def grade_assignment_submission(
    submission: AssignmentSubmission,
    grader,
    score: Decimal,
    feedback: str = "",
) -> AssignmentSubmission:
    """
    Grades a student coursework submission:
    - Validates grader authority (assigned faculty or admin)
    - Validates 0 <= score <= assignment.max_score
    - Stamps grader and grading timestamp
    """
    assignment = submission.assignment
    if not is_teacher_authorized_for_subject(grader, assignment.classroom, assignment.subject_name):
        raise PermissionDenied("You are not authorized to grade assignments for this classroom and subject.")

    score_dec = Decimal(str(score))
    if score_dec < Decimal("0.00"):
        raise ValidationError("Grading score cannot be negative.")
    if score_dec > assignment.max_score:
        raise ValidationError(f"Score cannot exceed maximum possible assignment score of {assignment.max_score}.")

    submission.score = score_dec
    submission.feedback = feedback
    submission.graded_by = grader
    submission.graded_at = timezone.now()
    submission.save()
    return submission


def enter_student_assessment_score(
    assessment: Assessment,
    student,
    marks_obtained: Decimal,
    entered_by,
    teacher_remarks: str = "",
) -> StudentAssessmentScore:
    """
    Records or updates an assessment score for an enrolled student:
    - Validates user authority (assigned faculty or admin)
    - Enforces student enrollment in the classroom
    - Computes letter grade automatically
    """
    if not is_teacher_authorized_for_subject(entered_by, assessment.classroom, assessment.subject_name):
        raise PermissionDenied("You are not authorized to enter assessment scores for this classroom and subject.")

    if not is_student_enrolled_in_classroom(student, assessment.classroom):
        raise ValidationError(f"Student {student.get_full_name()} is not enrolled in {assessment.classroom.name}.")

    marks_dec = Decimal(str(marks_obtained))
    if marks_dec < Decimal("0.00"):
        raise ValidationError("Marks obtained cannot be negative.")
    if marks_dec > assessment.max_marks:
        raise ValidationError(f"Marks obtained ({marks_dec}) cannot exceed maximum marks ({assessment.max_marks}).")

    grade = calculate_letter_grade(marks_dec, assessment.max_marks)

    score_obj, created = StudentAssessmentScore.objects.update_or_create(
        assessment=assessment,
        student=student,
        defaults={
            "marks_obtained": marks_dec,
            "grade": grade,
            "teacher_remarks": teacher_remarks,
            "entered_by": entered_by,
        },
    )
    return score_obj


def publish_assessment_results(assessment: Assessment, publisher) -> Assessment:
    """
    Publishes assessment marks to students and parents:
    - Verifies publisher is the assigned teacher or an admin
    - Flags is_published=True and records publication metadata
    """
    if not is_teacher_authorized_for_subject(publisher, assessment.classroom, assessment.subject_name):
        raise PermissionDenied("You do not have permission to publish results for this assessment.")

    assessment.is_published = True
    assessment.published_at = timezone.now()
    assessment.published_by = publisher
    assessment.save()
    return assessment


def answer_student_doubt(doubt: StudentDoubt, answer_text: str, teacher) -> StudentDoubt:
    """
    Records a real faculty answer to a student doubt:
    - Verifies teacher authority (assigned teacher or admin)
    - Updates doubt to resolved state
    """
    if not is_teacher_authorized_for_subject(teacher, doubt.classroom, doubt.subject_name):
        raise PermissionDenied("You are not authorized to answer doubts for this subject/classroom.")

    if not answer_text.strip():
        raise ValidationError("Answer text cannot be blank.")

    doubt.answer_text = answer_text.strip()
    doubt.answered_by = teacher
    doubt.answered_at = timezone.now()
    doubt.is_resolved = True
    doubt.save()
    return doubt


# ============================================================================
# COACHING BATCHES, SCHEDULES, & ENROLMENTS SERVICES (TASK 2)
# ============================================================================


def is_teacher_authorized_for_batch_subject(teacher, batch: Batch, subject: Subject) -> bool:
    """
    Checks if a teacher is actively assigned to teach a subject in the given batch.
    Admin users and superusers bypass subject assignment restrictions.
    """
    if getattr(teacher, "role", None) == Role.ADMIN or teacher.is_superuser:
        return True

    return BatchTeacherAssignment.objects.filter(
        batch=batch,
        teacher=teacher,
        subject=subject,
    ).exists()


def check_batch_schedule_conflicts(student, batch: Batch, exclude_batch_id=None) -> list[str]:
    """
    Checks if a student has any time conflict between their existing active batches
    and the proposed batch. Returns list of conflict descriptions (empty if none).
    """
    conflicts = []
    student_enrollments = BatchEnrollment.objects.filter(
        student=student,
        status=BatchEnrollment.Status.ACTIVE,
    ).select_related("batch")

    if exclude_batch_id:
        student_enrollments = student_enrollments.exclude(batch_id=exclude_batch_id)

    target_schedules = list(batch.schedules.all())
    if not target_schedules:
        return conflicts

    for enr in student_enrollments:
        enr_schedules = enr.batch.schedules.all()
        for s_active in enr_schedules:
            for s_target in target_schedules:
                if s_active.conflicts_with(s_target):
                    conflicts.append(
                        f"Schedule clash with enrolled batch '{enr.batch.name}' on {s_target.get_day_of_week_display()} "
                        f"({s_target.start_time.strftime('%H:%M')}-{s_target.end_time.strftime('%H:%M')} overlaps with {s_active.start_time.strftime('%H:%M')}-{s_active.end_time.strftime('%H:%M')})"
                    )
    return conflicts


def validate_batch_enrollment(student, batch: Batch, check_conflicts: bool = True, exclude_batch_id=None):
    """
    Validates institutional boundaries, student role, duplicate active enrolments,
    and schedule clashes.
    """
    if getattr(student, "role", None) != Role.STUDENT:
        raise ValidationError(f"User {student.get_full_name() or student.username} is not registered as a student.")

    # Cross-institute validation
    student_inst_match = (
        (getattr(student, "institution_id", None) and student.institution_id == batch.institution_id) or
        (hasattr(student, "memberships") and student.memberships.filter(institution_id=batch.institution_id, is_active=True).exists()) or
        (hasattr(student, "institution_memberships") and student.institution_memberships.filter(institution_id=batch.institution_id, is_active=True).exists())
    )
    if not student_inst_match:
        raise ValidationError(
            f"Unauthorized cross-institute enrolment: Student does not belong to {batch.institution.name}."
        )

    # Duplicate active enrolment prevention
    existing_active = BatchEnrollment.objects.filter(
        student=student,
        batch=batch,
        status=BatchEnrollment.Status.ACTIVE,
    )
    if exclude_batch_id and str(batch.pk) == str(exclude_batch_id):
        existing_active = existing_active.exclude(batch_id=exclude_batch_id)

    if existing_active.exists():
        raise ValidationError(f"Duplicate active enrolment: Student is already actively enrolled in '{batch.name}'.")

    # Schedule conflicts check
    if check_conflicts:
        conflicts = check_batch_schedule_conflicts(student, batch, exclude_batch_id=exclude_batch_id)
        if conflicts:
            raise ValidationError(f"Schedule conflict detected: {'; '.join(conflicts)}")


def enroll_student_in_batch(
    student,
    batch: Batch,
    created_by=None,
    roll_number: str = "",
    start_date=None,
    notes: str = "",
    force_waitlist: bool = False,
    check_conflicts: bool = True,
) -> BatchEnrollment:
    """
    Enrolls a student in a coaching batch with capacity & waitlist management:
    - If capacity is available: enrolled as ACTIVE.
    - If capacity reached:
        - If waitlist enabled: enrolled as WAITLISTED with incremented position.
        - If waitlist disabled or full: raises ValidationError.
    - Multiple active enrolments in different batches for the same student are supported!
    """
    validate_batch_enrollment(student, batch, check_conflicts=check_conflicts)

    now_date = start_date or timezone.now().date()

    # Determine status & waitlist position
    if not force_waitlist and not batch.is_full:
        status = BatchEnrollment.Status.ACTIVE
        waitlist_pos = None
    else:
        # Batch is full or force waitlist requested
        if not batch.enable_waitlist:
            raise ValidationError(
                f"Batch '{batch.name}' has reached its maximum capacity of {batch.capacity} seats and waitlisting is disabled."
            )
        waitlisted_count = batch.waitlisted_enrollments_count
        if waitlisted_count >= batch.max_waitlist_capacity:
            raise ValidationError(
                f"Batch '{batch.name}' waitlist is full ({waitlisted_count}/{batch.max_waitlist_capacity} waitlisted)."
            )
        status = BatchEnrollment.Status.WAITLISTED
        waitlist_pos = waitlisted_count + 1

    enrollment = BatchEnrollment.objects.create(
        institution=batch.institution,
        student=student,
        batch=batch,
        roll_number=roll_number,
        status=status,
        start_date=now_date,
        waitlist_position=waitlist_pos,
        notes=notes,
        created_by=created_by,
    )
    return enrollment


def promote_waitlisted_student_for_batch(batch: Batch) -> BatchEnrollment | None:
    """
    When a seat opens in a batch (due to transfer, drop, completion, or capacity increase),
    automatically promotes the next student in line from WAITLISTED to ACTIVE.
    """
    if batch.available_seats <= 0:
        return None

    first_waitlisted = (
        batch.batch_enrollments.filter(status=BatchEnrollment.Status.WAITLISTED)
        .order_by("waitlist_position", "enrolled_at")
        .first()
    )
    if not first_waitlisted:
        return None

    first_waitlisted.status = BatchEnrollment.Status.ACTIVE
    first_waitlisted.waitlist_position = None
    first_waitlisted.save()

    # Re-order remaining waitlist
    remaining = batch.batch_enrollments.filter(
        status=BatchEnrollment.Status.WAITLISTED
    ).order_by("waitlist_position", "enrolled_at")
    for idx, enr in enumerate(remaining, start=1):
        if enr.waitlist_position != idx:
            enr.waitlist_position = idx
            enr.save(update_fields=["waitlist_position"])

    return first_waitlisted


def transfer_student_batch(
    enrollment: BatchEnrollment,
    target_batch: Batch,
    reason: str = "",
    transferred_by=None,
    check_conflicts: bool = True,
) -> tuple[BatchEnrollment, BatchEnrollment]:
    """
    Transfers a student from their current batch to a target batch:
    - Verifies both batches belong to the same institution.
    - Validates target batch compatibility (capacity/waitlist, schedule conflicts).
    - Updates source enrolment to TRANSFERRED with end_date, reason, and target link.
    - Automatically creates target enrolment.
    - Triggers waitlist promotion in the source batch to fill the freed seat.
    """
    source_batch = enrollment.batch
    if source_batch.institution_id != target_batch.institution_id:
        raise ValidationError("Cannot transfer student to a batch belonging to another institution.")

    if source_batch.pk == target_batch.pk:
        raise ValidationError("Target batch cannot be the same as the current batch.")

    if enrollment.status not in [BatchEnrollment.Status.ACTIVE, BatchEnrollment.Status.WAITLISTED]:
        raise ValidationError(
            f"Only active or waitlisted enrolments can be transferred. Current status: {enrollment.get_status_display()}."
        )

    # Validate target batch enrolment (excluding current batch from conflict detection)
    validate_batch_enrollment(
        enrollment.student,
        target_batch,
        check_conflicts=check_conflicts,
        exclude_batch_id=source_batch.pk,
    )

    # Enroll in target batch
    new_enrollment = enroll_student_in_batch(
        student=enrollment.student,
        batch=target_batch,
        created_by=transferred_by,
        roll_number=enrollment.roll_number,
        notes=f"Transferred from batch '{source_batch.name}'. Reason: {reason}",
        check_conflicts=check_conflicts,
    )

    # Mark source enrollment as transferred
    enrollment.status = BatchEnrollment.Status.TRANSFERRED
    enrollment.end_date = timezone.now().date()
    enrollment.transferred_to = new_enrollment
    enrollment.transfer_reason = reason
    enrollment.save()

    # If source batch was active, a seat opened! Promote waitlist
    promote_waitlisted_student_for_batch(source_batch)

    return enrollment, new_enrollment


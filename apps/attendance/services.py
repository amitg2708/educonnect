"""
EduConnect Attendance Domain Services.
Provides:
- Policy-driven attendance calculations & percentages
- Teacher assignment authorization validation
- Duplicate prevention (session & student records)
- Date boundary validation against academic sessions
- Attendance correction workflows with audit trails
"""

from decimal import Decimal
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import models
from django.utils import timezone
from .models import (
    AttendancePolicy,
    AcademicSession,
    ClassRoom,
    ClassEnrollment,
    TeacherAssignment,
    AttendanceSession,
    AttendanceRecord,
    AttendanceStatus,
    AttendanceCorrectionRequest,
    CorrectionStatus,
    AttendanceAuditLog,
)


def get_active_attendance_policy(institution=None) -> AttendancePolicy:
    """
    Returns the active institutional attendance policy, or creates default.
    """
    qs = AttendancePolicy.objects.filter(is_active=True)
    if institution:
        qs = qs.filter(institution=institution)
    policy = qs.first()
    if not policy:
        policy = AttendancePolicy.objects.create(
            institution=institution,
            name="Standard Institution Attendance Policy",
            minimum_required_percentage=Decimal("75.00"),
            present_weight=Decimal("1.00"),
            late_weight=Decimal("0.50"),
            excused_weight=Decimal("1.00"),
            absent_weight=Decimal("0.00"),
            is_active=True,
        )
    return policy


def calculate_student_attendance_summary(
    student,
    classroom: ClassRoom = None,
    subject_name: str = None,
    academic_session: AcademicSession = None,
    policy: AttendancePolicy = None,
):
    """
    Calculates detailed ground-truth attendance metrics for a student.
    Returns:
    - total_sessions
    - present_count
    - absent_count
    - late_count
    - excused_count
    - weighted_presence_units
    - percentage (Decimal)
    - is_below_minimum (bool)
    - absence_records
    """
    if policy is None:
        policy = get_active_attendance_policy()

    records = AttendanceRecord.objects.filter(student=student).select_related("session", "session__classroom")

    if classroom:
        records = records.filter(session__classroom=classroom)
    if subject_name:
        records = records.filter(session__subject_name=subject_name)
    if academic_session:
        records = records.filter(session__classroom__academic_session=academic_session)

    total_sessions = records.count()

    present_count = records.filter(status=AttendanceStatus.PRESENT).count()
    absent_count = records.filter(status=AttendanceStatus.ABSENT).count()
    late_count = records.filter(status=AttendanceStatus.LATE).count()
    excused_count = records.filter(status=AttendanceStatus.EXCUSED).count()

    # Policy weighted units
    weighted_units = (
        (Decimal(present_count) * policy.present_weight)
        + (Decimal(late_count) * policy.late_weight)
        + (Decimal(excused_count) * policy.excused_weight)
        + (Decimal(absent_count) * policy.absent_weight)
    )

    if total_sessions > 0:
        percentage = ((weighted_units / Decimal(total_sessions)) * Decimal("100.00")).quantize(Decimal("0.01"))
    else:
        percentage = Decimal("100.00")

    is_below_minimum = percentage < policy.minimum_required_percentage if total_sessions > 0 else False

    absence_records = list(records.filter(status__in=[AttendanceStatus.ABSENT, AttendanceStatus.LATE]).order_by("-session__session_date"))

    return {
        "total_sessions": total_sessions,
        "present_count": present_count,
        "absent_count": absent_count,
        "late_count": late_count,
        "excused_count": excused_count,
        "weighted_units": weighted_units,
        "percentage": percentage,
        "is_below_minimum": is_below_minimum,
        "policy": policy,
        "absence_records": absence_records,
    }


def mark_session_attendance(
    assignment: TeacherAssignment,
    session_date,
    session_period: str,
    topic: str,
    student_records: dict,  # {student_id_str: {"status": "present", "remarks": "..."}}
    actor,
):
    """
    Marks attendance for an authorized class session.
    Guarantees:
    - Authorization check: Actor must be the assigned teacher or an administrator.
    - Date boundaries check: Session date must fall within the academic session date range.
    - Duplicate prevention: Rejects if session already recorded for this class, subject, date, and period.
    - Class membership validation: Validates each student is an enrolled member of this classroom.
    """
    classroom = assignment.classroom

    # 1. Authorization check
    is_admin = actor.is_superuser or (hasattr(actor, "role") and actor.role == "admin")
    if not is_admin and assignment.teacher != actor:
        raise PermissionDenied("Unauthorized: You are not assigned to mark attendance for this subject/class.")

    # 2. Date boundary check against AcademicSession
    academic_session = classroom.academic_session
    if academic_session:
        if session_date < academic_session.start_date or session_date > academic_session.end_date:
            raise ValidationError(
                f"Session date {session_date} is outside the active term range "
                f"({academic_session.start_date} to {academic_session.end_date})."
            )

    # 3. Duplicate session check
    existing_session = AttendanceSession.objects.filter(
        classroom=classroom,
        subject_name=assignment.subject_name,
        session_date=session_date,
        session_period=session_period,
    ).first()

    if existing_session:
        raise ValidationError(
            f"An attendance session for {assignment.subject_name} ({session_period}) "
            f"on {session_date} has already been recorded."
        )

    # 4. Valid enrolled students in this classroom
    enrolled_students = {
        str(e.student_id): e.student
        for e in ClassEnrollment.objects.filter(classroom=classroom, is_active=True).select_related("student")
    }

    if not enrolled_students:
        raise ValidationError(f"Cannot mark attendance: Classroom '{classroom.name}' has no enrolled students.")

    # 5. Create AttendanceSession
    session = AttendanceSession.objects.create(
        institution=classroom.institution,
        classroom=classroom,
        teacher=assignment.teacher,
        subject_name=assignment.subject_name,
        session_date=session_date,
        session_period=session_period,
        topic=topic.strip() if topic else "",
        created_by=actor,
    )

    # 6. Create Records for all enrolled students
    records_to_create = []
    for student_id_str, student in enrolled_students.items():
        data = student_records.get(student_id_str, {})
        status = data.get("status", AttendanceStatus.PRESENT)
        remarks = data.get("remarks", "").strip()

        # Validate status choice
        if status not in AttendanceStatus.values:
            status = AttendanceStatus.PRESENT

        rec = AttendanceRecord.objects.create(
            session=session,
            student=student,
            status=status,
            remarks=remarks,
            marked_by=actor,
        )
        records_to_create.append(rec)

    # 7. Audit Log
    AttendanceAuditLog.objects.create(
        session=session,
        action="MARKED",
        actor=actor,
        reason=f"Marked attendance for {len(records_to_create)} students in {assignment.subject_name} [{session_period}].",
    )

    return session


def correct_attendance_session(
    session: AttendanceSession,
    updated_records: dict,  # {record_id_str: {"status": "absent", "remarks": "..."}}
    actor,
    reason: str,
):
    """
    Authorizes and applies corrections to an existing attendance session.
    Tracks who modified, when, and stores audit logs.
    """
    if not reason or not reason.strip():
        raise ValidationError("Audit reason is required to correct attendance records.")

    modified_count = 0
    now = timezone.now()

    for record_id_str, data in updated_records.items():
        try:
            record = AttendanceRecord.objects.get(id=record_id_str, session=session)
        except AttendanceRecord.DoesNotExist:
            continue

        new_status = data.get("status")
        new_remarks = data.get("remarks", "")

        if new_status and new_status in AttendanceStatus.values and new_status != record.status:
            old_status = record.status
            record.status = new_status
            if new_remarks:
                record.remarks = new_remarks
            record.modified_by = actor
            record.modified_at = now
            record.save(update_fields=["status", "remarks", "modified_by", "modified_at"])

            AttendanceAuditLog.objects.create(
                session=session,
                record=record,
                action="CORRECTED",
                actor=actor,
                old_status=old_status,
                new_status=new_status,
                reason=reason.strip(),
            )
            modified_count += 1

    return modified_count


def review_correction_request(
    correction: AttendanceCorrectionRequest,
    decision: str,  # "approved" or "rejected"
    reviewer,
    review_notes: str = "",
):
    """
    Applies review decision to student's correction request.
    If approved, mutates AttendanceRecord status with modified_by audit tracking.
    """
    if correction.status != CorrectionStatus.PENDING:
        raise ValidationError(f"This correction request has already been reviewed ({correction.get_status_display()}).")

    correction.status = CorrectionStatus.APPROVED if decision == "approved" else CorrectionStatus.REJECTED
    correction.reviewer = reviewer
    correction.review_notes = review_notes.strip()
    correction.reviewed_at = timezone.now()
    correction.save(update_fields=["status", "reviewer", "review_notes", "reviewed_at"])

    if decision == "approved":
        record = correction.record
        old_status = record.status
        record.status = correction.requested_status
        record.modified_by = reviewer
        record.modified_at = timezone.now()
        record.save(update_fields=["status", "modified_by", "modified_at"])

        AttendanceAuditLog.objects.create(
            session=record.session,
            record=record,
            action="CORRECTION_APPROVED",
            actor=reviewer,
            old_status=old_status,
            new_status=correction.requested_status,
            reason=f"Approved correction request #{correction.id}: {correction.reason}",
        )

    return correction

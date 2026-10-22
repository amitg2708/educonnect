"""
EduConnect Attendance Management Views.
Implements:
- Teacher workspace (assigned classes, marking sessions, session history, record corrections)
- Student workspace (personal attendance, percentage, absence history, correction requests)
- Parent portal (authorized children attendance, absence alerts, percentage)
- Admin control center (academic terms, classrooms, roster enrollment, teacher assignments,
  policy configuration, correction approvals, and institutional reports)
"""

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from apps.accounts.decorators import role_required, admin_required
from apps.accounts.models import Role, ParentStudentLink
from .models import (
    AcademicSession,
    ClassRoom,
    ClassEnrollment,
    TeacherAssignment,
    AttendancePolicy,
    AttendanceSession,
    AttendanceRecord,
    AttendanceStatus,
    AttendanceCorrectionRequest,
    CorrectionStatus,
    AttendanceAuditLog,
)
from .forms import (
    AcademicSessionForm,
    ClassRoomForm,
    ClassEnrollmentForm,
    TeacherAssignmentForm,
    AttendancePolicyForm,
    AttendanceCorrectionForm,
    CorrectionReviewForm,
)
from .services import (
    get_active_attendance_policy,
    calculate_student_attendance_summary,
    mark_session_attendance,
    correct_attendance_session,
    review_correction_request,
)

User = get_user_model()


# ==============================================================================
# SUBJECT TEACHER VIEWS
# ==============================================================================

@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_attendance_home(request):
    """
    Teacher attendance desk: Displays assigned classes and subjects.
    Prevents teachers from marking students outside their authorized assignments.
    """
    inst = getattr(request, "institution", None)
    assignments = (
        TeacherAssignment.objects.filter(teacher=request.user, is_active=True)
        .select_related("classroom", "classroom__academic_session", "classroom__course")
        .order_by("classroom__name", "subject_name")
    )

    # Recent sessions conducted by this teacher
    recent_sessions = (
        AttendanceSession.objects.filter(teacher=request.user)
        .select_related("classroom")
        .order_by("-session_date", "-created_at")
    )

    if inst:
        assignments = assignments.filter(classroom__institution=inst)
        recent_sessions = recent_sessions.filter(institution=inst)

    recent_sessions = recent_sessions[:10]

    context = {
        "assignments": assignments,
        "recent_sessions": recent_sessions,
        "total_assignments": assignments.count(),
    }
    return render(request, "attendance/teacher/assignments.html", context)


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_mark_attendance_view(request, assignment_id):
    """
    Mark student attendance roster for an authorized subject and class.
    Validates:
    - Teacher assignment authorization
    - Academic session date boundaries
    - Class membership validation
    - Duplicate session prevention
    """
    assignment = get_object_or_404(
        TeacherAssignment.objects.select_related("classroom", "classroom__academic_session", "teacher"),
        id=assignment_id,
    )
    inst = getattr(request, "institution", None)
    if inst and assignment.classroom.institution and assignment.classroom.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("You are not authorized to mark attendance for another institution's classroom.")

    # Strict authorization: Teacher must own assignment unless superuser/admin
    is_admin = request.user.is_superuser or request.user.role == Role.ADMIN
    if not is_admin and assignment.teacher != request.user:
        raise PermissionDenied("You are not authorized to mark attendance for this class/subject.")

    classroom = assignment.classroom
    enrollments = (
        ClassEnrollment.objects.filter(classroom=classroom, is_active=True)
        .select_related("student")
        .order_by("roll_number", "student__username")
    )

    if request.method == "POST":
        session_date_str = request.POST.get("session_date")
        session_period = request.POST.get("session_period", "Period 1").strip()
        topic = request.POST.get("topic", "").strip()

        try:
            if not session_date_str:
                raise ValidationError("Session date is required.")
            session_date = timezone.datetime.strptime(session_date_str, "%Y-%m-%d").date()

            # Parse student records from POST
            student_records = {}
            for e in enrollments:
                sid = str(e.student.id)
                status = request.POST.get(f"status_{sid}", AttendanceStatus.PRESENT)
                remarks = request.POST.get(f"remarks_{sid}", "").strip()
                student_records[sid] = {"status": status, "remarks": remarks}

            session = mark_session_attendance(
                assignment=assignment,
                session_date=session_date,
                session_period=session_period,
                topic=topic,
                student_records=student_records,
                actor=request.user,
            )

            messages.success(
                request,
                f"Attendance marked successfully for {len(student_records)} students in "
                f"{assignment.subject_name} ({session.session_period}) on {session.session_date}.",
            )
            return redirect("attendance:teacher_session_history", assignment_id=assignment.id)

        except ValidationError as e:
            messages.error(request, str(e.message if hasattr(e, "message") else e))

    today = timezone.now().date()
    context = {
        "assignment": assignment,
        "classroom": classroom,
        "enrollments": enrollments,
        "today": today,
        "status_choices": AttendanceStatus.choices,
    }
    return render(request, "attendance/teacher/mark_session.html", context)


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_session_history_view(request, assignment_id):
    """
    View previous attendance sessions for an authorized teacher assignment.
    """
    assignment = get_object_or_404(
        TeacherAssignment.objects.select_related("classroom", "teacher"),
        id=assignment_id,
    )

    is_admin = request.user.is_superuser or request.user.role == Role.ADMIN
    if not is_admin and assignment.teacher != request.user:
        raise PermissionDenied("You are not authorized to view attendance history for this assignment.")

    sessions = (
        AttendanceSession.objects.filter(classroom=assignment.classroom, subject_name=assignment.subject_name)
        .prefetch_related("records")
        .order_by("-session_date", "session_period")
    )

    paginator = Paginator(sessions, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "assignment": assignment,
        "page_obj": page_obj,
    }
    return render(request, "attendance/teacher/session_history.html", context)


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_edit_session_view(request, session_id):
    """
    Correct attendance records for an existing session with mandatory audit trail reason.
    """
    session = get_object_or_404(
        AttendanceSession.objects.select_related("classroom", "teacher"),
        id=session_id,
    )

    is_admin = request.user.is_superuser or request.user.role == Role.ADMIN
    if not is_admin and session.teacher != request.user:
        raise PermissionDenied("You are not authorized to modify this session.")

    records = session.records.select_related("student").order_by("student__username")

    if request.method == "POST":
        reason = request.POST.get("audit_reason", "").strip()
        if not reason:
            messages.error(request, "A mandatory audit reason is required to correct attendance records.")
        else:
            updated_data = {}
            for rec in records:
                rid = str(rec.id)
                status = request.POST.get(f"status_{rid}")
                remarks = request.POST.get(f"remarks_{rid}", "").strip()
                if status:
                    updated_data[rid] = {"status": status, "remarks": remarks}

            try:
                count = correct_attendance_session(
                    session=session,
                    updated_records=updated_data,
                    actor=request.user,
                    reason=reason,
                )
                messages.success(request, f"Updated {count} attendance record(s) with logged audit trail.")
                return redirect("attendance:teacher_edit_session", session_id=session.id)
            except ValidationError as e:
                messages.error(request, str(e))

    audit_logs = session.audit_logs.select_related("actor").order_by("-timestamp")[:15]

    context = {
        "session": session,
        "records": records,
        "status_choices": AttendanceStatus.choices,
        "audit_logs": audit_logs,
    }
    return render(request, "attendance/teacher/edit_session.html", context)


# ==============================================================================
# STUDENT VIEWS
# ==============================================================================

@login_required
@role_required(Role.STUDENT, Role.ADMIN)
def student_attendance_view(request):
    """
    Personal student attendance dashboard:
    - Overall attendance percentage (policy-calculated)
    - Per-subject breakdown
    - Absence and late records
    - Submit attendance correction request button
    """
    policy = get_active_attendance_policy()
    overall_summary = calculate_student_attendance_summary(request.user, policy=policy)

    # Per-subject breakdown
    user_records = AttendanceRecord.objects.filter(student=request.user).select_related("session")
    subjects = list(user_records.values_list("session__subject_name", flat=True).distinct())

    subject_breakdowns = []
    for sub in subjects:
        sub_summary = calculate_student_attendance_summary(request.user, subject_name=sub, policy=policy)
        subject_breakdowns.append({
            "subject_name": sub,
            "total": sub_summary["total_sessions"],
            "present": sub_summary["present_count"],
            "absent": sub_summary["absent_count"],
            "late": sub_summary["late_count"],
            "excused": sub_summary["excused_count"],
            "percentage": sub_summary["percentage"],
            "is_below_minimum": sub_summary["is_below_minimum"],
        })

    # Recent absence history
    recent_absences = (
        user_records.filter(status__in=[AttendanceStatus.ABSENT, AttendanceStatus.LATE])
        .select_related("session", "session__classroom")
        .order_by("-session__session_date")[:15]
    )

    # Correction requests submitted by student
    my_corrections = (
        AttendanceCorrectionRequest.objects.filter(student=request.user)
        .select_related("record", "record__session")
        .order_by("-created_at")[:10]
    )

    context = {
        "overall": overall_summary,
        "subject_breakdowns": subject_breakdowns,
        "recent_absences": recent_absences,
        "my_corrections": my_corrections,
        "policy": policy,
    }
    return render(request, "attendance/student/my_attendance.html", context)


@login_required
@role_required(Role.STUDENT, Role.PARENT, Role.ADMIN)
def submit_correction_request_view(request, record_id):
    """
    Submit an attendance correction request (e.g. medical excuse, school duty, clerical error).
    Strictly verifies ownership: Student or authorized parent.
    """
    record = get_object_or_404(AttendanceRecord.objects.select_related("session", "student"), id=record_id)
    student = record.student

    # Verification: Must be the student or their authorized parent
    is_owner = (request.user == student)
    is_authorized_parent = False
    if request.user.role == Role.PARENT:
        is_authorized_parent = ParentStudentLink.objects.filter(
            parent=request.user,
            student=student,
            is_authorized=True,
        ).exists()

    if not (is_owner or is_authorized_parent or request.user.is_superuser or request.user.role == Role.ADMIN):
        raise PermissionDenied("You are not authorized to submit a correction request for this record.")

    if request.method == "POST":
        form = AttendanceCorrectionForm(request.POST, request.FILES)
        if form.is_valid():
            correction = form.save(commit=False)
            correction.record = record
            correction.student = student
            correction.requested_by = request.user
            correction.status = CorrectionStatus.PENDING
            correction.save()
            messages.success(request, "Attendance correction request submitted for administrative review.")
            return redirect("attendance:student_attendance")
    else:
        form = AttendanceCorrectionForm(initial={"requested_status": AttendanceStatus.EXCUSED})

    context = {
        "record": record,
        "form": form,
    }
    return render(request, "attendance/student/correction_request.html", context)


# ==============================================================================
# PARENT VIEWS
# ==============================================================================

@login_required
@role_required(Role.PARENT, Role.ADMIN)
def parent_child_attendance_view(request, student_id):
    """
    Parent attendance portal for an authorized linked child.
    Enforces server-side authorization link.
    Displays:
    - Overall attendance percentage
    - Absence notifications and alerts
    - Subject-by-subject attendance records
    """
    link_filter = {
        "parent": request.user,
        "student_id": student_id,
        "is_authorized": True,
    }
    inst = getattr(request, "institution", None)
    if inst:
        link_filter["institution"] = inst

    if not request.user.is_superuser and request.user.role == Role.PARENT:
        is_linked = ParentStudentLink.objects.filter(**link_filter).exists()
        if not is_linked:
            raise PermissionDenied("You are not authorized to access attendance records for this student.")

    child = get_object_or_404(User, id=student_id, role=Role.STUDENT)
    policy = get_active_attendance_policy(institution=inst)
    overall = calculate_student_attendance_summary(child, policy=policy)

    # Per-subject breakdown
    user_records = AttendanceRecord.objects.filter(student=child).select_related("session")
    if inst:
        user_records = user_records.filter(session__institution=inst)
    subjects = list(user_records.values_list("session__subject_name", flat=True).distinct())

    subject_breakdowns = []
    for sub in subjects:
        sub_summary = calculate_student_attendance_summary(child, subject_name=sub, policy=policy)
        subject_breakdowns.append({
            "subject_name": sub,
            "total": sub_summary["total_sessions"],
            "present": sub_summary["present_count"],
            "absent": sub_summary["absent_count"],
            "late": sub_summary["late_count"],
            "excused": sub_summary["excused_count"],
            "percentage": sub_summary["percentage"],
            "is_below_minimum": sub_summary["is_below_minimum"],
        })

    recent_absences = (
        user_records.filter(status__in=[AttendanceStatus.ABSENT, AttendanceStatus.LATE])
        .select_related("session")
        .order_by("-session__session_date")[:15]
    )

    context = {
        "child": child,
        "overall": overall,
        "subject_breakdowns": subject_breakdowns,
        "recent_absences": recent_absences,
        "policy": policy,
    }
    return render(request, "attendance/parent/child_attendance.html", context)


# ==============================================================================
# ADMIN VIEWS
# ==============================================================================

@login_required
@role_required(Role.ADMIN)
def admin_attendance_dashboard(request):
    """
    Administration control center for institution attendance:
    - Academic terms
    - Classrooms & cohorts
    - Active policies
    - Pending correction review desk
    """
    inst = getattr(request, "institution", None)
    classrooms_qs = ClassRoom.objects.filter(is_active=True)
    sessions_qs = AttendanceSession.objects.all()
    corrections_qs = AttendanceCorrectionRequest.objects.filter(status=CorrectionStatus.PENDING)
    if inst:
        classrooms_qs = classrooms_qs.filter(institution=inst)
        sessions_qs = sessions_qs.filter(institution=inst)
        corrections_qs = corrections_qs.filter(record__session__institution=inst)

    total_classrooms = classrooms_qs.count()
    total_sessions_count = sessions_qs.count()
    pending_corrections_count = corrections_qs.count()
    active_policy = get_active_attendance_policy(institution=inst)

    recent_sessions = sessions_qs.select_related("classroom", "teacher").order_by("-session_date", "-created_at")[:8]
    pending_corrections = corrections_qs.select_related("student", "record", "record__session")[:5]

    context = {
        "total_classrooms": total_classrooms,
        "total_sessions_count": total_sessions_count,
        "pending_corrections_count": pending_corrections_count,
        "active_policy": active_policy,
        "recent_sessions": recent_sessions,
        "pending_corrections": pending_corrections,
    }
    return render(request, "attendance/admin/dashboard.html", context)


@login_required
@role_required(Role.ADMIN)
def admin_sessions_list(request):
    """
    Manage academic terms / sessions.
    """
    inst = getattr(request, "institution", None)
    if request.method == "POST":
        form = AcademicSessionForm(request.POST)
        if form.is_valid():
            session = form.save(commit=False)
            if inst:
                session.institution = inst
            session.save()
            messages.success(request, f"Academic session '{session.name}' created.")
            return redirect("attendance:admin_sessions")
    else:
        form = AcademicSessionForm()

    sessions = AcademicSession.objects.all().order_by("-start_date")
    if inst:
        sessions = sessions.filter(institution=inst)
    return render(request, "attendance/admin/sessions_list.html", {"sessions": sessions, "form": form})


@login_required
@role_required(Role.ADMIN)
def admin_classrooms_list(request):
    """
    Manage classrooms, cohorts, and student capacity.
    """
    inst = getattr(request, "institution", None)
    if request.method == "POST":
        form = ClassRoomForm(request.POST)
        if form.is_valid():
            classroom = form.save(commit=False)
            if inst:
                classroom.institution = inst
            classroom.save()
            messages.success(request, f"Classroom '{classroom.name}' created.")
            return redirect("attendance:admin_classroom_detail", classroom_id=classroom.id)
    else:
        form = ClassRoomForm()

    classrooms = ClassRoom.objects.select_related("academic_session", "course").prefetch_related("enrollments", "teacher_assignments").order_by("name")
    if inst:
        classrooms = classrooms.filter(institution=inst)
    return render(request, "attendance/admin/classrooms_list.html", {"classrooms": classrooms, "form": form})


@login_required
@role_required(Role.ADMIN)
def admin_classroom_detail(request, classroom_id):
    """
    View classroom roster, enroll students, and assign subject faculty.
    """
    classroom = get_object_or_404(ClassRoom.objects.select_related("academic_session", "course"), id=classroom_id)
    inst = getattr(request, "institution", None)
    if inst and classroom.institution and classroom.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to classroom outside your active institution.")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "enroll_student":
            enroll_form = ClassEnrollmentForm(request.POST)
            if enroll_form.is_valid():
                enrollment = enroll_form.save(commit=False)
                enrollment.classroom = classroom
                enrollment.save()
                messages.success(request, f"Enrolled student '{enrollment.student.username}' in {classroom.name}.")
                return redirect("attendance:admin_classroom_detail", classroom_id=classroom.id)
        elif action == "assign_teacher":
            teacher_form = TeacherAssignmentForm(request.POST)
            if teacher_form.is_valid():
                assignment = teacher_form.save(commit=False)
                assignment.classroom = classroom
                assignment.save()
                messages.success(request, f"Assigned teacher '{assignment.teacher.username}' for {assignment.subject_name}.")
                return redirect("attendance:admin_classroom_detail", classroom_id=classroom.id)

    enroll_form = ClassEnrollmentForm(initial={"classroom": classroom})
    teacher_form = TeacherAssignmentForm(initial={"classroom": classroom})

    enrollments = classroom.enrollments.select_related("student").order_by("roll_number", "student__username")
    assignments = classroom.teacher_assignments.select_related("teacher").order_by("subject_name")

    context = {
        "classroom": classroom,
        "enrollments": enrollments,
        "assignments": assignments,
        "enroll_form": enroll_form,
        "teacher_form": teacher_form,
    }
    return render(request, "attendance/admin/classroom_detail.html", context)


@login_required
@role_required(Role.ADMIN)
def admin_corrections_list(request):
    """
    Review student/parent attendance correction requests.
    """
    inst = getattr(request, "institution", None)
    corrections = AttendanceCorrectionRequest.objects.select_related("student", "record", "record__session", "requested_by").order_by("-created_at")
    if inst:
        corrections = corrections.filter(record__session__institution=inst)
    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        corrections = corrections.filter(status=status_filter)

    return render(request, "attendance/admin/corrections_list.html", {"corrections": corrections, "status_filter": status_filter})


@login_required
@role_required(Role.ADMIN)
def admin_review_correction_view(request, correction_id):
    """
    Approve or reject an attendance correction request.
    """
    correction = get_object_or_404(
        AttendanceCorrectionRequest.objects.select_related("student", "record", "record__session"),
        id=correction_id,
    )
    inst = getattr(request, "institution", None)
    if inst and correction.record.session.institution and correction.record.session.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to correction request outside your active institution.")

    if request.method == "POST":
        form = CorrectionReviewForm(request.POST)
        if form.is_valid():
            try:
                review_correction_request(
                    correction=correction,
                    decision=form.cleaned_data["decision"],
                    reviewer=request.user,
                    review_notes=form.cleaned_data["review_notes"],
                )
                messages.success(request, f"Correction request marked as '{correction.get_status_display()}'.")
                return redirect("attendance:admin_corrections")
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = CorrectionReviewForm()

    context = {
        "correction": correction,
        "form": form,
    }
    return render(request, "attendance/admin/review_correction.html", context)


@login_required
@role_required(Role.ADMIN)
def admin_attendance_report(request):
    """
    Generate attendance summaries and filterable reports by classroom, subject, and date range.
    Highlights students below minimum required attendance threshold (<75%).
    """
    inst = getattr(request, "institution", None)
    policy = get_active_attendance_policy(institution=inst)
    classrooms = ClassRoom.objects.filter(is_active=True).order_by("name")
    if inst:
        classrooms = classrooms.filter(institution=inst)
    selected_class_id = request.GET.get("classroom", "").strip()
    filter_defaulters = request.GET.get("defaulters_only") == "1"

    student_reports = []
    if selected_class_id:
        target_classroom = get_object_or_404(ClassRoom, id=selected_class_id)
        if inst and target_classroom.institution and target_classroom.institution != inst and not request.user.is_superuser:
            raise PermissionDenied("Access denied to classroom outside your active institution.")
        enrollments = ClassEnrollment.objects.filter(classroom=target_classroom, is_active=True).select_related("student")

        for e in enrollments:
            summary = calculate_student_attendance_summary(e.student, classroom=target_classroom, policy=policy)
            if filter_defaulters and not summary["is_below_minimum"]:
                continue
            student_reports.append({
                "student": e.student,
                "roll_number": e.roll_number,
                "total": summary["total_sessions"],
                "present": summary["present_count"],
                "absent": summary["absent_count"],
                "late": summary["late_count"],
                "excused": summary["excused_count"],
                "percentage": summary["percentage"],
                "is_below_minimum": summary["is_below_minimum"],
            })

    context = {
        "classrooms": classrooms,
        "selected_class_id": selected_class_id,
        "filter_defaulters": filter_defaulters,
        "student_reports": student_reports,
        "policy": policy,
    }
    return render(request, "attendance/admin/attendance_report.html", context)

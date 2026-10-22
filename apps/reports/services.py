"""
Administration Analytics & Report Generation Services for EduConnect.
Provides real database aggregation across all institutional modules,
audit logging for administrative interventions, and streaming CSV report exports.
"""

import csv
from decimal import Decimal
import io
from typing import Any, Dict
from django.db.models import Sum
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.admissions.models import AdmissionApplication
from apps.attendance.models import (
    AttendanceRecord,
    AttendanceSession,
    ClassEnrollment,
    ClassRoom,
    TeacherAssignment,
)
from apps.attendance.services import calculate_student_attendance_summary
from apps.academics.models import Assessment, StudentAssessmentScore
from apps.complaints.models import ComplaintTicket, TicketStatus
from apps.fees.models import Payment, PaymentStatus, StudentFeeAllocation
from apps.notifications.models import Announcement
from apps.reports.models import AdminAuditLog, InstitutionSetting


def get_client_ip(request) -> str:
    """
    Extracts client IP address from HTTP headers.
    """
    if not request:
        return ""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def log_admin_action(
    actor,
    action: str,
    description: str,
    target_model: str = "",
    target_id: str = "",
    request=None,
    institution=None,
) -> AdminAuditLog:
    """
    Records an administrative action in the immutable AdminAuditLog.
    """
    ip = get_client_ip(request)
    inst = institution or getattr(request, "institution", None)
    return AdminAuditLog.objects.create(
        institution=inst,
        actor=actor,
        action=action,
        description=description,
        target_model=target_model,
        target_id=str(target_id),
        ip_address=ip or None,
    )


def get_admin_dashboard_metrics(institution=None) -> Dict[str, Any]:
    """
    Computes genuine server-side statistics scoped to the given institution,
    or across the entire platform if institution is None.
    """
    now = timezone.now()

    # 1. Students & Enrolments
    if institution:
        total_students = User.objects.filter(
            institution_memberships__institution=institution,
            institution_memberships__role=Role.STUDENT,
            institution_memberships__is_active=True,
        ).distinct().count()
        if total_students == 0:
            total_students = ClassEnrollment.objects.filter(
                classroom__institution=institution,
                is_active=True,
            ).values("student").distinct().count()

        active_enrolments = ClassEnrollment.objects.filter(
            classroom__institution=institution,
            is_active=True,
        ).count()
        total_classrooms = ClassRoom.objects.filter(institution=institution, is_active=True).count()
        admissions_total = AdmissionApplication.objects.filter(institution=institution).count()
        admissions_pending = AdmissionApplication.objects.filter(
            institution=institution,
            status__in=["submitted", "under_review", "action_required"],
        ).count()
        allocations = StudentFeeAllocation.objects.filter(institution=institution)
        confirmed_payments_count = Payment.objects.filter(
            institution=institution,
            status=PaymentStatus.VERIFIED,
        ).count()
        attendance_sessions_count = AttendanceSession.objects.filter(institution=institution).count()
        attendance_records_count = AttendanceRecord.objects.filter(session__institution=institution).count()
        total_present = AttendanceRecord.objects.filter(session__institution=institution, status="present").count()
        open_complaints = ComplaintTicket.objects.filter(
            institution=institution,
            status__in=[TicketStatus.OPEN, TicketStatus.UNDER_REVIEW, TicketStatus.IN_PROGRESS],
        ).count()
        all_tickets = list(ComplaintTicket.objects.filter(institution=institution).select_related("category").all())
        active_teachers = User.objects.filter(
            institution_memberships__institution=institution,
            institution_memberships__role=Role.TEACHER,
            institution_memberships__is_active=True,
        ).distinct().count()
        active_assignments = TeacherAssignment.objects.filter(
            classroom__institution=institution,
            is_active=True,
        ).count()
        active_announcements = Announcement.objects.filter(
            institution=institution,
            is_published=True,
        ).count()
        settings_obj = InstitutionSetting.get_settings(institution=institution)
    else:
        total_students = User.objects.filter(role=Role.STUDENT).count()
        active_enrolments = ClassEnrollment.objects.filter(is_active=True).count()
        total_classrooms = ClassRoom.objects.filter(is_active=True).count()
        admissions_total = AdmissionApplication.objects.count()
        admissions_pending = AdmissionApplication.objects.filter(
            status__in=["submitted", "under_review", "action_required"]
        ).count()
        allocations = StudentFeeAllocation.objects.all()
        confirmed_payments_count = Payment.objects.filter(status=PaymentStatus.VERIFIED).count()
        attendance_sessions_count = AttendanceSession.objects.count()
        attendance_records_count = AttendanceRecord.objects.count()
        total_present = AttendanceRecord.objects.filter(status="present").count()
        open_complaints = ComplaintTicket.objects.filter(
            status__in=[TicketStatus.OPEN, TicketStatus.UNDER_REVIEW, TicketStatus.IN_PROGRESS]
        ).count()
        all_tickets = list(ComplaintTicket.objects.select_related("category").all())
        active_teachers = User.objects.filter(role=Role.TEACHER, is_active=True).count()
        active_assignments = TeacherAssignment.objects.filter(is_active=True).count()
        active_announcements = sum(1 for a in Announcement.objects.all() if a.is_active)
        settings_obj = InstitutionSetting.get_settings()

    # 3. Fees Collection & Outstanding
    total_gross = Decimal("0.00")
    total_net = Decimal("0.00")
    total_paid = Decimal("0.00")
    total_outstanding = Decimal("0.00")
    for a in allocations:
        total_gross += a.gross_amount
        total_net += a.net_amount
        total_paid += a.amount_paid
        total_outstanding += a.outstanding_balance

    # 4. Attendance presence rate
    overall_attendance_rate = Decimal("0.0")
    if attendance_records_count > 0:
        overall_attendance_rate = round(
            Decimal(str(total_present)) / Decimal(str(attendance_records_count)) * Decimal("100.0"), 1
        )

    # 5. Overdue complaints
    overdue_complaints = sum(1 for t in all_tickets if t.is_overdue)

    # 8. User Distribution Across All 6 Roles
    if institution:
        from apps.institutions.models import InstitutionMembership
        memberships_qs = InstitutionMembership.objects.filter(institution=institution, is_active=True)
        role_counts = {
            "admin": memberships_qs.filter(role=Role.ADMIN).count(),
            "teacher": active_teachers,
            "student": total_students,
            "parent": memberships_qs.filter(role=Role.PARENT).count(),
            "accounts": memberships_qs.filter(role=Role.ACCOUNTS).count(),
            "applicant": memberships_qs.filter(role=Role.APPLICANT).count(),
        }
    else:
        role_counts = {
            "admin": User.objects.filter(role=Role.ADMIN).count(),
            "teacher": active_teachers,
            "student": total_students,
            "parent": User.objects.filter(role=Role.PARENT).count(),
            "accounts": User.objects.filter(role=Role.ACCOUNTS).count(),
            "applicant": User.objects.filter(role=Role.APPLICANT).count(),
        }

    settings_obj = InstitutionSetting.get_settings()

    return {
        "institution_settings": settings_obj,
        "total_students": total_students,
        "active_enrolments": active_enrolments,
        "total_classrooms": total_classrooms,
        "admissions_total": admissions_total,
        "admissions_pending": admissions_pending,
        "total_gross_fees": total_net,
        "total_net_fees": total_net,
        "total_fees_collected": total_paid,
        "total_fees_outstanding": total_outstanding,
        "confirmed_payments_count": confirmed_payments_count,
        "attendance_sessions_count": attendance_sessions_count,
        "attendance_records_count": attendance_records_count,
        "overall_attendance_rate": overall_attendance_rate,
        "open_complaints": open_complaints,
        "overdue_complaints": overdue_complaints,
        "active_teachers": active_teachers,
        "active_assignments": active_assignments,
        "active_announcements": active_announcements,
        "role_counts": role_counts,
    }


# ==============================================================================
# CSV EXPORT GENERATORS
# ==============================================================================

def export_admissions_csv(queryset) -> str:
    """
    Exports filtered admission applications to CSV format.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Application Number",
        "Applicant Full Name",
        "Email",
        "Phone",
        "Program / Course",
        "Status",
        "Date Submitted",
    ])
    for app in queryset:
        writer.writerow([
            app.application_number,
            app.applicant.get_full_name() or app.applicant.username,
            app.applicant.email,
            getattr(app, "phone_number", ""),
            app.course.title if getattr(app, "course", None) else "General",
            app.get_status_display(),
            app.submitted_at.strftime("%Y-%m-%d %H:%M") if app.submitted_at else "",
        ])
    return output.getvalue()


def export_fees_csv(queryset) -> str:
    """
    Exports student fee allocations and dues to CSV format.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Student ID",
        "Student Name",
        "Email",
        "Fee Structure",
        "Gross Amount ($)",
        "Discount ($)",
        "Net Amount ($)",
        "Amount Paid ($)",
        "Outstanding Balance ($)",
        "Payment Status",
    ])
    for a in queryset:
        writer.writerow([
            a.student.student_id or a.student.username,
            a.student.get_full_name() or a.student.username,
            a.student.email,
            a.fee_structure.title if a.fee_structure else "General",
            str(a.gross_amount),
            str(a.discount_amount),
            str(a.net_amount),
            str(a.amount_paid),
            str(a.outstanding_balance),
            a.get_status_display(),
        ])
    return output.getvalue()


def export_attendance_csv(enrollments_queryset, classroom=None) -> str:
    """
    Exports student attendance summaries and percentages to CSV format.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Roll Number",
        "Student Name",
        "Classroom",
        "Total Sessions",
        "Present Count",
        "Absent Count",
        "Late Count",
        "Excused Count",
        "Attendance %",
        "Threshold Status",
    ])
    for enr in enrollments_queryset:
        summary = calculate_student_attendance_summary(
            student=enr.student,
            classroom=enr.classroom,
        )
        writer.writerow([
            enr.roll_number or "-",
            enr.student.get_full_name() or enr.student.username,
            enr.classroom.name,
            summary["total_sessions"],
            summary["present_count"],
            summary["absent_count"],
            summary["late_count"],
            summary["excused_count"],
            f"{summary['percentage'].quantize(Decimal('0.1'))}%",
            "Defaulter / Below 75%" if summary["is_below_minimum"] else "Satisfactory",
        ])
    return output.getvalue()


def export_academics_csv(scores_queryset) -> str:
    """
    Exports assessment marks and grade distributions to CSV format.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Assessment Title",
        "Type",
        "Subject",
        "Classroom",
        "Student Name",
        "Max Marks",
        "Marks Obtained",
        "Grade",
        "Remarks",
        "Published",
    ])
    for s in scores_queryset:
        writer.writerow([
            s.assessment.title,
            s.assessment.get_assessment_type_display(),
            s.assessment.subject_name,
            s.assessment.classroom.code,
            s.student.get_full_name() or s.student.username,
            str(s.assessment.max_marks),
            str(s.marks_obtained),
            s.grade,
            s.teacher_remarks,
            "Yes" if s.assessment.is_published else "Draft",
        ])
    return output.getvalue()


def export_complaints_csv(queryset) -> str:
    """
    Exports grievance tickets and resolution metrics to CSV format.
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Ticket Number",
        "Submitter Name",
        "Role",
        "Category",
        "Subject",
        "Priority",
        "Status",
        "Assigned To",
        "SLA (Days)",
        "Is Overdue",
        "Created At",
        "Resolved At",
        "Satisfaction (1-5)",
    ])
    for t in queryset:
        writer.writerow([
            t.ticket_number,
            t.submitter.get_full_name() or t.submitter.username,
            t.submitter.get_role_display(),
            t.category.name,
            t.subject,
            t.get_priority_display(),
            t.get_status_display(),
            t.assigned_to.username if t.assigned_to else "Unassigned",
            t.category.sla_days,
            "YES" if t.is_overdue else "No",
            t.created_at.strftime("%Y-%m-%d %H:%M"),
            t.resolved_at.strftime("%Y-%m-%d %H:%M") if t.resolved_at else "-",
            str(t.satisfaction_rating) if t.satisfaction_rating else "-",
        ])
    return output.getvalue()

"""
Views for EduConnect Administrative Dashboard & Reporting System.
Implements real database metric aggregation, filtered reports with CSV export,
institution settings, classroom/enrollment/teacher-assignment management,
and sensitive action audit logs.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import admin_required
from apps.admissions.models import AdmissionApplication
from apps.attendance.models import AcademicSession, ClassEnrollment, ClassRoom, TeacherAssignment
from apps.academics.models import Assessment, StudentAssessmentScore
from apps.complaints.models import ComplaintCategory, ComplaintTicket
from apps.fees.models import FeeStructure, StudentFeeAllocation
from apps.reports.forms import (
    ClassEnrollmentCreateForm,
    ClassRoomCreateForm,
    InstitutionSettingForm,
    TeacherAssignmentCreateForm,
)
from apps.reports.models import AdminAuditLog, InstitutionSetting
from apps.reports.services import (
    export_academics_csv,
    export_admissions_csv,
    export_attendance_csv,
    export_complaints_csv,
    export_fees_csv,
    get_admin_dashboard_metrics,
    log_admin_action,
)


@admin_required
def admin_dashboard_view(request):
    """
    Central Admin Dashboard populated with live database statistics.
    """
    metrics = get_admin_dashboard_metrics()
    recent_logs = AdminAuditLog.objects.select_related("actor").order_by("-created_at")[:6]
    recent_classrooms = ClassRoom.objects.filter(is_active=True).order_by("-created_at")[:5]

    context = {
        **metrics,
        "recent_logs": recent_logs,
        "recent_classrooms": recent_classrooms,
    }
    return render(request, "reports/admin/dashboard.html", context)


# ==============================================================================
# REPORT DESKS & EXPORTS
# ==============================================================================

@admin_required
def admissions_report(request):
    """
    Filtered admissions applications report with CSV download capability.
    """
    queryset = AdmissionApplication.objects.select_related("applicant", "course").order_by("-submitted_at")

    status_filter = request.GET.get("status")
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    search_query = request.GET.get("q")
    if search_query:
        queryset = queryset.filter(applicant__email__icontains=search_query)

    # CSV Export
    if request.GET.get("export") == "csv":
        csv_data = export_admissions_csv(queryset)
        log_admin_action(
            actor=request.user,
            action="EXPORT_REPORT",
            description="Exported Admissions Applications Report to CSV.",
            target_model="AdmissionApplication",
            request=request,
        )
        response = HttpResponse(csv_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="admissions_report.csv"'
        return response

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "total_count": queryset.count(),
        "selected_status": status_filter,
        "search_query": search_query,
    }
    return render(request, "reports/admin/admissions_report.html", context)


@admin_required
def fees_report(request):
    """
    Fee collections, outstanding dues, and ledger summaries with CSV export.
    """
    queryset = StudentFeeAllocation.objects.select_related("student", "fee_structure").order_by("-created_at")

    status_filter = request.GET.get("status")
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    structure_id = request.GET.get("fee_structure")
    if structure_id:
        queryset = queryset.filter(fee_structure_id=structure_id)

    # Aggregates for current filtered view
    total_net = sum(a.net_amount for a in queryset)
    total_collected = sum(a.amount_paid for a in queryset)
    total_balance = sum(a.outstanding_balance for a in queryset)

    # CSV Export
    if request.GET.get("export") == "csv":
        csv_data = export_fees_csv(queryset)
        log_admin_action(
            actor=request.user,
            action="EXPORT_REPORT",
            description="Exported Fee Collections and Dues Report to CSV.",
            target_model="StudentFeeAllocation",
            request=request,
        )
        response = HttpResponse(csv_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="fee_collection_report.csv"'
        return response

    structures = FeeStructure.objects.filter(is_active=True)
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "total_count": queryset.count(),
        "total_net": total_net,
        "total_collected": total_collected,
        "total_balance": total_balance,
        "structures": structures,
        "selected_status": status_filter,
        "selected_structure": structure_id,
    }
    return render(request, "reports/admin/fees_report.html", context)


@admin_required
def attendance_report(request):
    """
    Classroom-level attendance summaries and defaulter roster with CSV export.
    """
    classrooms = ClassRoom.objects.filter(is_active=True)
    selected_class_id = request.GET.get("classroom")

    if selected_class_id:
        selected_classroom = get_object_or_404(ClassRoom, id=selected_class_id)
        enrollments = ClassEnrollment.objects.filter(
            classroom=selected_classroom, is_active=True
        ).select_related("student", "classroom")
    else:
        selected_classroom = classrooms.first()
        if selected_classroom:
            enrollments = ClassEnrollment.objects.filter(
                classroom=selected_classroom, is_active=True
            ).select_related("student", "classroom")
        else:
            enrollments = ClassEnrollment.objects.none()

    # CSV Export
    if request.GET.get("export") == "csv":
        csv_data = export_attendance_csv(enrollments, selected_classroom)
        log_admin_action(
            actor=request.user,
            action="EXPORT_REPORT",
            description=f"Exported Attendance Report for {selected_classroom.name if selected_classroom else 'All'} to CSV.",
            target_model="AttendanceRecord",
            request=request,
        )
        response = HttpResponse(csv_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="attendance_report.csv"'
        return response

    context = {
        "classrooms": classrooms,
        "selected_classroom": selected_classroom,
        "enrollments": enrollments,
        "total_count": enrollments.count(),
    }
    return render(request, "reports/admin/attendance_report.html", context)


@admin_required
def academics_report(request):
    """
    Campus academic performance, assessments, and grade distribution report.
    """
    scores = StudentAssessmentScore.objects.select_related("assessment", "assessment__classroom", "student").order_by(
        "-assessment__date_conducted"
    )

    class_id = request.GET.get("classroom")
    if class_id:
        scores = scores.filter(assessment__classroom_id=class_id)

    asm_type = request.GET.get("type")
    if asm_type:
        scores = scores.filter(assessment__assessment_type=asm_type)

    # CSV Export
    if request.GET.get("export") == "csv":
        csv_data = export_academics_csv(scores)
        log_admin_action(
            actor=request.user,
            action="EXPORT_REPORT",
            description="Exported Academic Performance Report to CSV.",
            target_model="StudentAssessmentScore",
            request=request,
        )
        response = HttpResponse(csv_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="academics_report.csv"'
        return response

    classrooms = ClassRoom.objects.filter(is_active=True)
    paginator = Paginator(scores, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "classrooms": classrooms,
        "total_count": scores.count(),
        "selected_class": class_id,
        "selected_type": asm_type,
    }
    return render(request, "reports/admin/academics_report.html", context)


@admin_required
def complaints_report(request):
    """
    Grievance resolution statistics and overdue tickets report.
    """
    queryset = ComplaintTicket.objects.select_related("category", "submitter", "assigned_to").order_by("-created_at")

    category_code = request.GET.get("category")
    if category_code:
        queryset = queryset.filter(category__code=category_code)

    status_filter = request.GET.get("status")
    if status_filter:
        queryset = queryset.filter(status=status_filter)

    # CSV Export
    if request.GET.get("export") == "csv":
        csv_data = export_complaints_csv(queryset)
        log_admin_action(
            actor=request.user,
            action="EXPORT_REPORT",
            description="Exported Grievance Tickets Report to CSV.",
            target_model="ComplaintTicket",
            request=request,
        )
        response = HttpResponse(csv_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="complaints_report.csv"'
        return response

    categories = ComplaintCategory.objects.filter(is_active=True)
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page_obj,
        "categories": categories,
        "total_count": queryset.count(),
        "selected_category": category_code,
        "selected_status": status_filter,
    }
    return render(request, "reports/admin/complaints_report.html", context)


# ==============================================================================
# MANAGEMENT DESKS & INSTITUTION SETTINGS
# ==============================================================================

@admin_required
def institution_settings_view(request):
    """
    Configure global institutional operational parameters with audit logging.
    """
    settings_obj = InstitutionSetting.get_settings()
    if request.method == "POST":
        form = InstitutionSettingForm(request.POST, instance=settings_obj)
        if form.is_valid():
            inst = form.save(commit=False)
            inst.updated_by = request.user
            inst.save()
            log_admin_action(
                actor=request.user,
                action="SETTINGS_UPDATE",
                description=f"Updated institution settings for {inst.institution_name}.",
                target_model="InstitutionSetting",
                target_id=str(inst.id),
                request=request,
            )
            messages.success(request, "Institution settings saved successfully.")
            return redirect("reports:institution_settings")
    else:
        form = InstitutionSettingForm(instance=settings_obj)

    return render(request, "reports/admin/settings.html", {"form": form})


@admin_required
def admin_audit_logs_view(request):
    """
    Search and inspect immutable audit logs of administrative operations.
    """
    logs = AdminAuditLog.objects.select_related("actor").order_by("-created_at")

    action_filter = request.GET.get("action")
    if action_filter:
        logs = logs.filter(action__icontains=action_filter)

    paginator = Paginator(logs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "reports/admin/audit_logs.html",
        {"page_obj": page_obj, "selected_action": action_filter},
    )


@admin_required
def manage_classes_view(request):
    """
    Manage classrooms and section cohorts with live creation.
    """
    if request.method == "POST":
        form = ClassRoomCreateForm(request.POST)
        if form.is_valid():
            classroom = form.save()
            log_admin_action(
                actor=request.user,
                action="CLASS_CREATE",
                description=f"Created classroom {classroom.name} ({classroom.code}).",
                target_model="ClassRoom",
                target_id=str(classroom.id),
                request=request,
            )
            messages.success(request, f"Classroom {classroom.name} created successfully.")
            return redirect("reports:manage_classes")
    else:
        form = ClassRoomCreateForm()

    classrooms = ClassRoom.objects.select_related("academic_session").all()
    return render(
        request,
        "reports/admin/manage_classes.html",
        {"form": form, "classrooms": classrooms},
    )


@admin_required
def manage_enrollments_view(request):
    """
    Enrol registered students into designated classroom cohorts.
    """
    if request.method == "POST":
        form = ClassEnrollmentCreateForm(request.POST)
        if form.is_valid():
            enr = form.save()
            log_admin_action(
                actor=request.user,
                action="ENROLLMENT_CREATE",
                description=f"Enrolled {enr.student.username} into {enr.classroom.code}.",
                target_model="ClassEnrollment",
                target_id=str(enr.id),
                request=request,
            )
            messages.success(request, f"Student {enr.student.get_full_name()} enrolled into {enr.classroom.name}.")
            return redirect("reports:manage_enrollments")
    else:
        form = ClassEnrollmentCreateForm()

    enrollments = ClassEnrollment.objects.select_related("student", "classroom").all().order_by("-enrolled_date")
    paginator = Paginator(enrollments, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "reports/admin/manage_enrollments.html",
        {"form": form, "page_obj": page_obj},
    )


@admin_required
def manage_assignments_view(request):
    """
    Authorize faculty teaching assignments for designated subjects and classes.
    """
    if request.method == "POST":
        form = TeacherAssignmentCreateForm(request.POST)
        if form.is_valid():
            ta = form.save()
            log_admin_action(
                actor=request.user,
                action="TEACHER_ASSIGNMENT",
                description=f"Assigned {ta.teacher.username} to teach {ta.subject_name} in {ta.classroom.code}.",
                target_model="TeacherAssignment",
                target_id=str(ta.id),
                request=request,
            )
            messages.success(
                request,
                f"Assigned {ta.teacher.get_full_name()} to teach {ta.subject_name} ({ta.classroom.name}).",
            )
            return redirect("reports:manage_assignments")
    else:
        form = TeacherAssignmentCreateForm()

    assignments = TeacherAssignment.objects.select_related("teacher", "classroom").all()
    return render(
        request,
        "reports/admin/manage_assignments.html",
        {"form": form, "assignments": assignments},
    )

"""
EduConnect Admissions Management Views.
Handles applicant submission, permitted updates, document uploads,
document access control, administrative review, decisions, and student conversion.
"""

import os
import secrets
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from apps.accounts.decorators import admin_required
from apps.accounts.models import Role, User
from apps.core.models import Course
from apps.academics.models import Batch
from apps.academics.services import enroll_student_in_batch
from apps.institutions.models import Institution, InstitutionMembership, Branch
from .forms import (
    AdminApplicationDecisionForm,
    AdmissionApplicationForm,
    AdmissionApplicationUpdateForm,
    ApplicationDocumentUploadForm,
    PublicEnquiryForm,
    StaffEnquiryForm,
    EnquiryFollowUpForm,
    EnquiryAssignStaffForm,
    ConvertApplicantToStudentForm,
)
from .models import (
    AdmissionApplication,
    ApplicationDocument,
    ApplicationStatus,
    ApplicationStatusHistory,
    DocumentType,
    Enquiry,
    EnquiryFollowUp,
    EnquirySource,
    EnquiryStatus,
)


# ==============================================================================
# Applicant-Facing Views
# ==============================================================================

def course_eligibility_view(request):
    """
    View available courses, duration, fee per term, and prerequisite eligibility.
    """
    selected_level = request.GET.get("level", "").strip()
    courses = Course.objects.filter(is_active=True)

    if selected_level and selected_level in [lvl[0] for lvl in Course.Level.choices]:
        courses = courses.filter(level=selected_level)

    courses = courses.order_by("level", "code")

    context = {
        "page_title": "Courses & Admission Eligibility",
        "courses": courses,
        "levels": Course.Level.choices,
        "selected_level": selected_level,
    }
    return render(request, "admissions/eligibility.html", context)


@login_required
def apply_view(request):
    """
    Create a new admission application with applicant details and required documents.
    """
    # Pre-select course if slug provided in query string
    course_slug = request.GET.get("course", "").strip()
    initial_course = None
    if course_slug:
        initial_course = Course.objects.filter(slug=course_slug, is_active=True).first()

    # Pre-fill applicant details from user account
    initial_data = {
        "first_name": request.user.first_name,
        "last_name": request.user.last_name,
        "email": request.user.email,
        "phone_number": request.user.phone_number,
    }
    if initial_course:
        initial_data["course"] = initial_course

    if request.method == "POST":
        form = AdmissionApplicationForm(
            request.POST,
            request.FILES,
            applicant_user=request.user,
        )
        if form.is_valid():
            application = form.save(commit=False)
            application.applicant = request.user
            application.status = ApplicationStatus.SUBMITTED
            application.submitted_at = timezone.now()
            inst = getattr(request, "institution", None)
            if inst:
                application.institution = inst
            elif application.course and application.course.institution:
                application.institution = application.course.institution
            application.save()

            # Process mandatory uploaded documents
            identity_file = request.FILES.get("identity_proof_file")
            if identity_file:
                ApplicationDocument.objects.create(
                    application=application,
                    document_type=DocumentType.IDENTITY_PROOF,
                    title="National ID / Birth Certificate",
                    file=identity_file,
                )

            transcript_file = request.FILES.get("transcript_file")
            if transcript_file:
                ApplicationDocument.objects.create(
                    application=application,
                    document_type=DocumentType.ACADEMIC_TRANSCRIPT,
                    title="Prior Academic Transcript",
                    file=transcript_file,
                )

            photo_file = request.FILES.get("passport_photo_file")
            if photo_file:
                ApplicationDocument.objects.create(
                    application=application,
                    document_type=DocumentType.PASSPORT_PHOTO,
                    title="Passport Size Photograph",
                    file=photo_file,
                )

            # Record initial audit entry
            ApplicationStatusHistory.objects.create(
                application=application,
                from_status="",
                to_status=ApplicationStatus.SUBMITTED,
                changed_by=request.user,
                notes="Initial application submitted with required verification documents.",
            )

            messages.success(
                request,
                f"Your admission application has been submitted successfully! "
                f"Your unique reference number is {application.application_number}. "
                f"Keep this reference number for all future inquiries.",
            )
            return redirect("admissions:application_detail", application_number=application.application_number)
        else:
            messages.error(request, "Please review the form and correct the highlighted errors.")
    else:
        form = AdmissionApplicationForm(initial=initial_data, applicant_user=request.user)

    context = {
        "page_title": "Submit Admission Application",
        "form": form,
        "initial_course": initial_course,
    }
    return render(request, "admissions/apply.html", context)


@login_required
def my_applications_view(request):
    """
    List all admission applications submitted by the logged-in applicant.
    """
    applications = AdmissionApplication.objects.filter(applicant=request.user).order_by("-submitted_at")
    context = {
        "page_title": "My Admission Applications",
        "applications": applications,
    }
    return render(request, "admissions/my_applications.html", context)


@login_required
def application_detail_view(request, application_number):
    """
    View status, timeline, missing document notices, decision letters, and documents.
    """
    application = get_object_or_404(AdmissionApplication, application_number=application_number)

    # Permission check: must be applicant or admin/staff
    if not (request.user == application.applicant or request.user.role == Role.ADMIN or request.user.is_superuser):
        raise PermissionDenied("You do not have permission to view this application.")

    documents = application.documents.all()
    history = application.status_history.all()

    context = {
        "page_title": f"Application {application.application_number}",
        "application": application,
        "documents": documents,
        "history": history,
    }
    return render(request, "admissions/detail.html", context)


@login_required
def edit_application_view(request, application_number):
    """
    Update permitted details when the application is in an editable state (Draft or Action Required).
    """
    application = get_object_or_404(AdmissionApplication, application_number=application_number)

    # Permission check: must be applicant or admin
    if not (request.user == application.applicant or request.user.role == Role.ADMIN or request.user.is_superuser):
        raise PermissionDenied("You do not have permission to modify this application.")

    # Status check: only editable when in DRAFT or ACTION_REQUIRED
    if not application.is_editable:
        messages.error(
            request,
            f"Application {application.application_number} is currently '{application.get_status_display()}' "
            f"and cannot be edited at this stage.",
        )
        return redirect("admissions:application_detail", application_number=application.application_number)

    if request.method == "POST":
        form = AdmissionApplicationUpdateForm(request.POST, instance=application)
        if form.is_valid():
            form.save()

            ApplicationStatusHistory.objects.create(
                application=application,
                from_status=application.status,
                to_status=application.status,
                changed_by=request.user,
                notes="Applicant updated personal, guardian, or academic information.",
            )

            messages.success(request, "Application details updated successfully.")
            return redirect("admissions:application_detail", application_number=application.application_number)
        else:
            messages.error(request, "Please correct the errors in the update form.")
    else:
        form = AdmissionApplicationUpdateForm(instance=application)

    context = {
        "page_title": f"Edit Application {application.application_number}",
        "application": application,
        "form": form,
    }
    return render(request, "admissions/edit.html", context)


@login_required
def upload_document_view(request, application_number):
    """
    Upload an additional or requested missing document for the application.
    """
    application = get_object_or_404(AdmissionApplication, application_number=application_number)

    if not (request.user == application.applicant or request.user.role == Role.ADMIN or request.user.is_superuser):
        raise PermissionDenied("You do not have permission to upload documents for this application.")

    if not application.is_editable and not (request.user.role == Role.ADMIN or request.user.is_superuser):
        messages.error(
            request,
            "Document upload is closed while your application is undergoing review or finalized.",
        )
        return redirect("admissions:application_detail", application_number=application.application_number)

    if request.method == "POST":
        form = ApplicationDocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            doc = form.save(commit=False)
            doc.application = application
            doc.save()

            ApplicationStatusHistory.objects.create(
                application=application,
                from_status=application.status,
                to_status=application.status,
                changed_by=request.user,
                notes=f"New document uploaded: {doc.get_document_type_display()} ({doc.title}).",
            )

            messages.success(request, f"Document '{doc.title}' uploaded successfully.")
            return redirect("admissions:application_detail", application_number=application.application_number)
        else:
            messages.error(request, "Please check the document file type and size (max 5 MB).")
    else:
        form = ApplicationDocumentUploadForm()

    context = {
        "page_title": f"Upload Document - {application.application_number}",
        "application": application,
        "form": form,
    }
    return render(request, "admissions/upload_document.html", context)


@login_required
def resubmit_application_view(request, application_number):
    """
    Applicant resubmits their application after updating requested information.
    Transitions status from ACTION_REQUIRED back to SUBMITTED.
    """
    if request.method != "POST":
        return redirect("admissions:application_detail", application_number=application_number)

    application = get_object_or_404(AdmissionApplication, application_number=application_number)

    if not (request.user == application.applicant or request.user.is_superuser):
        raise PermissionDenied("You cannot resubmit this application.")

    if application.status != ApplicationStatus.ACTION_REQUIRED:
        messages.warning(request, "This application does not require resubmission.")
        return redirect("admissions:application_detail", application_number=application.application_number)

    prev_status = application.status
    application.status = ApplicationStatus.SUBMITTED
    application.save()

    ApplicationStatusHistory.objects.create(
        application=application,
        from_status=prev_status,
        to_status=ApplicationStatus.SUBMITTED,
        changed_by=request.user,
        notes="Applicant addressed required items and resubmitted application for staff review.",
    )

    messages.success(request, "Application resubmitted successfully! It is now pending staff review.")
    return redirect("admissions:application_detail", application_number=application.application_number)


@login_required
def download_document_view(request, document_id):
    """
    Secure document download endpoint:
    Restricts access strictly to administrators or the owning applicant.
    """
    document = get_object_or_404(ApplicationDocument, pk=document_id)
    inst = getattr(request, "institution", None)
    if inst and document.application.institution and document.application.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to documents from another institution.")

    # Permission check
    is_admin_user = request.user.role == Role.ADMIN or request.user.is_superuser
    is_owner = request.user == document.application.applicant

    if not (is_admin_user or is_owner):
        raise PermissionDenied("You do not have permission to view or download this document.")

    if not document.file:
        raise Http404("Document file does not exist.")

    try:
        response = FileResponse(document.file.open("rb"))
        response["Content-Disposition"] = f'inline; filename="{os.path.basename(document.file.name)}"'
        return response
    except FileNotFoundError:
        raise Http404("The requested file was not found on the server.")


# ==============================================================================
# Administrative Views (Staff / Admin)
# ==============================================================================

@admin_required
def admin_application_list_view(request):
    """
    Administrative directory to view, search, and filter admission applications.
    """
    inst = getattr(request, "institution", None)
    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    course_filter = request.GET.get("course", "").strip()
    ordering = request.GET.get("ordering", "-submitted_at")

    applications = AdmissionApplication.objects.select_related("course", "applicant")
    if inst:
        applications = applications.filter(institution=inst)

    # Search filter
    if query:
        applications = applications.filter(
            Q(application_number__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone_number__icontains=query)
        )

    # Status filter
    if status_filter and status_filter in [s[0] for s in ApplicationStatus.choices]:
        applications = applications.filter(status=status_filter)

    # Course filter
    if course_filter:
        applications = applications.filter(course__code=course_filter)

    # Ordering
    if ordering in ["submitted_at", "-submitted_at", "first_name", "-first_name"]:
        applications = applications.order_by(ordering)
    else:
        applications = applications.order_by("-submitted_at")

    # Counts
    base_apps = AdmissionApplication.objects.filter(institution=inst) if inst else AdmissionApplication.objects.all()
    stats = {
        "total": base_apps.count(),
        "submitted": base_apps.filter(status=ApplicationStatus.SUBMITTED).count(),
        "under_review": base_apps.filter(status=ApplicationStatus.UNDER_REVIEW).count(),
        "action_required": base_apps.filter(status=ApplicationStatus.ACTION_REQUIRED).count(),
        "approved": base_apps.filter(status=ApplicationStatus.APPROVED).count(),
        "rejected": base_apps.filter(status=ApplicationStatus.REJECTED).count(),
        "enrolled": base_apps.filter(status=ApplicationStatus.ENROLLED).count(),
    }

    courses = Course.objects.filter(is_active=True)
    if inst:
        courses = courses.filter(institution=inst)
    courses = courses.order_by("code")

    context = {
        "page_title": "Admissions Desk - Applications",
        "applications": applications,
        "courses": courses,
        "statuses": ApplicationStatus.choices,
        "stats": stats,
        "query": query,
        "selected_status": status_filter,
        "selected_course": course_filter,
        "ordering": ordering,
    }
    return render(request, "admissions/admin/list.html", context)


@admin_required
def admin_application_detail_view(request, application_number):
    """
    Administrative dossier review of application details, uploaded files, and status history.
    """
    application = get_object_or_404(AdmissionApplication, application_number=application_number)
    inst = getattr(request, "institution", None)
    if inst and application.institution and application.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to application from another institution.")

    documents = application.documents.all()
    history = application.status_history.all()

    decision_form = AdminApplicationDecisionForm(
        initial={
            "status": application.status if application.status in [ApplicationStatus.UNDER_REVIEW, ApplicationStatus.ACTION_REQUIRED, ApplicationStatus.APPROVED, ApplicationStatus.REJECTED] else ApplicationStatus.UNDER_REVIEW,
            "applicant_remarks": application.applicant_remarks,
            "admin_notes": application.admin_notes,
        }
    )

    available_batches = Batch.objects.filter(
        course=application.course,
        status__in=[Batch.Status.UPCOMING, Batch.Status.ONGOING],
    )
    if application.institution:
        available_batches = available_batches.filter(institution=application.institution)
    elif inst:
        available_batches = available_batches.filter(institution=inst)

    context = {
        "page_title": f"Review Application: {application.application_number}",
        "application": application,
        "documents": documents,
        "history": history,
        "decision_form": decision_form,
        "available_batches": available_batches,
    }
    return render(request, "admissions/admin/detail.html", context)


@admin_required
def admin_application_decision_view(request, application_number):
    """
    Execute decision transition: Under Review, Action Required, Approved, or Rejected.
    """
    if request.method != "POST":
        return redirect("admissions:admin_application_detail", application_number=application_number)

    application = get_object_or_404(AdmissionApplication, application_number=application_number)
    inst = getattr(request, "institution", None)
    if inst and application.institution and application.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to application from another institution.")

    # Disallow tampering if already enrolled
    if application.status == ApplicationStatus.ENROLLED:
        messages.error(request, "This application is already officially enrolled and cannot be transitioned.")
        return redirect("admissions:admin_application_detail", application_number=application.application_number)

    form = AdminApplicationDecisionForm(request.POST)
    if form.is_valid():
        prev_status = application.status
        new_status = form.cleaned_data["status"]
        remarks = form.cleaned_data["applicant_remarks"]
        admin_notes = form.cleaned_data.get("admin_notes", "")

        # Update application state
        application.status = new_status
        application.applicant_remarks = remarks
        application.admin_notes = admin_notes
        application.decided_by = request.user

        if new_status == ApplicationStatus.ACTION_REQUIRED:
            application.missing_documents_requested = remarks

        if new_status in [ApplicationStatus.APPROVED, ApplicationStatus.REJECTED]:
            application.decision_date = timezone.now()

        application.save()

        # Audit history
        ApplicationStatusHistory.objects.create(
            application=application,
            from_status=prev_status,
            to_status=new_status,
            changed_by=request.user,
            notes=f"Decision recorded: {application.get_status_display()}. Remarks: {remarks}",
        )

        messages.success(
            request,
            f"Application {application.application_number} transitioned to '{application.get_status_display()}'.",
        )
    else:
        messages.error(request, "Invalid decision submission. Please provide necessary remarks.")

    return redirect("admissions:admin_application_detail", application_number=application.application_number)


@admin_required
def admin_convert_to_student_view(request, application_number):
    """
    Convert an approved applicant into an active student:
    - Verifies status is Approved
    - Prevents duplicate student accounts: checks if user exists by email, links existing account
    - Assigns unique institutional student_id
    - Updates user role to Student
    - Ensures InstitutionMembership exists for this student at this institution
    - Enrolls student into target batch if specified
    - Links converted_student and sets status to Enrolled
    - Updates linked source_enquiry or matching enquiries to Converted
    """
    if request.method != "POST":
        return redirect("admissions:admin_application_detail", application_number=application_number)

    application = get_object_or_404(AdmissionApplication, application_number=application_number)
    inst = getattr(request, "institution", None)
    if inst and application.institution and application.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to application from another institution.")

    # Check eligibility
    if application.status != ApplicationStatus.APPROVED:
        messages.error(
            request,
            f"Only Approved applications can be converted into active students. "
            f"Current status is '{application.get_status_display()}'.",
        )
        return redirect("admissions:admin_application_detail", application_number=application.application_number)

    if application.converted_student or application.status == ApplicationStatus.ENROLLED:
        messages.warning(
            request,
            f"This application was already converted to an active student (ID: {application.student_id_assigned}).",
        )
        return redirect("admissions:admin_application_detail", application_number=application.application_number)

    target_institution = application.institution or inst

    # Prevent duplicate student accounts: check if an existing user exists with this email
    existing_user = User.objects.filter(email__iexact=application.email.strip()).first()
    if existing_user:
        user = existing_user
        if user.role == Role.APPLICANT:
            user.role = Role.STUDENT
    else:
        user = application.applicant
        if user.role == Role.APPLICANT:
            user.role = Role.STUDENT

    # Assign student ID if not present
    if not user.student_id:
        year = timezone.now().year
        while True:
            candidate_id = f"STU-{year}-{secrets.token_hex(3).upper()}"
            if not User.objects.filter(student_id=candidate_id).exists():
                user.student_id = candidate_id
                break

    if application.course and not user.grade_level:
        user.grade_level = application.course.title
    user.save()

    # Ensure InstitutionMembership exists for this student at this institution
    if target_institution:
        membership, _ = InstitutionMembership.objects.get_or_create(
            user=user,
            institution=target_institution,
            defaults={"role": Role.STUDENT, "is_active": True},
        )
        if membership.role != Role.STUDENT:
            membership.role = Role.STUDENT
            membership.is_active = True
            membership.save()

    # Batch enrolment
    batch_id = request.POST.get("target_batch")
    target_batch = None
    if batch_id:
        target_batch = Batch.objects.filter(id=batch_id, institution=target_institution).first()
    elif application.target_batch:
        target_batch = application.target_batch
    elif application.source_enquiry and application.source_enquiry.batch_interest:
        target_batch = application.source_enquiry.batch_interest

    roll_number = request.POST.get("roll_number", "").strip() or user.student_id

    batch_enrolled = False
    if target_batch:
        try:
            enroll_student_in_batch(
                student=user,
                batch=target_batch,
                roll_number=roll_number,
                created_by=request.user,
                notes=f"Enrolled via admission application {application.application_number}",
            )
            application.target_batch = target_batch
            batch_enrolled = True
        except ValidationError as e:
            messages.warning(
                request,
                f"Applicant converted to student, but batch enrolment note: {e.message if hasattr(e, 'message') else e}"
            )

    # Update application
    prev_status = application.status
    application.status = ApplicationStatus.ENROLLED
    application.converted_student = user
    application.student_id_assigned = user.student_id
    application.save()

    # Update linked source_enquiry or any matching enquiry by email
    if application.source_enquiry:
        eq = application.source_enquiry
        eq.status = EnquiryStatus.CONVERTED
        eq.converted_student = user
        eq.converted_application = application
        eq.converted_at = timezone.now()
        eq.save()

    if target_institution:
        matching_enquiries = Enquiry.objects.filter(
            institution=target_institution,
            email__iexact=application.email.strip(),
        ).exclude(status=EnquiryStatus.CONVERTED)
        for eq in matching_enquiries:
            eq.status = EnquiryStatus.CONVERTED
            eq.converted_student = user
            eq.converted_application = application
            eq.converted_at = timezone.now()
            eq.save()

    # Audit history
    notes = f"Applicant converted into active Student with ID {user.student_id}."
    if batch_enrolled:
        notes += f" Enrolled into batch '{target_batch.name}'."
    ApplicationStatusHistory.objects.create(
        application=application,
        from_status=prev_status,
        to_status=ApplicationStatus.ENROLLED,
        changed_by=request.user,
        notes=notes,
    )

    messages.success(
        request,
        f"Enrollment successful! {application.full_name} is now an active Student with ID: {user.student_id}."
        + (f" Enrolled in batch {target_batch.name}." if batch_enrolled else "")
    )
    return redirect("admissions:admin_application_detail", application_number=application.application_number)


@admin_required
def admin_verify_document_view(request, document_id):
    """
    Toggle document verification badge.
    """
    if request.method != "POST":
        return redirect("admissions:admin_application_list")

    document = get_object_or_404(ApplicationDocument, pk=document_id)
    inst = getattr(request, "institution", None)
    if inst and document.application.institution and document.application.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to document from another institution.")

    document.is_verified = not document.is_verified
    document.verification_notes = (
        f"Verified by {request.user.username} on {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        if document.is_verified
        else ""
    )
    document.save()

    status_str = "verified" if document.is_verified else "unverified"
    messages.success(request, f"Document '{document.title}' marked as {status_str}.")
    return redirect("admissions:admin_application_detail", application_number=document.application.application_number)


# ==============================================================================
# Coaching CRM & Enquiries Views (Task 3)
# ==============================================================================

def public_enquiry_create_view(request, institution_slug=None):
    """
    Public-facing enquiry form on the institute's public website.
    Supports institute-scoped prospect submission.
    """
    target_institution = None
    if institution_slug:
        target_institution = get_object_or_404(Institution, slug=institution_slug, is_active=True)
    else:
        inst_param = request.GET.get("institution") or request.GET.get("inst")
        if inst_param:
            target_institution = (
                Institution.objects.filter(slug=inst_param, is_active=True).first()
                or Institution.objects.filter(code__iexact=inst_param, is_active=True).first()
            )
            if not target_institution and len(inst_param) == 24:
                try:
                    target_institution = Institution.objects.filter(id=inst_param, is_active=True).first()
                except Exception:
                    pass
    if not target_institution:
        target_institution = getattr(request, "institution", None) or Institution.objects.filter(is_active=True).first()

    submitted_enquiry = None

    if request.method == "POST":
        form = PublicEnquiryForm(request.POST, institution=target_institution)
        if form.is_valid():
            enquiry = form.save(commit=False)
            enquiry.institution = target_institution
            enquiry.source = EnquirySource.WEBSITE
            enquiry.status = EnquiryStatus.NEW
            enquiry.save()

            # Record initial interaction log
            first_admin = None
            if target_institution:
                first_mem = target_institution.memberships.filter(role=Role.ADMIN).first()
                if first_mem:
                    first_admin = first_mem.user
            if not first_admin:
                first_admin = User.objects.filter(role=Role.ADMIN).first() or User.objects.first()

            if first_admin:
                EnquiryFollowUp.objects.create(
                    enquiry=enquiry,
                    staff=first_admin,
                    contact_mode="email",
                    notes="Online prospect enquiry submitted via institute public website.",
                    old_status="",
                    new_status=EnquiryStatus.NEW,
                )

            messages.success(
                request,
                f"Thank you for contacting us! Your enquiry reference number is {enquiry.enquiry_number}. "
                f"Our academic counselors will get in touch with you shortly."
            )
            submitted_enquiry = enquiry
            form = PublicEnquiryForm(institution=target_institution)
    else:
        form = PublicEnquiryForm(institution=target_institution)

    context = {
        "page_title": f"Admissions Enquiry - {target_institution.name if target_institution else 'EduConnect'}",
        "target_institution": target_institution,
        "form": form,
        "submitted_enquiry": submitted_enquiry,
    }
    return render(request, "admissions/public_enquiry.html", context)


@login_required
def admin_enquiries_list_view(request):
    """
    CRM Enquiries directory & pipeline management desk for institute staff.
    """
    inst = getattr(request, "institution", None)
    active_role = getattr(request, "user_role", None) or getattr(request.user, "role", None)
    if not (request.user.is_superuser or active_role in [Role.ADMIN, Role.TEACHER, Role.ACCOUNTS]):
        raise PermissionDenied("You do not have permission to access the CRM Enquiries Desk.")

    query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    source_filter = request.GET.get("source", "").strip()
    assigned_filter = request.GET.get("assigned_to", "").strip()

    enquiries = Enquiry.objects.select_related("course", "batch_interest", "assigned_to", "branch")
    if inst:
        enquiries = enquiries.filter(institution=inst)

    if query:
        enquiries = enquiries.filter(
            Q(enquiry_number__icontains=query)
            | Q(name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
            | Q(target_class__icontains=query)
        )

    if status_filter and status_filter in [s[0] for s in EnquiryStatus.choices]:
        enquiries = enquiries.filter(status=status_filter)

    if source_filter and source_filter in [s[0] for s in EnquirySource.choices]:
        enquiries = enquiries.filter(source=source_filter)

    if assigned_filter:
        if assigned_filter == "unassigned":
            enquiries = enquiries.filter(assigned_to__isnull=True)
        else:
            enquiries = enquiries.filter(assigned_to_id=assigned_filter)

    base_qs = Enquiry.objects.filter(institution=inst) if inst else Enquiry.objects.all()
    total_count = base_qs.count()
    converted_count = base_qs.filter(status=EnquiryStatus.CONVERTED).count()
    conversion_rate = round((converted_count / total_count * 100), 1) if total_count > 0 else 0.0

    today = timezone.now().date()
    stats = {
        "total": total_count,
        "new": base_qs.filter(status=EnquiryStatus.NEW).count(),
        "contacted": base_qs.filter(status=EnquiryStatus.CONTACTED).count(),
        "trial_class": base_qs.filter(status=EnquiryStatus.TRIAL_CLASS).count(),
        "follow_up_required": base_qs.filter(status=EnquiryStatus.FOLLOW_UP_REQUIRED).count(),
        "converted": converted_count,
        "not_interested": base_qs.filter(status=EnquiryStatus.NOT_INTERESTED).count(),
        "conversion_rate": conversion_rate,
        "follow_ups_due_today": base_qs.filter(next_follow_up_date=today).count(),
        "overdue_follow_ups": base_qs.filter(
            next_follow_up_date__lt=today,
            status__in=[EnquiryStatus.NEW, EnquiryStatus.CONTACTED, EnquiryStatus.FOLLOW_UP_REQUIRED],
        ).count(),
    }

    if inst:
        staff_members = User.objects.filter(
            institution_memberships__institution=inst,
            institution_memberships__role__in=[Role.ADMIN, Role.TEACHER, Role.ACCOUNTS],
            institution_memberships__is_active=True,
        ).distinct()
    else:
        staff_members = User.objects.filter(role__in=[Role.ADMIN, Role.TEACHER])

    context = {
        "page_title": "CRM Enquiries & Leads Desk",
        "enquiries": enquiries.order_by("-created_at"),
        "statuses": EnquiryStatus.choices,
        "sources": EnquirySource.choices,
        "staff_members": staff_members,
        "stats": stats,
        "query": query,
        "selected_status": status_filter,
        "selected_source": source_filter,
        "selected_assigned": assigned_filter,
    }
    return render(request, "admissions/admin/enquiries/list.html", context)


@login_required
def admin_enquiry_create_view(request):
    """
    Staff manual entry for enquiries received by phone, walk-in, referral, or email.
    """
    inst = getattr(request, "institution", None)
    active_role = getattr(request, "user_role", None) or getattr(request.user, "role", None)
    if not (request.user.is_superuser or active_role in [Role.ADMIN, Role.TEACHER, Role.ACCOUNTS]):
        raise PermissionDenied("You do not have permission to log enquiries.")

    if request.method == "POST":
        form = StaffEnquiryForm(request.POST, institution=inst)
        if form.is_valid():
            enquiry = form.save(commit=False)
            enquiry.institution = inst or (Institution.objects.filter(is_active=True).first())
            enquiry.save()

            # Record initial follow-up note
            initial_note = f"Lead logged manually via {enquiry.get_source_display()}."
            if enquiry.notes:
                initial_note += f" Initial remarks: {enquiry.notes}"
            EnquiryFollowUp.objects.create(
                enquiry=enquiry,
                staff=request.user,
                contact_mode=enquiry.source if enquiry.source in ["phone", "walk_in"] else "other",
                notes=initial_note,
                old_status="",
                new_status=enquiry.status,
                scheduled_follow_up_date=enquiry.next_follow_up_date,
            )

            messages.success(request, f"Enquiry {enquiry.enquiry_number} for {enquiry.name} created successfully.")
            return redirect("admissions:admin_enquiry_detail", enquiry_number=enquiry.enquiry_number)
        else:
            messages.error(request, "Please review the form for errors.")
    else:
        form = StaffEnquiryForm(institution=inst, initial={"source": EnquirySource.PHONE})

    context = {
        "page_title": "Log New Prospect Enquiry",
        "form": form,
    }
    return render(request, "admissions/admin/enquiries/form.html", context)


@login_required
def admin_enquiry_detail_view(request, enquiry_number):
    """
    360-degree enquiry overview with follow-up timeline, counselor assignment, and quick convert.
    """
    enquiry = get_object_or_404(Enquiry, enquiry_number=enquiry_number)
    inst = getattr(request, "institution", None)
    if inst and enquiry.institution and enquiry.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied: Enquiry belongs to another institution.")

    active_role = getattr(request, "user_role", None) or getattr(request.user, "role", None)
    if not (request.user.is_superuser or active_role in [Role.ADMIN, Role.TEACHER, Role.ACCOUNTS]):
        raise PermissionDenied("You do not have permission to view enquiry details.")

    follow_up_form = EnquiryFollowUpForm(initial={
        "new_status": enquiry.status,
        "scheduled_follow_up_date": enquiry.next_follow_up_date,
    })
    assign_form = EnquiryAssignStaffForm(institution=enquiry.institution, initial={
        "assigned_to": enquiry.assigned_to,
        "next_follow_up_date": enquiry.next_follow_up_date,
    })
    convert_form = ConvertApplicantToStudentForm(institution=enquiry.institution, course=enquiry.course, initial={
        "target_batch": enquiry.batch_interest,
    })

    context = {
        "page_title": f"Enquiry Dossier: {enquiry.enquiry_number} - {enquiry.name}",
        "enquiry": enquiry,
        "follow_ups": enquiry.follow_ups.all(),
        "follow_up_form": follow_up_form,
        "assign_form": assign_form,
        "convert_form": convert_form,
    }
    return render(request, "admissions/admin/enquiries/detail.html", context)


@login_required
def admin_enquiry_followup_view(request, enquiry_number):
    """
    Add a follow-up interaction note, update pipeline status, or schedule next follow-up.
    """
    if request.method != "POST":
        return redirect("admissions:admin_enquiry_detail", enquiry_number=enquiry_number)

    enquiry = get_object_or_404(Enquiry, enquiry_number=enquiry_number)
    inst = getattr(request, "institution", None)
    if inst and enquiry.institution and enquiry.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied: Enquiry belongs to another institution.")

    form = EnquiryFollowUpForm(request.POST)
    if form.is_valid():
        follow_up = form.save(commit=False)
        follow_up.enquiry = enquiry
        follow_up.staff = request.user
        follow_up.old_status = enquiry.status

        new_status = form.cleaned_data.get("new_status")
        if new_status:
            follow_up.new_status = new_status
            enquiry.status = new_status

        sched_date = form.cleaned_data.get("scheduled_follow_up_date")
        if sched_date:
            enquiry.next_follow_up_date = sched_date

        follow_up.save()
        enquiry.save()

        messages.success(request, f"Follow-up interaction recorded for {enquiry.name}.")
    else:
        messages.error(request, "Error saving follow-up note.")

    return redirect("admissions:admin_enquiry_detail", enquiry_number=enquiry.enquiry_number)


@login_required
def admin_enquiry_assign_view(request, enquiry_number):
    """
    Assign or reassign an enquiry to an authorized counselor / staff member.
    """
    if request.method != "POST":
        return redirect("admissions:admin_enquiry_detail", enquiry_number=enquiry_number)

    enquiry = get_object_or_404(Enquiry, enquiry_number=enquiry_number)
    inst = getattr(request, "institution", None)
    if inst and enquiry.institution and enquiry.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied: Enquiry belongs to another institution.")

    form = EnquiryAssignStaffForm(request.POST, institution=enquiry.institution)
    if form.is_valid():
        staff_member = form.cleaned_data["assigned_to"]
        next_date = form.cleaned_data.get("next_follow_up_date")
        note = form.cleaned_data.get("assignment_note", "")

        prev_assignee = enquiry.assigned_to.get_full_name() or enquiry.assigned_to.username if enquiry.assigned_to else "Unassigned"
        enquiry.assigned_to = staff_member
        if next_date:
            enquiry.next_follow_up_date = next_date
        enquiry.save()

        # Log follow up
        log_text = f"Enquiry assigned to {staff_member.get_full_name() or staff_member.username} (was: {prev_assignee})."
        if note:
            log_text += f" Note: {note}"
        EnquiryFollowUp.objects.create(
            enquiry=enquiry,
            staff=request.user,
            contact_mode="other",
            notes=log_text,
            old_status=enquiry.status,
            new_status=enquiry.status,
            scheduled_follow_up_date=next_date,
        )

        messages.success(request, f"Enquiry assigned to {staff_member.get_full_name() or staff_member.username}.")
    else:
        messages.error(request, "Invalid counselor assignment.")

    return redirect("admissions:admin_enquiry_detail", enquiry_number=enquiry.enquiry_number)


@login_required
def admin_enquiry_convert_view(request, enquiry_number):
    """
    Convert an enquiry directly to an active student and enrol into a batch.
    Prevents duplicate user accounts by checking email and linking existing accounts.
    """
    if request.method != "POST":
        return redirect("admissions:admin_enquiry_detail", enquiry_number=enquiry_number)

    enquiry = get_object_or_404(Enquiry, enquiry_number=enquiry_number)
    inst = getattr(request, "institution", None)
    if inst and enquiry.institution and enquiry.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied: Enquiry belongs to another institution.")

    if enquiry.status == EnquiryStatus.CONVERTED and enquiry.converted_student:
        messages.warning(
            request,
            f"Enquiry {enquiry.enquiry_number} was already converted into student {enquiry.converted_student.get_full_name()}."
        )
        return redirect("admissions:admin_enquiry_detail", enquiry_number=enquiry.enquiry_number)

    # 1. Prevent duplicate account: Look up existing user by email
    existing_user = User.objects.filter(email__iexact=enquiry.email.strip()).first()
    if existing_user:
        student_user = existing_user
        if student_user.role == Role.APPLICANT:
            student_user.role = Role.STUDENT
    else:
        # Create new student account
        name_parts = enquiry.name.strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
        username_candidate = enquiry.email.split("@")[0].lower().replace(".", "_")[:20]
        while User.objects.filter(username=username_candidate).exists():
            username_candidate = f"{enquiry.email.split('@')[0][:15]}_{secrets.token_hex(2)}"

        student_user = User.objects.create_user(
            username=username_candidate,
            email=enquiry.email.strip(),
            first_name=first_name,
            last_name=last_name,
            phone_number=enquiry.phone,
            role=Role.STUDENT,
            institution=enquiry.institution,
        )

    # Assign student ID if not set
    if not student_user.student_id:
        year = timezone.now().year
        while True:
            candidate_id = f"STU-{year}-{secrets.token_hex(3).upper()}"
            if not User.objects.filter(student_id=candidate_id).exists():
                student_user.student_id = candidate_id
                break

    if enquiry.target_class and not student_user.grade_level:
        student_user.grade_level = enquiry.target_class
    student_user.save()

    # Ensure active InstitutionMembership
    membership, _ = InstitutionMembership.objects.get_or_create(
        user=student_user,
        institution=enquiry.institution,
        defaults={"role": Role.STUDENT, "is_active": True},
    )
    if membership.role != Role.STUDENT:
        membership.role = Role.STUDENT
        membership.is_active = True
        membership.save()

    # Batch enrolment
    batch_id = request.POST.get("target_batch")
    target_batch = None
    if batch_id:
        target_batch = Batch.objects.filter(id=batch_id, institution=enquiry.institution).first()
    elif enquiry.batch_interest:
        target_batch = enquiry.batch_interest

    roll_number = request.POST.get("roll_number", "").strip() or student_user.student_id
    batch_enrolled = False
    if target_batch:
        try:
            enroll_student_in_batch(
                student=student_user,
                batch=target_batch,
                roll_number=roll_number,
                created_by=request.user,
                notes=f"Converted from lead {enquiry.enquiry_number}",
            )
            batch_enrolled = True
        except ValidationError as e:
            messages.warning(
                request,
                f"Converted to student, but batch enrolment note: {e.message if hasattr(e, 'message') else e}"
            )

    # Update enquiry
    enquiry.status = EnquiryStatus.CONVERTED
    enquiry.converted_student = student_user
    enquiry.converted_at = timezone.now()
    enquiry.save()

    # Follow up log
    EnquiryFollowUp.objects.create(
        enquiry=enquiry,
        staff=request.user,
        contact_mode="other",
        notes=f"Prospect officially converted to Student (ID: {student_user.student_id})"
              + (f" and enrolled in batch '{target_batch.name}'." if batch_enrolled else "."),
        old_status=enquiry.status,
        new_status=EnquiryStatus.CONVERTED,
    )

    messages.success(
        request,
        f"Enquiry {enquiry.enquiry_number} successfully converted to Student ({student_user.get_full_name()})!"
        + (f" Enrolled in {target_batch.name}." if batch_enrolled else "")
    )
    return redirect("admissions:admin_enquiry_detail", enquiry_number=enquiry.enquiry_number)


@login_required
def admin_enquiries_report_view(request):
    """
    Source-wise enquiry, pipeline progression, and conversion analytics report.
    """
    inst = getattr(request, "institution", None)
    active_role = getattr(request, "user_role", None) or getattr(request.user, "role", None)
    if not (request.user.is_superuser or active_role in [Role.ADMIN, Role.TEACHER, Role.ACCOUNTS]):
        raise PermissionDenied("You do not have permission to view CRM reports.")

    base_qs = Enquiry.objects.all()
    if inst:
        base_qs = base_qs.filter(institution=inst)

    total_leads = base_qs.count()
    total_converted = base_qs.filter(status=EnquiryStatus.CONVERTED).count()
    overall_conv_rate = round((total_converted / total_leads * 100), 1) if total_leads > 0 else 0.0

    # Source breakdown
    source_stats = []
    top_source = None
    top_source_count = -1

    for src_code, src_label in EnquirySource.choices:
        src_qs = base_qs.filter(source=src_code)
        count = src_qs.count()
        conv = src_qs.filter(status=EnquiryStatus.CONVERTED).count()
        rate = round((conv / count * 100), 1) if count > 0 else 0.0
        contacted = src_qs.filter(status=EnquiryStatus.CONTACTED).count()
        trial = src_qs.filter(status=EnquiryStatus.TRIAL_CLASS).count()
        follow_up = src_qs.filter(status=EnquiryStatus.FOLLOW_UP_REQUIRED).count()
        not_interested = src_qs.filter(status=EnquiryStatus.NOT_INTERESTED).count()

        if count > top_source_count:
            top_source_count = count
            top_source = src_label

        source_stats.append({
            "code": src_code,
            "label": src_label,
            "count": count,
            "converted": conv,
            "rate": rate,
            "contacted": contacted,
            "trial": trial,
            "follow_up": follow_up,
            "not_interested": not_interested,
            "percentage_of_total": round((count / total_leads * 100), 1) if total_leads > 0 else 0.0,
        })

    # Status distribution
    status_distribution = []
    for st_code, st_label in EnquiryStatus.choices:
        cnt = base_qs.filter(status=st_code).count()
        pct = round((cnt / total_leads * 100), 1) if total_leads > 0 else 0.0
        status_distribution.append({
            "code": st_code,
            "label": st_label,
            "count": cnt,
            "percentage": pct,
        })

    context = {
        "page_title": "Source-wise Enquiry & Conversion Reports",
        "total_leads": total_leads,
        "total_converted": total_converted,
        "overall_conv_rate": overall_conv_rate,
        "top_source": top_source or "N/A",
        "source_stats": source_stats,
        "status_distribution": status_distribution,
    }
    return render(request, "admissions/admin/enquiries/reports.html", context)


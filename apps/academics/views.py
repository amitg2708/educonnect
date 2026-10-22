"""
EduConnect Academics & Subject Teacher Views.
Implements teacher content management, assignment creation & grading,
assessment score entry, publication controls, student submissions,
Q&A doubt clearance, and parent academic tracking.
"""

from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.models import ParentStudentLink, Role, User
from apps.attendance.models import AcademicSession, ClassEnrollment, ClassRoom, TeacherAssignment
from apps.academics.forms import (
    AssessmentForm,
    AssignmentForm,
    AssignmentSubmissionForm,
    BatchEnrollmentForm,
    BatchForm,
    BatchScheduleForm,
    BatchTeacherAssignmentForm,
    BatchTransferForm,
    CourseCatalogueForm,
    StudentDoubtForm,
    StudentScoreForm,
    StudyMaterialForm,
    SubjectForm,
    SubmissionGradingForm,
    TeacherDoubtReplyForm,
)
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
    StudyMaterial,
    Subject,
)
from apps.academics.services import (
    answer_student_doubt,
    check_batch_schedule_conflicts,
    enroll_student_in_batch,
    enter_student_assessment_score,
    grade_assignment_submission,
    is_student_enrolled_in_classroom,
    is_teacher_authorized_for_batch_subject,
    is_teacher_authorized_for_subject,
    promote_waitlisted_student_for_batch,
    publish_assessment_results,
    submit_student_assignment,
    transfer_student_batch,
    validate_batch_enrollment,
)
from apps.core.models import Course
from apps.institutions.models import Branch, Institution, InstitutionMembership


# ==============================================================================
# TEACHER ACADEMIC VIEWS
# ==============================================================================

@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_dashboard(request):
    """
    Overview for subject teachers: assignments, pending grading, doubts, assessments.
    """
    teacher = request.user
    inst = getattr(request, "institution", None)
    if teacher.role == Role.ADMIN:
        assignments_qs = Assignment.objects.filter(institution=inst) if inst else Assignment.objects.all()
        materials_qs = StudyMaterial.objects.filter(institution=inst) if inst else StudyMaterial.objects.all()
        assessments_qs = Assessment.objects.filter(institution=inst) if inst else Assessment.objects.all()
        doubts_qs = StudentDoubt.objects.filter(institution=inst) if inst else StudentDoubt.objects.all()
        teacher_assignments = TeacherAssignment.objects.filter(classroom__institution=inst, is_active=True) if inst else TeacherAssignment.objects.filter(is_active=True)
    else:
        assignments_qs = Assignment.objects.filter(teacher=teacher)
        materials_qs = StudyMaterial.objects.filter(teacher=teacher)
        assessments_qs = Assessment.objects.filter(teacher=teacher)
        doubts_qs = StudentDoubt.objects.filter(assigned_teacher=teacher)
        teacher_assignments = TeacherAssignment.objects.filter(teacher=teacher, is_active=True)
        if inst:
            assignments_qs = assignments_qs.filter(institution=inst)
            materials_qs = materials_qs.filter(institution=inst)
            assessments_qs = assessments_qs.filter(institution=inst)
            doubts_qs = doubts_qs.filter(institution=inst)
            teacher_assignments = teacher_assignments.filter(classroom__institution=inst)

    pending_grading_count = AssignmentSubmission.objects.filter(
        assignment__in=assignments_qs, score__isnull=True
    ).count()

    pending_doubts_count = doubts_qs.filter(is_resolved=False).count()

    context = {
        "teacher_assignments": teacher_assignments,
        "recent_materials": materials_qs[:5],
        "active_assignments": assignments_qs[:5],
        "recent_assessments": assessments_qs[:5],
        "pending_doubts": doubts_qs.filter(is_resolved=False)[:5],
        "pending_grading_count": pending_grading_count,
        "pending_doubts_count": pending_doubts_count,
        "total_materials_count": materials_qs.count(),
        "total_assignments_count": assignments_qs.count(),
    }
    return render(request, "academics/teacher/dashboard.html", context)


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_materials(request):
    """
    Upload and manage study materials and lecture notes.
    """
    teacher = request.user
    inst = getattr(request, "institution", None)
    if request.method == "POST":
        form = StudyMaterialForm(request.POST, request.FILES, teacher=teacher)
        if form.is_valid():
            material = form.save(commit=False)
            material.teacher = teacher
            material.institution = inst or material.classroom.institution
            # Verify subject authorization
            if not is_teacher_authorized_for_subject(teacher, material.classroom, material.subject_name):
                messages.error(
                    request,
                    f"You are not assigned to teach '{material.subject_name}' in '{material.classroom.name}'.",
                )
            else:
                material.save()
                messages.success(request, f"Study material '{material.title}' uploaded successfully.")
                return redirect("academics:teacher_materials")
    else:
        form = StudyMaterialForm(teacher=teacher)

    if teacher.role == Role.ADMIN:
        materials = StudyMaterial.objects.filter(institution=inst) if inst else StudyMaterial.objects.all()
    else:
        materials = StudyMaterial.objects.filter(teacher=teacher)
        if inst:
            materials = materials.filter(institution=inst)

    return render(
        request,
        "academics/teacher/materials.html",
        {"form": form, "materials": materials},
    )


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_delete_material(request, material_id):
    """
    Delete a study material item.
    """
    material = get_object_or_404(StudyMaterial, id=material_id)
    inst = getattr(request, "institution", None)
    if inst and material.institution and material.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to material outside your active institution.")

    if request.user.role != Role.ADMIN and material.teacher != request.user:
        raise PermissionDenied("You can only delete your own study materials.")

    if request.method == "POST":
        title = material.title
        material.delete()
        messages.success(request, f"Study material '{title}' has been removed.")
    return redirect("academics:teacher_materials")


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_assignments(request):
    """
    List and create coursework assignments.
    """
    teacher = request.user
    inst = getattr(request, "institution", None)
    if request.method == "POST":
        form = AssignmentForm(request.POST, request.FILES, teacher=teacher)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.teacher = teacher
            assignment.institution = inst or assignment.classroom.institution
            if not is_teacher_authorized_for_subject(teacher, assignment.classroom, assignment.subject_name):
                messages.error(
                    request,
                    f"You are not assigned to teach '{assignment.subject_name}' in '{assignment.classroom.name}'.",
                )
            else:
                assignment.save()
                messages.success(request, f"Assignment '{assignment.title}' created successfully.")
                return redirect("academics:teacher_assignments")
    else:
        form = AssignmentForm(teacher=teacher)

    if teacher.role == Role.ADMIN:
        assignments = Assignment.objects.filter(institution=inst) if inst else Assignment.objects.all()
    else:
        assignments = Assignment.objects.filter(teacher=teacher)
        if inst:
            assignments = assignments.filter(institution=inst)

    return render(
        request,
        "academics/teacher/assignments.html",
        {"form": form, "assignments": assignments},
    )


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_assignment_submissions(request, assignment_id):
    """
    View all submissions for a particular assignment with grading status.
    """
    assignment = get_object_or_404(Assignment, id=assignment_id)
    if request.user.role != Role.ADMIN and assignment.teacher != request.user:
        raise PermissionDenied("You can only manage submissions for your own assignments.")

    submissions = assignment.submissions.select_related("student").all()
    # Also find enrolled students who haven't submitted yet
    enrolled_student_ids = ClassEnrollment.objects.filter(
        classroom=assignment.classroom, is_active=True
    ).values_list("student_id", flat=True)
    submitted_student_ids = submissions.values_list("student_id", flat=True)
    missing_students = User.objects.filter(id__in=enrolled_student_ids).exclude(id__in=submitted_student_ids)

    return render(
        request,
        "academics/teacher/assignment_submissions.html",
        {
            "assignment": assignment,
            "submissions": submissions,
            "missing_students": missing_students,
        },
    )


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_grade_submission(request, submission_id):
    """
    Grade an individual coursework submission.
    """
    submission = get_object_or_404(
        AssignmentSubmission.objects.select_related("assignment", "student"), id=submission_id
    )
    assignment = submission.assignment

    if request.user.role != Role.ADMIN and assignment.teacher != request.user:
        raise PermissionDenied("You can only grade submissions for your assigned coursework.")

    if request.method == "POST":
        form = SubmissionGradingForm(request.POST, instance=submission)
        if form.is_valid():
            score = form.cleaned_data["score"]
            feedback = form.cleaned_data.get("feedback", "")
            try:
                grade_assignment_submission(submission, request.user, score, feedback)
                messages.success(
                    request,
                    f"Graded submission for {submission.student.get_full_name() or submission.student.username}.",
                )
                return redirect("academics:teacher_assignment_submissions", assignment_id=str(assignment.id))
            except (ValidationError, PermissionDenied) as e:
                messages.error(request, str(e))
    else:
        form = SubmissionGradingForm(instance=submission)

    return render(
        request,
        "academics/teacher/grade_submission.html",
        {"submission": submission, "form": form, "assignment": assignment},
    )


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_assessments(request):
    """
    List and configure academic assessments and tests.
    """
    teacher = request.user
    inst = getattr(request, "institution", None)
    if request.method == "POST":
        form = AssessmentForm(request.POST, teacher=teacher)
        if form.is_valid():
            assessment = form.save(commit=False)
            assessment.teacher = teacher
            assessment.institution = inst or assessment.classroom.institution
            if not is_teacher_authorized_for_subject(teacher, assessment.classroom, assessment.subject_name):
                messages.error(
                    request,
                    f"You are not assigned to teach '{assessment.subject_name}' in '{assessment.classroom.name}'.",
                )
            else:
                assessment.save()
                messages.success(request, f"Assessment '{assessment.title}' created.")
                return redirect("academics:teacher_assessments")
    else:
        form = AssessmentForm(teacher=teacher)

    if teacher.role == Role.ADMIN:
        assessments = Assessment.objects.filter(institution=inst) if inst else Assessment.objects.all()
    else:
        assessments = Assessment.objects.filter(teacher=teacher)
        if inst:
            assessments = assessments.filter(institution=inst)

    return render(
        request,
        "academics/teacher/assessments.html",
        {"form": form, "assessments": assessments},
    )


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_enter_marks(request, assessment_id):
    """
    Enter and update marks for enrolled students in an assessment.
    Marks remain strictly unpublished until authorized publication.
    """
    assessment = get_object_or_404(Assessment.objects.select_related("classroom"), id=assessment_id)
    inst = getattr(request, "institution", None)
    if inst and assessment.institution and assessment.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to assessment outside your active institution.")

    if request.user.role != Role.ADMIN and assessment.teacher != request.user:
        raise PermissionDenied("You can only enter marks for your own assessments.")

    enrollments = (
        ClassEnrollment.objects.filter(classroom=assessment.classroom, is_active=True)
        .select_related("student")
        .order_by("roll_number", "student__username")
    )
    existing_scores = {s.student_id: s for s in assessment.scores.all()}

    if request.method == "POST":
        student_id = request.POST.get("student_id")
        marks_raw = request.POST.get("marks_obtained")
        remarks = request.POST.get("teacher_remarks", "")

        if student_id and marks_raw is not None:
            student = get_object_or_404(User, id=student_id, role=Role.STUDENT)
            try:
                marks_dec = Decimal(str(marks_raw))
                enter_student_assessment_score(assessment, student, marks_dec, request.user, remarks)
                messages.success(request, f"Marks updated for {student.get_full_name() or student.username}.")
                return redirect("academics:teacher_enter_marks", assessment_id=str(assessment.id))
            except (ValidationError, PermissionDenied, ValueError) as e:
                messages.error(request, f"Error saving score: {e}")

    student_roster = []
    for enr in enrollments:
        score_obj = existing_scores.get(enr.student_id)
        student_roster.append(
            {
                "student": enr.student,
                "roll_number": enr.roll_number,
                "score": score_obj,
            }
        )

    return render(
        request,
        "academics/teacher/enter_marks.html",
        {
            "assessment": assessment,
            "student_roster": student_roster,
        },
    )


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_publish_assessment(request, assessment_id):
    """
    Publish assessment results, making them visible to students and parents.
    """
    assessment = get_object_or_404(Assessment, id=assessment_id)
    inst = getattr(request, "institution", None)
    if inst and assessment.institution and assessment.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to assessment outside your active institution.")

    if request.user.role != Role.ADMIN and assessment.teacher != request.user:
        raise PermissionDenied("You can only publish results for your own assessments.")

    if request.method == "POST":
        try:
            publish_assessment_results(assessment, request.user)
            messages.success(request, f"Results for '{assessment.title}' are now published and visible to students/parents.")
        except (ValidationError, PermissionDenied) as e:
            messages.error(request, str(e))

    return redirect("academics:teacher_assessments")


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_doubts(request):
    """
    Inbox of student academic questions assigned to this teacher.
    """
    teacher = request.user
    inst = getattr(request, "institution", None)
    if teacher.role == Role.ADMIN:
        doubts = StudentDoubt.objects.filter(institution=inst) if inst else StudentDoubt.objects.all()
    else:
        doubts = StudentDoubt.objects.filter(assigned_teacher=teacher)
        if inst:
            doubts = doubts.filter(institution=inst)

    return render(
        request,
        "academics/teacher/doubts.html",
        {"doubts": doubts},
    )


@login_required
@role_required(Role.TEACHER, Role.ADMIN)
def teacher_answer_doubt_view(request, doubt_id):
    """
    Answer an individual student doubt.
    """
    doubt = get_object_or_404(StudentDoubt, id=doubt_id)
    if request.user.role != Role.ADMIN and doubt.assigned_teacher != request.user:
        raise PermissionDenied("You can only answer doubts assigned to you.")

    if request.method == "POST":
        form = TeacherDoubtReplyForm(request.POST)
        if form.is_valid():
            answer = form.cleaned_data["answer_text"]
            try:
                answer_student_doubt(doubt, answer, request.user)
                messages.success(request, "Doubt response submitted successfully.")
                return redirect("academics:teacher_doubts")
            except (ValidationError, PermissionDenied) as e:
                messages.error(request, str(e))
    else:
        form = TeacherDoubtReplyForm(initial={"answer_text": doubt.answer_text})

    return render(
        request,
        "academics/teacher/answer_doubt.html",
        {"doubt": doubt, "form": form},
    )


# ==============================================================================
# STUDENT ACADEMIC VIEWS
# ==============================================================================

@login_required
@role_required(Role.STUDENT)
def student_dashboard(request):
    """
    Academic dashboard for enrolled students: study materials, assignments, published marks, doubts.
    """
    student = request.user
    enrolled_classroom_ids = ClassEnrollment.objects.filter(
        student=student, is_active=True
    ).values_list("classroom_id", flat=True)

    materials = StudyMaterial.objects.filter(classroom_id__in=enrolled_classroom_ids)[:6]
    assignments = Assignment.objects.filter(
        classroom_id__in=enrolled_classroom_ids, is_published=True
    ).order_by("due_datetime")[:6]

    # Student submissions
    submissions = {s.assignment_id: s for s in AssignmentSubmission.objects.filter(student=student)}
    assignment_list = [{"assignment": a, "submission": submissions.get(a.id)} for a in assignments]

    # Published assessment scores ONLY!
    scores = (
        StudentAssessmentScore.objects.filter(student=student, assessment__is_published=True)
        .select_related("assessment")
        .order_by("-assessment__date_conducted")[:6]
    )

    doubts = StudentDoubt.objects.filter(student=student)[:5]

    context = {
        "materials": materials,
        "assignment_list": assignment_list,
        "scores": scores,
        "doubts": doubts,
    }
    return render(request, "academics/student/dashboard.html", context)


@login_required
@role_required(Role.STUDENT)
def student_materials(request):
    """
    Browse lecture notes and study resources for enrolled classes.
    """
    student = request.user
    enrolled_classroom_ids = ClassEnrollment.objects.filter(
        student=student, is_active=True
    ).values_list("classroom_id", flat=True)

    materials = StudyMaterial.objects.filter(classroom_id__in=enrolled_classroom_ids).select_related(
        "classroom", "teacher"
    )
    subject = request.GET.get("subject")
    if subject:
        materials = materials.filter(subject_name__iexact=subject)

    return render(
        request,
        "academics/student/materials.html",
        {"materials": materials, "selected_subject": subject},
    )


@login_required
@role_required(Role.STUDENT)
def student_assignments(request):
    """
    List coursework assignments, deadlines, submission status, and received grades.
    """
    student = request.user
    enrolled_classroom_ids = ClassEnrollment.objects.filter(
        student=student, is_active=True
    ).values_list("classroom_id", flat=True)

    assignments = Assignment.objects.filter(
        classroom_id__in=enrolled_classroom_ids, is_published=True
    ).select_related("classroom", "teacher")

    submissions = {s.assignment_id: s for s in AssignmentSubmission.objects.filter(student=student)}

    assignment_list = []
    for a in assignments:
        assignment_list.append(
            {
                "assignment": a,
                "submission": submissions.get(a.id),
            }
        )

    return render(
        request,
        "academics/student/assignments.html",
        {"assignment_list": assignment_list},
    )


@login_required
@role_required(Role.STUDENT)
def student_submit_assignment_view(request, assignment_id):
    """
    Submit completed coursework or homework file.
    """
    student = request.user
    assignment = get_object_or_404(Assignment, id=assignment_id, is_published=True)

    if not is_student_enrolled_in_classroom(student, assignment.classroom):
        raise PermissionDenied("You are not enrolled in the classroom for this assignment.")

    existing_submission = AssignmentSubmission.objects.filter(assignment=assignment, student=student).first()

    if request.method == "POST":
        form = AssignmentSubmissionForm(request.POST, request.FILES, instance=existing_submission)
        if form.is_valid():
            try:
                sub_file = request.FILES["submission_file"]
                notes = form.cleaned_data.get("notes", "")
                submit_student_assignment(assignment, student, sub_file, notes)
                messages.success(request, f"Coursework for '{assignment.title}' submitted successfully.")
                return redirect("academics:student_assignments")
            except (ValidationError, PermissionDenied) as e:
                messages.error(request, str(e))
    else:
        form = AssignmentSubmissionForm(instance=existing_submission)

    return render(
        request,
        "academics/student/submit_assignment.html",
        {
            "assignment": assignment,
            "form": form,
            "existing_submission": existing_submission,
        },
    )


@login_required
@role_required(Role.STUDENT)
def student_results(request):
    """
    View published assessment results.
    Strictly excludes confidential unpublished tests!
    """
    student = request.user
    scores = (
        StudentAssessmentScore.objects.filter(
            student=student,
            assessment__is_published=True,
        )
        .select_related("assessment", "assessment__classroom")
        .order_by("-assessment__date_conducted")
    )

    return render(
        request,
        "academics/student/results.html",
        {"scores": scores},
    )


@login_required
@role_required(Role.STUDENT)
def student_doubts(request):
    """
    Ask and view academic doubts submitted to faculty.
    """
    student = request.user
    if request.method == "POST":
        form = StudentDoubtForm(request.POST, student=student)
        if form.is_valid():
            doubt = form.save(commit=False)
            doubt.student = student
            # Verify student enrollment
            if not is_student_enrolled_in_classroom(student, doubt.classroom):
                messages.error(request, "You are not enrolled in this classroom.")
            else:
                doubt.save()
                messages.success(request, f"Your question '{doubt.question_title}' has been sent to your teacher.")
                return redirect("academics:student_doubts")
    else:
        form = StudentDoubtForm(student=student)

    doubts = StudentDoubt.objects.filter(student=student).select_related("assigned_teacher", "classroom")
    return render(
        request,
        "academics/student/doubts.html",
        {"form": form, "doubts": doubts},
    )


# ==============================================================================
# PARENT ACADEMIC VIEWS
# ==============================================================================

@login_required
@role_required(Role.PARENT)
def parent_child_academics(request, student_id=None):
    """
    View academic performance, assignments, and study materials for authorized children only.
    Confidential unpublished assessment marks are strictly hidden.
    """
    parent = request.user
    inst = getattr(request, "institution", None)
    children_links = ParentStudentLink.objects.filter(parent=parent, is_authorized=True).select_related("student")
    if inst:
        children_links = children_links.filter(institution=inst)
    if not children_links.exists():
        messages.warning(request, "No linked students found for your parent profile at this institution.")
        return render(request, "academics/parent/child_academics.html", {"children_links": []})

    if student_id:
        active_link = get_object_or_404(children_links, student_id=student_id)
        selected_student = active_link.student
    else:
        selected_student = children_links.first().student

    enrolled_classroom_ids = ClassEnrollment.objects.filter(
        student=selected_student, is_active=True
    ).values_list("classroom_id", flat=True)

    materials = StudyMaterial.objects.filter(classroom_id__in=enrolled_classroom_ids)[:8]
    assignments = Assignment.objects.filter(
        classroom_id__in=enrolled_classroom_ids, is_published=True
    ).order_by("-due_datetime")[:8]
    submissions = {s.assignment_id: s for s in AssignmentSubmission.objects.filter(student=selected_student)}

    scores = (
        StudentAssessmentScore.objects.filter(
            student=selected_student,
            assessment__is_published=True,
        )
        .select_related("assessment", "assessment__classroom")
        .order_by("-assessment__date_conducted")
    )

    context = {
        "children_links": children_links,
        "selected_student": selected_student,
        "materials": materials,
        "assignments": assignments,
        "submissions": submissions,
        "scores": scores,
    }
    return render(request, "academics/parent/child_academics.html", context)


# ==============================================================================
# ADMIN ACADEMIC VIEWS
# ==============================================================================

@login_required
@role_required(Role.ADMIN)
def admin_academics_overview(request):
    """
    Admin institutional academic oversight: total materials, assignments, assessments, and publication audits.
    """
    inst = getattr(request, "institution", None)
    assessments = Assessment.objects.select_related("classroom", "teacher").all()
    assignments = Assignment.objects.select_related("classroom", "teacher").all()
    materials = StudyMaterial.objects.select_related("classroom", "teacher").all()
    submissions_qs = AssignmentSubmission.objects.all()

    if inst:
        assessments = assessments.filter(institution=inst)
        assignments = assignments.filter(institution=inst)
        materials = materials.filter(institution=inst)
        submissions_qs = submissions_qs.filter(assignment__institution=inst)

    total_submissions = submissions_qs.count()
    total_graded = submissions_qs.filter(score__isnull=False).count()

    context = {
        "assessments": assessments,
        "assignments": assignments,
        "materials": materials,
        "total_submissions": total_submissions,
        "total_graded": total_graded,
    }
    return render(request, "academics/admin/overview.html", context)


# ==============================================================================
# COACHING BATCHES, COURSES & ENROLMENT DESK (TASK 2)
# ==============================================================================


def get_active_institution(request):
    """
    Resolves the active tenant coaching institute context.
    Priority: request.institution -> user.institution -> user membership -> first active.
    """
    inst = getattr(request, "institution", None)
    if not inst and request.user.is_authenticated:
        inst = getattr(request.user, "institution", None)
        if not inst:
            membership = InstitutionMembership.objects.filter(user=request.user, is_active=True).first()
            if membership:
                inst = membership.institution
    if not inst:
        inst = Institution.objects.filter(is_active=True).first()
    return inst


# --- Course Catalogue ---

@login_required
@role_required(Role.ADMIN)
def admin_courses(request):
    """
    Course catalogue administration with search, multi-category filters, and pagination.
    """
    inst = get_active_institution(request)
    courses = Course.objects.filter(Q(institution=inst) | Q(institution__isnull=True))

    search_query = request.GET.get("q", "").strip()
    if search_query:
        courses = courses.filter(
            Q(title__icontains=search_query)
            | Q(code__icontains=search_query)
            | Q(board__icontains=search_query)
            | Q(examination_scheme__icontains=search_query)
            | Q(target_class__icontains=search_query)
        )

    category = request.GET.get("category", "").strip()
    if category:
        courses = courses.filter(category=category)

    stream = request.GET.get("stream", "").strip()
    if stream:
        courses = courses.filter(stream=stream)

    status = request.GET.get("status", "").strip()
    if status == "active":
        courses = courses.filter(is_active=True)
    elif status == "inactive":
        courses = courses.filter(is_active=False)

    paginator = Paginator(courses.order_by("-created_at"), 10)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    context = {
        "institution": inst,
        "page_obj": page_obj,
        "search_query": search_query,
        "selected_category": category,
        "selected_stream": stream,
        "selected_status": status,
        "category_choices": Course.Category.choices,
        "stream_choices": Course.Stream.choices,
        "total_courses": courses.count(),
    }
    return render(request, "academics/admin/courses/list.html", context)


@login_required
@role_required(Role.ADMIN)
def admin_course_create(request):
    """
    Create a new course offering for the institute catalogue.
    """
    inst = get_active_institution(request)
    if request.method == "POST":
        form = CourseCatalogueForm(request.POST, request.FILES, institution=inst)
        if form.is_valid():
            course = form.save()
            messages.success(request, f"Course '{course.title}' [{course.code}] added to catalogue.")
            return redirect("academics:admin_courses")
    else:
        form = CourseCatalogueForm(institution=inst)

    return render(
        request,
        "academics/admin/courses/form.html",
        {"form": form, "institution": inst, "is_create": True},
    )


@login_required
@role_required(Role.ADMIN)
def admin_course_edit(request, course_id):
    """
    Update an existing course curriculum and fees.
    """
    inst = get_active_institution(request)
    course = get_object_or_404(Course, id=course_id)
    if course.institution and inst and course.institution_id != inst.id and not request.user.is_superuser:
        raise PermissionDenied("You do not have permission to modify courses belonging to another institute.")

    if request.method == "POST":
        form = CourseCatalogueForm(request.POST, request.FILES, instance=course, institution=inst)
        if form.is_valid():
            form.save()
            messages.success(request, f"Course '{course.title}' updated successfully.")
            return redirect("academics:admin_courses")
    else:
        form = CourseCatalogueForm(instance=course, institution=inst)

    return render(
        request,
        "academics/admin/courses/form.html",
        {"form": form, "course": course, "institution": inst, "is_create": False},
    )


# --- Subjects ---

@login_required
@role_required(Role.ADMIN)
def admin_subjects(request):
    """
    Subject and discipline configuration for the coaching institute.
    """
    inst = get_active_institution(request)
    subjects = Subject.objects.filter(Q(institution=inst) | Q(institution__isnull=True)).order_by("name")

    search_query = request.GET.get("q", "").strip()
    if search_query:
        subjects = subjects.filter(Q(name__icontains=search_query) | Q(code__icontains=search_query))

    form = SubjectForm(institution=inst)
    if request.method == "POST":
        form = SubjectForm(request.POST, institution=inst)
        if form.is_valid():
            subject = form.save()
            messages.success(request, f"Subject '{subject.name}' [{subject.code}] configured successfully.")
            return redirect("academics:admin_subjects")
        else:
            messages.error(request, "Failed to configure subject. Please check the form errors below.")

    context = {
        "institution": inst,
        "subjects": subjects,
        "form": form,
        "search_query": search_query,
    }
    return render(request, "academics/admin/subjects/list.html", context)


# --- Coaching Batches ---

@login_required
@role_required(Role.ADMIN)
def admin_batches(request):
    """
    Batches desk: filter cohorts by branch, course, status, stream, with capacity meters.
    """
    inst = get_active_institution(request)
    batches = Batch.objects.filter(institution=inst).select_related(
        "course", "branch", "academic_session", "classroom"
    )

    search_query = request.GET.get("q", "").strip()
    if search_query:
        batches = batches.filter(
            Q(name__icontains=search_query)
            | Q(code__icontains=search_query)
            | Q(target_class__icontains=search_query)
            | Q(stream__icontains=search_query)
            | Q(board__icontains=search_query)
        )

    branch_id = request.GET.get("branch", "").strip()
    if branch_id:
        batches = batches.filter(branch_id=branch_id)

    status = request.GET.get("status", "").strip()
    if status:
        batches = batches.filter(status=status)

    course_id = request.GET.get("course", "").strip()
    if course_id:
        batches = batches.filter(course_id=course_id)

    paginator = Paginator(batches.order_by("-start_date", "name"), 12)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    branches = Branch.objects.filter(institution=inst, is_active=True) if inst else Branch.objects.none()
    courses = Course.objects.filter(Q(institution=inst) | Q(institution__isnull=True), is_active=True)

    context = {
        "institution": inst,
        "page_obj": page_obj,
        "branches": branches,
        "courses": courses,
        "search_query": search_query,
        "selected_branch": branch_id,
        "selected_status": status,
        "selected_course": course_id,
        "status_choices": Batch.Status.choices,
        "total_batches": batches.count(),
    }
    return render(request, "academics/admin/batches/list.html", context)


@login_required
@role_required(Role.ADMIN)
def admin_batch_create(request):
    """
    Creates a new coaching batch with capacity, waitlist, session, and campus branch constraints.
    """
    inst = get_active_institution(request)
    if request.method == "POST":
        form = BatchForm(request.POST, institution=inst)
        if form.is_valid():
            try:
                batch = form.save()
                messages.success(request, f"Coaching Batch '{batch.name}' [{batch.code}] created successfully.")
                return redirect("academics:admin_batch_detail", batch_id=batch.id)
            except ValidationError as err:
                for field, errs in getattr(err, "message_dict", {}).items():
                    for e in errs:
                        form.add_error(field, e)
                if not getattr(err, "message_dict", None):
                    form.add_error(None, err)
    else:
        form = BatchForm(institution=inst)

    return render(
        request,
        "academics/admin/batches/form.html",
        {"form": form, "institution": inst, "is_create": True},
    )


@login_required
@role_required(Role.ADMIN)
def admin_batch_edit(request, batch_id):
    """
    Update batch operational details, dates, or capacity.
    """
    inst = get_active_institution(request)
    batch = get_object_or_404(Batch, id=batch_id, institution=inst)

    if request.method == "POST":
        form = BatchForm(request.POST, instance=batch, institution=inst)
        if form.is_valid():
            try:
                form.save()
                messages.success(request, f"Batch '{batch.name}' updated successfully.")
                return redirect("academics:admin_batch_detail", batch_id=batch.id)
            except ValidationError as err:
                form.add_error(None, err)
    else:
        form = BatchForm(instance=batch, institution=inst)

    return render(
        request,
        "academics/admin/batches/form.html",
        {"form": form, "batch": batch, "institution": inst, "is_create": False},
    )


@login_required
@role_required(Role.ADMIN)
def admin_batch_detail(request, batch_id):
    """
    Batch operational command center:
    - Roster of active, waitlisted, and transferred students.
    - Weekly timetable schedule cards.
    - Assigned subject teachers and lead mentors.
    - Quick enrolment, transfer, and schedule slot modals.
    """
    inst = get_active_institution(request)
    batch = get_object_or_404(
        Batch.objects.select_related("course", "branch", "academic_session", "classroom"),
        id=batch_id,
        institution=inst,
    )

    enrollments = batch.batch_enrollments.select_related("student", "created_by").order_by(
        "status", "waitlist_position", "roll_number", "-enrolled_at"
    )
    active_enrollments = [e for e in enrollments if e.status == BatchEnrollment.Status.ACTIVE]
    waitlisted_enrollments = [e for e in enrollments if e.status == BatchEnrollment.Status.WAITLISTED]
    history_enrollments = [e for e in enrollments if e.status not in (BatchEnrollment.Status.ACTIVE, BatchEnrollment.Status.WAITLISTED)]

    schedules = batch.schedules.select_related("subject", "teacher").order_by("day_of_week", "start_time")
    teacher_assignments = batch.teacher_assignments.select_related("teacher", "subject").order_by("subject__name")

    schedule_form = BatchScheduleForm(batch=batch)
    teacher_form = BatchTeacherAssignmentForm(batch=batch)
    enrollment_form = BatchEnrollmentForm(batch=batch)

    context = {
        "institution": inst,
        "batch": batch,
        "enrollments": enrollments,
        "active_enrollments": active_enrollments,
        "waitlisted_enrollments": waitlisted_enrollments,
        "history_enrollments": history_enrollments,
        "schedules": schedules,
        "teacher_assignments": teacher_assignments,
        "schedule_form": schedule_form,
        "teacher_form": teacher_form,
        "enrollment_form": enrollment_form,
    }
    return render(request, "academics/admin/batches/detail.html", context)


@login_required
@role_required(Role.ADMIN)
def admin_batch_schedule_add(request, batch_id):
    """
    Adds a weekly timetable slot for a coaching batch.
    Enforces time overlap validations.
    """
    inst = get_active_institution(request)
    batch = get_object_or_404(Batch, id=batch_id, institution=inst)

    if request.method == "POST":
        form = BatchScheduleForm(request.POST, batch=batch)
        if form.is_valid():
            try:
                schedule = form.save(commit=False)
                schedule.batch = batch

                # Check if batch has an overlapping schedule slot
                for existing in batch.schedules.filter(day_of_week=schedule.day_of_week):
                    if existing.conflicts_with(schedule):
                        raise ValidationError(
                            f"Time slot conflicts with existing slot: {existing.get_day_of_week_display()} "
                            f"{existing.start_time.strftime('%H:%M')}-{existing.end_time.strftime('%H:%M')}."
                        )

                schedule.save()
                messages.success(
                    request,
                    f"Schedule slot added: {schedule.get_day_of_week_display()} {schedule.start_time.strftime('%H:%M')}-{schedule.end_time.strftime('%H:%M')}."
                )
            except ValidationError as err:
                msg = "; ".join(err.messages) if hasattr(err, "messages") else str(err)
                messages.error(request, f"Cannot add schedule slot: {msg}")
        else:
            messages.error(request, "Invalid schedule details submitted.")

    return redirect("academics:admin_batch_detail", batch_id=batch.id)


@login_required
@role_required(Role.ADMIN)
def admin_batch_schedule_delete(request, batch_id, schedule_id):
    """
    Deletes a timetable slot.
    """
    inst = get_active_institution(request)
    batch = get_object_or_404(Batch, id=batch_id, institution=inst)
    schedule = get_object_or_404(BatchSchedule, id=schedule_id, batch=batch)

    if request.method == "POST":
        schedule.delete()
        messages.success(request, "Schedule slot removed.")

    return redirect("academics:admin_batch_detail", batch_id=batch.id)


@login_required
@role_required(Role.ADMIN)
def admin_batch_assign_teacher(request, batch_id):
    """
    Assigns an authorized Subject Teacher to a batch subject.
    """
    inst = get_active_institution(request)
    batch = get_object_or_404(Batch, id=batch_id, institution=inst)

    if request.method == "POST":
        form = BatchTeacherAssignmentForm(request.POST, batch=batch)
        if form.is_valid():
            try:
                assignment = form.save(commit=False)
                assignment.batch = batch
                assignment.save()
                messages.success(
                    request,
                    f"Faculty {assignment.teacher.get_full_name()} assigned to {assignment.subject.name} in {batch.name}."
                )
            except ValidationError as err:
                msg = "; ".join(err.messages) if hasattr(err, "messages") else str(err)
                messages.error(request, f"Assignment rejected: {msg}")
        else:
            messages.error(request, "Invalid teacher assignment data.")

    return redirect("academics:admin_batch_detail", batch_id=batch.id)


@login_required
@role_required(Role.ADMIN)
def admin_batch_unassign_teacher(request, batch_id, assignment_id):
    """
    Removes faculty assignment from a batch subject.
    """
    inst = get_active_institution(request)
    batch = get_object_or_404(Batch, id=batch_id, institution=inst)
    assignment = get_object_or_404(BatchTeacherAssignment, id=assignment_id, batch=batch)

    if request.method == "POST":
        teacher_name = assignment.teacher.get_full_name() or assignment.teacher.username
        subject_name = assignment.subject.name
        assignment.delete()
        messages.success(request, f"Faculty {teacher_name} unassigned from {subject_name}.")

    return redirect("academics:admin_batch_detail", batch_id=batch.id)


# --- Student Enrolments & Transfers ---

@login_required
@role_required(Role.ADMIN)
def admin_enrollments(request):
    """
    All student enrolments across batches in the coaching institute.
    Supports search, filters (batch, status), and batch transfer workflow.
    """
    inst = get_active_institution(request)
    enrollments = BatchEnrollment.objects.filter(institution=inst).select_related(
        "student", "batch", "batch__course", "batch__branch", "transferred_to"
    )

    search_query = request.GET.get("q", "").strip()
    if search_query:
        enrollments = enrollments.filter(
            Q(student__username__icontains=search_query)
            | Q(student__first_name__icontains=search_query)
            | Q(student__last_name__icontains=search_query)
            | Q(enrollment_number__icontains=search_query)
            | Q(roll_number__icontains=search_query)
            | Q(batch__name__icontains=search_query)
        )

    batch_id = request.GET.get("batch", "").strip()
    if batch_id:
        enrollments = enrollments.filter(batch_id=batch_id)

    status = request.GET.get("status", "").strip()
    if status:
        enrollments = enrollments.filter(status=status)

    paginator = Paginator(enrollments.order_by("-enrolled_at"), 15)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    batches = Batch.objects.filter(institution=inst, status__in=[Batch.Status.UPCOMING, Batch.Status.ONGOING])

    context = {
        "institution": inst,
        "page_obj": page_obj,
        "batches": batches,
        "search_query": search_query,
        "selected_batch": batch_id,
        "selected_status": status,
        "status_choices": BatchEnrollment.Status.choices,
        "total_enrollments": enrollments.count(),
    }
    return render(request, "academics/admin/enrollments/list.html", context)


@login_required
@role_required(Role.ADMIN)
def admin_enrollment_create(request):
    """
    Direct enrolment endpoint to enrol a student into any institute batch.
    Validates capacity, duplicate active enrolments, and schedule clashes.
    """
    inst = get_active_institution(request)
    batch_id = request.GET.get("batch") or request.POST.get("batch")
    selected_batch = get_object_or_404(Batch, id=batch_id, institution=inst) if batch_id else None

    if request.method == "POST":
        batch_id_post = request.POST.get("batch")
        batch = get_object_or_404(Batch, id=batch_id_post, institution=inst)
        form = BatchEnrollmentForm(request.POST, batch=batch)
        if form.is_valid():
            student = form.cleaned_data["student"]
            roll_number = form.cleaned_data.get("roll_number", "")
            start_date = form.cleaned_data.get("start_date")
            notes = form.cleaned_data.get("notes", "")
            force_waitlist = form.cleaned_data.get("force_waitlist", False)

            try:
                enrollment = enroll_student_in_batch(
                    student=student,
                    batch=batch,
                    created_by=request.user,
                    roll_number=roll_number,
                    start_date=start_date,
                    notes=notes,
                    force_waitlist=force_waitlist,
                )
                if enrollment.status == BatchEnrollment.Status.WAITLISTED:
                    messages.warning(
                        request,
                        f"Batch is at capacity. Student {student.get_full_name()} placed on waitlist (Position #{enrollment.waitlist_position})."
                    )
                else:
                    messages.success(
                        request,
                        f"Student {student.get_full_name()} successfully enrolled in '{batch.name}' (Roll #{enrollment.roll_number or enrollment.enrollment_number})."
                    )
                return redirect("academics:admin_batch_detail", batch_id=batch.id)
            except ValidationError as err:
                msg = "; ".join(err.messages) if hasattr(err, "messages") else str(err)
                messages.error(request, f"Enrolment rejected: {msg}")
        else:
            messages.error(request, "Invalid enrolment submission. Please check the fields.")
    else:
        form = BatchEnrollmentForm(batch=selected_batch) if selected_batch else None

    all_batches = Batch.objects.filter(institution=inst, status__in=[Batch.Status.UPCOMING, Batch.Status.ONGOING])

    return render(
        request,
        "academics/admin/enrollments/form.html",
        {
            "form": form,
            "institution": inst,
            "selected_batch": selected_batch,
            "all_batches": all_batches,
        },
    )


@login_required
@role_required(Role.ADMIN)
def admin_enrollment_transfer(request, enrollment_id):
    """
    Transfers an enrolled student from one batch to another within the institute:
    - Validates target batch availability and schedule conflicts.
    - Marks source enrolment as TRANSFERRED.
    - Creates target enrolment.
    - Automatically promotes next waitlisted student in the source batch.
    """
    inst = get_active_institution(request)
    enrollment = get_object_or_404(
        BatchEnrollment.objects.select_related("batch", "student", "institution"),
        id=enrollment_id,
        institution=inst,
    )

    if request.method == "POST":
        target_batch_id = request.POST.get("target_batch")
        reason = request.POST.get("reason", "").strip()
        target_batch = get_object_or_404(Batch, id=target_batch_id, institution=inst)

        try:
            old_enr, new_enr = transfer_student_batch(
                enrollment=enrollment,
                target_batch=target_batch,
                reason=reason,
                transferred_by=request.user,
            )
            messages.success(
                request,
                f"Student {enrollment.student.get_full_name()} successfully transferred to '{target_batch.name}' (Status: {new_enr.get_status_display()})."
            )
        except ValidationError as err:
            msg = "; ".join(err.messages) if hasattr(err, "messages") else str(err)
            messages.error(request, f"Transfer rejected: {msg}")

        next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
        if next_url:
            return redirect(next_url)
        return redirect("academics:admin_batch_detail", batch_id=enrollment.batch_id)

    form = BatchTransferForm(current_enrollment=enrollment)
    return render(
        request,
        "academics/admin/enrollments/transfer.html",
        {"enrollment": enrollment, "form": form, "institution": inst},
    )


@login_required
@role_required(Role.ADMIN)
def admin_enrollment_status_update(request, enrollment_id):
    """
    Updates enrollment status (e.g., dropping or completing a student).
    If an active seat is vacated, promotes the waitlist immediately.
    """
    inst = get_active_institution(request)
    enrollment = get_object_or_404(BatchEnrollment, id=enrollment_id, institution=inst)

    if request.method == "POST":
        new_status = request.POST.get("status")
        if new_status in BatchEnrollment.Status.values:
            was_active = enrollment.status == BatchEnrollment.Status.ACTIVE
            enrollment.status = new_status
            if new_status in [BatchEnrollment.Status.DROPPED, BatchEnrollment.Status.COMPLETED]:
                enrollment.end_date = timezone.now().date()
            enrollment.save()

            if was_active and new_status in [BatchEnrollment.Status.DROPPED, BatchEnrollment.Status.COMPLETED]:
                promoted = promote_waitlisted_student_for_batch(enrollment.batch)
                if promoted:
                    messages.info(
                        request,
                        f"Waitlisted student {promoted.student.get_full_name()} has been automatically promoted to Active seat."
                    )

            messages.success(request, f"Enrolment status updated to {enrollment.get_status_display()}.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER")
    if next_url:
        return redirect(next_url)
    return redirect("academics:admin_batch_detail", batch_id=enrollment.batch_id)


# --- Student & Parent Coaching Portals ---

@login_required
@role_required(Role.STUDENT)
def student_my_batches(request):
    """
    Student portal showing all coaching batches the student is enrolled in,
    weekly timetable schedules, instructors, and batch announcements.
    A student has one account even when enrolled in multiple courses or batches.
    """
    student = request.user
    enrollments = student.coaching_batch_enrollments.select_related(
        "batch", "batch__course", "batch__branch", "batch__classroom", "institution"
    ).prefetch_related("batch__schedules", "batch__teacher_assignments").order_by("-enrolled_at")

    active_batches = [e for e in enrollments if e.status == BatchEnrollment.Status.ACTIVE]
    waitlisted_batches = [e for e in enrollments if e.status == BatchEnrollment.Status.WAITLISTED]
    completed_batches = [e for e in enrollments if e.status in (BatchEnrollment.Status.COMPLETED, BatchEnrollment.Status.TRANSFERRED, BatchEnrollment.Status.DROPPED)]

    context = {
        "student": student,
        "active_batches": active_batches,
        "waitlisted_batches": waitlisted_batches,
        "completed_batches": completed_batches,
    }
    return render(request, "academics/student/my_batches.html", context)


@login_required
@role_required(Role.PARENT)
def parent_child_batches(request, student_id=None):
    """
    Parent portal showing enrolled coaching cohorts, schedules, faculty,
    and seat status for their linked wards.
    """
    parent = request.user
    inst = getattr(request, "institution", None)
    children_links = ParentStudentLink.objects.filter(parent=parent, is_authorized=True).select_related("student")
    if inst:
        children_links = children_links.filter(institution=inst)

    selected_student = None
    if student_id:
        selected_student = get_object_or_404(User, id=student_id, role=Role.STUDENT)
    elif children_links.exists():
        selected_student = children_links.first().student

    enrollments = []
    if selected_student:
        enrollments = selected_student.coaching_batch_enrollments.select_related(
            "batch", "batch__course", "batch__branch", "institution"
        ).prefetch_related("batch__schedules", "batch__teacher_assignments").order_by("-enrolled_at")

    context = {
        "children_links": children_links,
        "selected_student": selected_student,
        "enrollments": enrollments,
    }
    return render(request, "academics/parent/child_batches.html", context)


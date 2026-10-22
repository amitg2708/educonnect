"""
URL routing for EduConnect Academics & Subject Teacher module.
"""

from django.urls import path
from apps.academics import views

app_name = "academics"

urlpatterns = [
    # Teacher desk
    path("teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("teacher/materials/", views.teacher_materials, name="teacher_materials"),
    path("teacher/materials/<str:material_id>/delete/", views.teacher_delete_material, name="teacher_delete_material"),
    path("teacher/assignments/", views.teacher_assignments, name="teacher_assignments"),
    path(
        "teacher/assignments/<str:assignment_id>/submissions/",
        views.teacher_assignment_submissions,
        name="teacher_assignment_submissions",
    ),
    path(
        "teacher/submissions/<str:submission_id>/grade/",
        views.teacher_grade_submission,
        name="teacher_grade_submission",
    ),
    path("teacher/assessments/", views.teacher_assessments, name="teacher_assessments"),
    path(
        "teacher/assessments/<str:assessment_id>/marks/",
        views.teacher_enter_marks,
        name="teacher_enter_marks",
    ),
    path(
        "teacher/assessments/<str:assessment_id>/publish/",
        views.teacher_publish_assessment,
        name="teacher_publish_assessment",
    ),
    path("teacher/doubts/", views.teacher_doubts, name="teacher_doubts"),
    path("teacher/doubts/<str:doubt_id>/answer/", views.teacher_answer_doubt_view, name="teacher_answer_doubt"),

    # Student desk
    path("student/", views.student_dashboard, name="student_dashboard"),
    path("student/materials/", views.student_materials, name="student_materials"),
    path("student/assignments/", views.student_assignments, name="student_assignments"),
    path(
        "student/assignments/<str:assignment_id>/submit/",
        views.student_submit_assignment_view,
        name="student_submit_assignment",
    ),
    path("student/results/", views.student_results, name="student_results"),
    path("student/doubts/", views.student_doubts, name="student_doubts"),

    # Parent desk
    path("parent/", views.parent_child_academics, name="parent_child_academics"),
    path("parent/child-batches/", views.parent_child_batches, name="parent_child_batches"),
    path("parent/child-batches/<str:student_id>/", views.parent_child_batches, name="parent_child_batches_detail"),
    path("parent/<str:student_id>/", views.parent_child_academics, name="parent_child_academics_detail"),

    # Admin desk
    path("admin-overview/", views.admin_academics_overview, name="admin_overview"),

    # Task 2: Course catalogue
    path("courses/", views.admin_courses, name="admin_courses"),
    path("courses/create/", views.admin_course_create, name="admin_course_create"),
    path("courses/<str:course_id>/edit/", views.admin_course_edit, name="admin_course_edit"),

    # Task 2: Subjects configuration
    path("subjects/", views.admin_subjects, name="admin_subjects"),

    # Task 2: Coaching Batches desk
    path("batches/", views.admin_batches, name="admin_batches"),
    path("batches/create/", views.admin_batch_create, name="admin_batch_create"),
    path("batches/<str:batch_id>/", views.admin_batch_detail, name="admin_batch_detail"),
    path("batches/<str:batch_id>/edit/", views.admin_batch_edit, name="admin_batch_edit"),
    path("batches/<str:batch_id>/schedule/add/", views.admin_batch_schedule_add, name="admin_batch_schedule_add"),
    path(
        "batches/<str:batch_id>/schedule/<str:schedule_id>/delete/",
        views.admin_batch_schedule_delete,
        name="admin_batch_schedule_delete",
    ),
    path(
        "batches/<str:batch_id>/teachers/assign/",
        views.admin_batch_assign_teacher,
        name="admin_batch_assign_teacher",
    ),
    path(
        "batches/<str:batch_id>/teachers/<str:assignment_id>/unassign/",
        views.admin_batch_unassign_teacher,
        name="admin_batch_unassign_teacher",
    ),

    # Task 2: Student enrolments & batch transfers
    path("enrollments/", views.admin_enrollments, name="admin_enrollments"),
    path("enrollments/create/", views.admin_enrollment_create, name="admin_enrollment_create"),
    path(
        "enrollments/<str:enrollment_id>/transfer/",
        views.admin_enrollment_transfer,
        name="admin_enrollment_transfer",
    ),
    path(
        "enrollments/<str:enrollment_id>/status/",
        views.admin_enrollment_status_update,
        name="admin_enrollment_status_update",
    ),

    # Task 2: Student & Parent batch portals
    path("student/my-batches/", views.student_my_batches, name="student_my_batches"),
]

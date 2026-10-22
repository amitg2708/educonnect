"""
EduConnect Attendance URL Configuration.
"""

from django.urls import path
from . import views

app_name = "attendance"

urlpatterns = [
    # Teacher Routes
    path("teacher/", views.teacher_attendance_home, name="teacher_home"),
    path("teacher/assignment/<str:assignment_id>/mark/", views.teacher_mark_attendance_view, name="teacher_mark"),
    path("teacher/assignment/<str:assignment_id>/history/", views.teacher_session_history_view, name="teacher_session_history"),
    path("teacher/session/<str:session_id>/edit/", views.teacher_edit_session_view, name="teacher_edit_session"),

    # Student Routes
    path("my-attendance/", views.student_attendance_view, name="student_attendance"),
    path("record/<str:record_id>/correct/", views.submit_correction_request_view, name="submit_correction"),

    # Parent Routes
    path("parent/child/<str:student_id>/", views.parent_child_attendance_view, name="parent_child_attendance"),

    # Admin Control Desk
    path("desk/", views.admin_attendance_dashboard, name="admin_dashboard"),
    path("sessions/", views.admin_sessions_list, name="admin_sessions"),
    path("classrooms/", views.admin_classrooms_list, name="admin_classrooms"),
    path("classrooms/<str:classroom_id>/", views.admin_classroom_detail, name="admin_classroom_detail"),
    path("corrections/", views.admin_corrections_list, name="admin_corrections"),
    path("corrections/<str:correction_id>/review/", views.admin_review_correction_view, name="admin_review_correction"),
    path("reports/", views.admin_attendance_report, name="admin_report"),
]

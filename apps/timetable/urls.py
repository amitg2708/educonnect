"""
EduConnect Timetable URL Configuration.
"""

from django.urls import path
from . import views

app_name = "timetable"

urlpatterns = [
    # Student & Parent
    path("my-schedule/", views.student_timetable_view, name="student_timetable"),
    path("parent/child/<str:student_id>/", views.parent_child_timetable_view, name="parent_child_timetable"),

    # Teacher
    path("teacher/", views.teacher_timetable_view, name="teacher_timetable"),

    # Admin Control Desk
    path("desk/", views.admin_timetable_dashboard, name="admin_dashboard"),
    path("slots/create/", views.admin_create_slot, name="create_slot"),
    path("slots/<str:slot_id>/edit/", views.admin_edit_slot, name="edit_slot"),
    path("slots/<str:slot_id>/cancel/", views.admin_cancel_slot, name="cancel_slot"),
]

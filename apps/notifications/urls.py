"""
URL configurations for EduConnect Notifications, Announcements & Parent Portal Hub.
"""

from django.urls import path
from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    # In-App Notifications
    path("inbox/", views.my_notifications_list, name="my_notifications"),
    path("read/<str:notification_id>/", views.mark_read_view, name="mark_read"),
    path("mark-all-read/", views.mark_all_read_view, name="mark_all_read"),

    # Campus Announcements
    path("announcements/", views.announcements_list, name="announcements_list"),
    path("announcements/<str:announcement_id>/", views.announcement_detail, name="announcement_detail"),
    path("admin-announcements/", views.admin_announcements_desk, name="admin_announcements"),

    # Part 10 Parent Portal Hub
    path("parent-hub/", views.parent_portal_hub, name="parent_hub"),
    path("parent-hub/<str:student_id>/", views.parent_portal_hub, name="parent_hub_child"),
]

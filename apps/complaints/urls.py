"""
URL configurations for EduConnect Complaint & Request Management module.
"""

from django.urls import path
from apps.complaints import views

app_name = "complaints"

urlpatterns = [
    # Student & Parent routes
    path("my-tickets/", views.my_tickets_list, name="my_tickets_list"),
    path("submit/", views.submit_ticket_view, name="submit_ticket"),
    path("ticket/<str:ticket_id>/", views.ticket_detail_view, name="ticket_detail"),
    path("ticket/<str:ticket_id>/reopen/", views.reopen_ticket_view, name="reopen_ticket"),
    path("ticket/<str:ticket_id>/feedback/", views.submit_feedback_view, name="submit_feedback"),

    # Staff & Admin desk
    path("staff/desk/", views.staff_tickets_desk, name="staff_desk"),
    path("staff/ticket/<str:ticket_id>/", views.staff_ticket_detail, name="staff_ticket_detail"),
    path("staff/reports/", views.staff_tickets_report, name="staff_reports"),
]

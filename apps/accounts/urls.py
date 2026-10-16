"""
URL patterns for EduConnect authentication, roles, and profiles.
"""

from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy
from . import views

app_name = "accounts"

urlpatterns = [
    # Authentication
    path("login/", views.EduConnectLoginView.as_view(), name="login"),
    path("logout/", views.EduConnectLogoutView.as_view(), name="logout"),
    path("register/", views.EduConnectRegisterView.as_view(), name="register"),
    # Central dispatcher
    path("dashboard/", views.dashboard_redirect_view, name="dashboard_redirect"),
    # Six Primary Role Dashboards
    path("dashboard/admin/", views.admin_dashboard, name="admin_dashboard"),
    path("dashboard/teacher/", views.teacher_dashboard, name="teacher_dashboard"),
    path("dashboard/student/", views.student_dashboard, name="student_dashboard"),
    path("dashboard/parent/", views.parent_dashboard, name="parent_dashboard"),
    path("dashboard/accounts/", views.accounts_dashboard, name="accounts_dashboard"),
    path("dashboard/applicant/", views.applicant_dashboard, name="applicant_dashboard"),
    # Parent-child detail view
    path("children/<str:student_id>/", views.parent_child_detail, name="parent_child_detail"),
    # Profile
    path("profile/", views.user_profile_view, name="profile"),
    # Admin tools
    path("admin/users/", views.admin_manage_users, name="admin_users"),
    path("admin/link-parent/", views.admin_link_parent_child, name="admin_link_parent"),
    # Password Reset Flow
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.html",
            success_url=reverse_lazy("accounts:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url=reverse_lazy("accounts:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]

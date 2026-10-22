"""
URL routing for EduConnect Multi-Tenant Institutions module.
"""

from django.urls import path
from apps.institutions import views

app_name = "institutions"

urlpatterns = [
    # Multi-tenant switching and selection
    path("select/", views.select_institution_view, name="select_institution"),
    path("switch/<str:institution_id>/", views.switch_institution_view, name="switch_institution"),

    # Invitations onboarding
    path("invitation/<str:token>/accept/", views.accept_invitation_view, name="accept_invitation"),

    # Institute Admin management
    path("admin/members/", views.manage_members_view, name="manage_members"),
    path("admin/invite/", views.send_invitation_view, name="send_invitation"),
    path("admin/branches/", views.manage_branches_view, name="manage_branches"),
    path("admin/branding/", views.institution_branding_view, name="branding"),

    # Platform Superuser Operator Hub
    path("platform/", views.platform_institutions_view, name="platform_admin"),
]

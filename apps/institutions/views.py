"""
Views for EduConnect Multi-Tenant Institution Management, Switching, and Onboarding.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.decorators import admin_required
from apps.accounts.models import Role, User
from apps.institutions.forms import BranchForm, InstitutionBrandingForm, InvitationForm
from apps.institutions.models import (
    Branch,
    Institution,
    InstitutionInvitation,
    InstitutionMembership,
    InvitationStatus,
)


@login_required
def select_institution_view(request):
    """
    Displays the user's available institution memberships and allows 1-click switching.
    """
    memberships = InstitutionMembership.objects.filter(
        user=request.user,
        is_active=True,
        institution__is_active=True,
    ).select_related("institution", "branch")

    context = {
        "page_title": "Select Active Institution",
        "memberships": memberships,
        "current_institution": getattr(request, "institution", None),
    }
    return render(request, "institutions/select.html", context)


@login_required
def switch_institution_view(request, institution_id):
    """
    Switches the user's active institution context in the session.
    Enforces that user is an active member of the target institution, or a superuser.
    """
    target_institution = get_object_or_404(Institution, id=institution_id, is_active=True)

    if not request.user.is_superuser:
        membership = InstitutionMembership.objects.filter(
            user=request.user,
            institution=target_institution,
            is_active=True,
        ).first()

        if not membership:
            raise PermissionDenied(f"You do not possess an active membership at {target_institution.name}.")

        request.session["active_institution_id"] = str(target_institution.id)
        messages.success(
            request,
            f"Switched active institution to {target_institution.name} as {membership.get_role_display()}.",
        )
    else:
        request.session["active_institution_id"] = str(target_institution.id)
        messages.success(request, f"Platform Admin switched view to {target_institution.name}.")

    next_url = request.GET.get("next")
    if next_url and next_url.startswith("/"):
        return redirect(next_url)
    return redirect("accounts:dashboard_redirect")


def accept_invitation_view(request, token):
    """
    Workflow for a user to claim an invitation token and join an institution.
    """
    invitation = get_object_or_404(InstitutionInvitation, token=token)

    if not invitation.is_valid():
        return render(
            request,
            "institutions/invitation_invalid.html",
            {"invitation": invitation, "reason": "This invitation link has expired or was already used."},
        )

    if request.method == "POST":
        if not request.user.is_authenticated:
            messages.info(request, "Please log in or register an account to accept your invitation.")
            return redirect(f"{reverse('accounts:login')}?next={request.path}")

        try:
            membership = invitation.accept(request.user)
            request.session["active_institution_id"] = str(invitation.institution.id)
            messages.success(
                request,
                f"Welcome! You have successfully joined {invitation.institution.name} as {membership.get_role_display()}.",
            )
            return redirect("accounts:dashboard_redirect")
        except ValidationError as e:
            messages.error(request, str(e))

    context = {
        "page_title": f"Invitation to Join {invitation.institution.name}",
        "invitation": invitation,
    }
    return render(request, "institutions/invitation_accept.html", context)


@admin_required
def manage_members_view(request):
    """
    Institute Administrator overview of all users and memberships in their institute.
    """
    current_inst = getattr(request, "institution", None)
    if not current_inst:
        raise PermissionDenied("No active institution context found.")

    memberships = InstitutionMembership.objects.filter(
        institution=current_inst,
    ).select_related("user", "branch").order_by("-joined_at")

    invitations = InstitutionInvitation.objects.filter(
        institution=current_inst,
        status=InvitationStatus.PENDING,
    ).order_by("-created_at")

    context = {
        "page_title": f"Manage Members - {current_inst.name}",
        "memberships": memberships,
        "invitations": invitations,
        "institution": current_inst,
    }
    return render(request, "institutions/admin/members.html", context)


@admin_required
def send_invitation_view(request):
    """
    Institute Administrator issues a new invitation token.
    """
    current_inst = getattr(request, "institution", None)
    if not current_inst:
        raise PermissionDenied("No active institution context found.")

    if request.method == "POST":
        form = InvitationForm(request.POST, institution=current_inst)
        if form.is_valid():
            invitation = form.save(commit=False)
            invitation.institution = current_inst
            invitation.invited_by = request.user
            invitation.save()

            invite_url = request.build_absolute_uri(
                reverse("institutions:accept_invitation", kwargs={"token": invitation.token})
            )
            messages.success(
                request,
                f"Invitation created for {invitation.email} ({invitation.get_role_display()})! Link: {invite_url}",
            )
            return redirect("institutions:manage_members")
    else:
        form = InvitationForm(institution=current_inst)

    context = {
        "page_title": "Send Institution Invitation",
        "form": form,
        "institution": current_inst,
    }
    return render(request, "institutions/admin/invite_form.html", context)


@admin_required
def manage_branches_view(request):
    """
    Manage branches/campuses for the active institution.
    """
    current_inst = getattr(request, "institution", None)
    if not current_inst:
        raise PermissionDenied("No active institution context found.")

    branches = Branch.objects.filter(institution=current_inst).order_by("name")

    if request.method == "POST":
        form = BranchForm(request.POST)
        if form.is_valid():
            branch = form.save(commit=False)
            branch.institution = current_inst
            branch.save()
            messages.success(request, f"Branch '{branch.name}' created successfully.")
            return redirect("institutions:manage_branches")
    else:
        form = BranchForm()

    context = {
        "page_title": f"Branches & Campuses - {current_inst.name}",
        "branches": branches,
        "form": form,
        "institution": current_inst,
    }
    return render(request, "institutions/admin/branches.html", context)


@admin_required
def institution_branding_view(request):
    """
    Allows Institute Administrator to customize colors, tagline, contact info, and branding.
    """
    current_inst = getattr(request, "institution", None)
    if not current_inst:
        raise PermissionDenied("No active institution context found.")

    if request.method == "POST":
        form = InstitutionBrandingForm(request.POST, request.FILES, instance=current_inst)
        if form.is_valid():
            form.save()
            messages.success(request, "Institution settings and branding updated successfully.")
            return redirect("institutions:branding")
    else:
        form = InstitutionBrandingForm(instance=current_inst)

    context = {
        "page_title": f"Branding & Settings - {current_inst.name}",
        "form": form,
        "institution": current_inst,
    }
    return render(request, "institutions/admin/branding.html", context)


@login_required
def platform_institutions_view(request):
    """
    Dedicated platform-wide operator view (superusers only).
    Allows creating new coaching institutes and monitoring all tenants.
    """
    if not request.user.is_superuser:
        raise PermissionDenied("Platform administration is restricted to platform superusers.")

    institutions = Institution.objects.all().order_by("-created_at")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        code = request.POST.get("code", "").strip().upper()
        tagline = request.POST.get("tagline", "").strip()
        primary_color = request.POST.get("primary_color", "#0d6efd")

        if name and code:
            if Institution.objects.filter(code=code).exists():
                messages.error(request, f"An institution with code '{code}' already exists.")
            else:
                inst = Institution.objects.create(
                    name=name,
                    code=code,
                    tagline=tagline,
                    primary_color=primary_color,
                )
                Branch.objects.create(
                    institution=inst,
                    name="Main Campus",
                    code="MAIN",
                    is_main=True,
                )
                messages.success(request, f"New coaching institute '{inst.name}' ({inst.code}) successfully provisioned!")
                return redirect("institutions:platform_admin")
        else:
            messages.error(request, "Name and Code are required to provision an institution.")

    context = {
        "page_title": "EduConnect Platform Operator Hub",
        "institutions": institutions,
    }
    return render(request, "institutions/admin/platform.html", context)

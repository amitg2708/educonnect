"""
Forms for EduConnect Institutions, Branches, and Invitations.
"""

from django import forms
from apps.accounts.models import Role
from apps.institutions.models import Branch, Institution, InstitutionInvitation


class InstitutionBrandingForm(forms.ModelForm):
    """Form to manage institution settings, contact info, and theme colors."""

    class Meta:
        model = Institution
        fields = [
            "name",
            "tagline",
            "description",
            "public_notice",
            "custom_domain",
            "contact_email",
            "contact_phone",
            "address",
            "website",
            "primary_color",
            "accent_color",
            "logo",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "tagline": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "description": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary", "rows": 3}),
            "public_notice": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary", "rows": 2, "placeholder": "e.g. Admissions open for 2026-27 cohort! Early bird discount applies."}),
            "custom_domain": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary", "placeholder": "e.g. apexacademy.com"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "address": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary", "rows": 2}),
            "website": forms.URLInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "primary_color": forms.TextInput(attrs={"type": "color", "class": "form-control form-control-color bg-dark border-secondary"}),
            "accent_color": forms.TextInput(attrs={"type": "color", "class": "form-control form-control-color bg-dark border-secondary"}),
            "logo": forms.FileInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
        }


class BranchForm(forms.ModelForm):
    """Form to create or update an institution branch."""

    class Meta:
        model = Branch
        fields = ["name", "code", "city", "state", "phone", "email", "address", "is_main"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary", "placeholder": "e.g. North Campus"}),
            "code": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary", "placeholder": "e.g. NORTH"}),
            "city": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "state": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "phone": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary"}),
            "address": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary", "rows": 2}),
            "is_main": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class InvitationForm(forms.ModelForm):
    """Form for administrators to issue institution invitations."""

    class Meta:
        model = InstitutionInvitation
        fields = ["email", "role", "branch", "notes"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary", "placeholder": "user@example.com"}),
            "role": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary"}),
            "branch": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary"}),
            "notes": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary", "rows": 2, "placeholder": "Welcome message or departmental instructions..."}),
        }

    def __init__(self, *args, institution=None, **kwargs):
        super().__init__(*args, **kwargs)
        if institution:
            self.fields["branch"].queryset = Branch.objects.filter(institution=institution, is_active=True)
            self.fields["branch"].empty_label = "All Branches / Main Campus"

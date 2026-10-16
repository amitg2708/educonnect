"""
EduConnect Authentication and Profile Forms.
Strictly prevents privilege escalation during registration.
"""

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from .models import Role, User, ParentStudentLink

# Permitted public self-registration roles
# NEVER include Admin or Accounts Staff in public registration!
PUBLIC_REGISTRATION_ROLES = [
    (Role.APPLICANT, "Applicant (Prospective Student)"),
    (Role.STUDENT, "Student"),
    (Role.PARENT, "Parent / Guardian"),
    (Role.TEACHER, "Subject Teacher"),
]


class EduConnectLoginForm(AuthenticationForm):
    """
    Styled login form with Bootstrap 5 styling.
    """

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Enter your username",
                "autofocus": True,
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control form-control-lg",
                "placeholder": "Enter your password",
            }
        )
    )


class EduConnectRegistrationForm(UserCreationForm):
    """
    Public registration form with strict role validation.
    Admin and Accounts Staff roles are strictly prohibited.
    """

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "name@example.com",
            }
        ),
    )
    first_name = forms.CharField(
        required=True,
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "First name"}
        ),
    )
    last_name = forms.CharField(
        required=True,
        max_length=100,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Last name"}
        ),
    )
    role = forms.ChoiceField(
        choices=PUBLIC_REGISTRATION_ROLES,
        required=True,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select your institutional role. Admin and Accounts Staff accounts must be provisioned by school administration.",
    )
    phone_number = forms.CharField(
        required=False,
        max_length=20,
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "+1 (555) 000-0000"}
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = (
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "phone_number",
        )

    def clean_email(self):
        email = self.cleaned_data.get("email").strip().lower()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email address already exists.")
        return email

    def clean_role(self):
        role = self.cleaned_data.get("role")
        # Enforce server-side security rule: Never allow Admin or Accounts Staff self-registration
        forbidden_roles = [Role.ADMIN, Role.ACCOUNTS]
        if role in forbidden_roles or role not in [r[0] for r in PUBLIC_REGISTRATION_ROLES]:
            raise ValidationError(
                "Unauthorized role selection. Administrative and financial accounts cannot be registered publicly."
            )
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.role = self.cleaned_data["role"]
        user.phone_number = self.cleaned_data.get("phone_number", "")
        if commit:
            user.save()
        return user


class UserProfileForm(forms.ModelForm):
    """
    Form allowing users to update their profile information.
    """

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "address",
            "bio",
            "grade_level",
            "subject_specialization",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "grade_level": forms.TextInput(attrs={"class": "form-control"}),
            "subject_specialization": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Lock fields that don't apply to the user's role
        if self.instance and self.instance.pk:
            if not self.instance.is_student_role:
                self.fields.pop("grade_level", None)
            if not self.instance.is_teacher_role:
                self.fields.pop("subject_specialization", None)


class ParentChildLinkAdminForm(forms.ModelForm):
    """
    Form for administrators to link parents with students.
    """

    class Meta:
        model = ParentStudentLink
        fields = ["parent", "student", "relationship_type", "is_authorized", "notes"]
        widgets = {
            "parent": forms.Select(attrs={"class": "form-select"}),
            "student": forms.Select(attrs={"class": "form-select"}),
            "relationship_type": forms.Select(attrs={"class": "form-select"}),
            "is_authorized": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].queryset = User.objects.filter(role=Role.PARENT)
        self.fields["student"].queryset = User.objects.filter(role=Role.STUDENT)

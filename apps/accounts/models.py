"""
EduConnect Custom User and Authentication Models.
Supports six primary roles with strict server-side permission checks
and MongoDB ObjectId-compatible primary keys.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as BaseUserManager
from django.db import models


class Role(models.TextChoices):
    ADMIN = "admin", "Admin"
    TEACHER = "teacher", "Subject Teacher"
    STUDENT = "student", "Student"
    PARENT = "parent", "Parent"
    ACCOUNTS = "accounts", "Accounts Staff"
    APPLICANT = "applicant", "Applicant"


class CustomUserManager(BaseUserManager):
    """
    Manager for EduConnect custom User model.
    """

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.ADMIN)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    Primary User model for EduConnect with role-based attributes and MongoDB compatibility.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_users",
        help_text="Primary or initial institution affiliation.",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.APPLICANT,
        help_text="Designates the user's operational role in the institution.",
    )
    phone_number = models.CharField(max_length=25, blank=True)
    address = models.TextField(blank=True)

    # Student specific
    student_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        help_text="Institutional student enrollment ID.",
    )
    grade_level = models.CharField(
        max_length=50,
        blank=True,
        help_text="Grade, Class, or Academic Program level.",
    )

    # Teacher / Staff specific
    employee_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        unique=True,
        help_text="Faculty / Staff employee ID.",
    )
    subject_specialization = models.CharField(
        max_length=120,
        blank=True,
        help_text="Primary teaching subject or department.",
    )

    # Profile notes
    bio = models.TextField(blank=True)

    objects = CustomUserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["role"]),
            models.Index(fields=["email"]),
        ]

    def __str__(self):
        full_name = self.get_full_name()
        display = full_name if full_name else self.username
        return f"{display} ({self.get_role_display()})"

    # Role check helpers
    @property
    def is_admin_role(self):
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def is_teacher_role(self):
        return self.role == Role.TEACHER

    @property
    def is_student_role(self):
        return self.role == Role.STUDENT

    @property
    def is_parent_role(self):
        return self.role == Role.PARENT

    @property
    def is_accounts_role(self):
        return self.role == Role.ACCOUNTS

    @property
    def is_applicant_role(self):
        return self.role == Role.APPLICANT

    def get_membership_for_institution(self, institution):
        """Returns the active membership of this user for a given institution."""
        if not institution:
            return None
        return self.institution_memberships.filter(institution=institution, is_active=True).first()

    def get_role_for_institution(self, institution):
        """Returns the specific role held by the user at the given institution."""
        membership = self.get_membership_for_institution(institution)
        return membership.role if membership else self.role

    def get_dashboard_url_name(self, role=None):
        """
        Return the designated dashboard url name based on the specified or active role.
        """
        target_role = role or self.role
        role_dashboard_map = {
            Role.ADMIN: "accounts:admin_dashboard",
            Role.TEACHER: "accounts:teacher_dashboard",
            Role.STUDENT: "accounts:student_dashboard",
            Role.PARENT: "accounts:parent_dashboard",
            Role.ACCOUNTS: "accounts:accounts_dashboard",
            Role.APPLICANT: "accounts:applicant_dashboard",
        }
        return role_dashboard_map.get(target_role, "core:index")

    @property
    def memberships(self):
        return self.institution_memberships

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.institution_id:
            from apps.institutions.models import InstitutionMembership
            InstitutionMembership.objects.get_or_create(
                user=self,
                institution_id=self.institution_id,
                defaults={
                    "role": self.role,
                    "is_default": True,
                    "is_active": True,
                },
            )


class ParentStudentLink(models.Model):
    """
    Explicit authorization link between a Parent and their child/student.
    Scoped per-institution so parents only access authorized child records within that institute.
    """

    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.CASCADE,
        related_name="parent_student_links",
        null=True,
        blank=True,
        help_text="Institution context for this parental authorization.",
    )
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="children_links",
        limit_choices_to={"role": Role.PARENT},
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="parent_links",
        limit_choices_to={"role": Role.STUDENT},
    )
    relationship_type = models.CharField(
        max_length=50,
        choices=[
            ("father", "Father"),
            ("mother", "Mother"),
            ("guardian", "Legal Guardian"),
            ("other", "Other"),
        ],
        default="guardian",
    )
    is_authorized = models.BooleanField(
        default=True,
        help_text="Whether this parental link is verified by school administration.",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Parent-Student Link"
        verbose_name_plural = "Parent-Student Links"
        unique_together = ("institution", "parent", "student")
        indexes = [
            models.Index(fields=["institution", "parent"]),
            models.Index(fields=["institution", "student"]),
        ]

    def __str__(self):
        inst_label = f" [{self.institution.code}]" if self.institution else ""
        parent_name = self.parent.get_full_name() or self.parent.username
        student_name = self.student.get_full_name() or self.student.username
        return f"{parent_name} -> {student_name} ({self.get_relationship_type_display()}){inst_label}"

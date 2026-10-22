"""
EduConnect Multi-Tenant Architecture Models.
Defines Institution, Branch, InstitutionMembership, and Invitation workflows.
Enables independent coaching institutes to coexist securely on a shared platform
with isolated data, custom branding, and multi-role user memberships.
"""

from datetime import timedelta
import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from apps.accounts.models import Role


def generate_invitation_token() -> str:
    """Generate a high-entropy URL-safe invitation token."""
    return secrets.token_urlsafe(32)


class Institution(models.Model):
    """
    Independent Coaching Institute / School / College tenant on EduConnect.
    """

    name = models.CharField(max_length=220, help_text="Official institution or coaching center name.")
    code = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Short unique institution code e.g. APEX, EDUCONNECT, FIITJEE",
    )
    slug = models.SlugField(
        max_length=250,
        unique=True,
        blank=True,
        help_text="URL-friendly identifier for institute portal routing.",
    )
    subdomain = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        unique=True,
        help_text="Optional custom subdomain e.g. apex.educonnect.local",
    )
    custom_domain = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        unique=True,
        help_text="Optional custom domain e.g. apexacademy.com",
    )
    tagline = models.CharField(max_length=255, blank=True, help_text="Motto or promotional tagline.")
    description = models.TextField(blank=True, help_text="Overview of programs and pedagogy.")
    public_notice = models.TextField(
        blank=True,
        help_text="Configurable public banner announcement or notice for prospective students and visitors.",
    )
    logo = models.ImageField(upload_to="institutions/logos/", blank=True, null=True)

    # Branding & Custom UI Theme
    primary_color = models.CharField(
        max_length=20,
        default="#0d6efd",
        help_text="Primary branding color (Hex e.g. #0d6efd or CSS variable).",
    )
    accent_color = models.CharField(
        max_length=20,
        default="#0dcaf0",
        help_text="Accent branding color (Hex e.g. #0dcaf0).",
    )

    # Contact & Location
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    website = models.URLField(blank=True)

    # System Status
    is_active = models.BooleanField(
        default=True,
        help_text="When false, institute users cannot access tenant-scoped portals.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Institution"
        verbose_name_plural = "Institutions"
        ordering = ["name"]
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.code}-{self.name}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class Branch(models.Model):
    """
    Physical or operational branch of an institution.
    e.g., Downtown Branch, North Campus, Online Division.
    """

    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="branches",
        help_text="Parent coaching institute or school.",
    )
    name = models.CharField(max_length=150, help_text="Branch name e.g. North Campus, Sector 14 Branch")
    code = models.CharField(max_length=50, help_text="Branch code e.g. MAIN, NORTH, ONLINE")
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    is_main = models.BooleanField(
        default=False,
        help_text="Designates this branch as the primary/headquarters campus.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        ordering = ["institution", "name"]
        unique_together = ("institution", "code")
        indexes = [
            models.Index(fields=["institution", "code"]),
            models.Index(fields=["institution", "is_active"]),
        ]

    def __str__(self):
        main_flag = " [Headquarters]" if self.is_main else ""
        return f"{self.institution.code} - {self.name} ({self.code}){main_flag}"


class InstitutionMembership(models.Model):
    """
    Binding between a User and an Institution.
    Enforces that a single User account can belong to multiple institutes
    holding distinct roles at each (e.g. Teacher at Institute A, Parent at Institute B).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="institution_memberships",
    )
    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="branch_memberships",
        help_text="Optional branch assignment for localized staff and students.",
    )
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
        help_text="Designated role of this user specifically within this institution.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this user's membership in this institute is currently active.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Whether this is the user's primary/default institution on login.",
    )
    designation = models.CharField(
        max_length=120,
        blank=True,
        help_text="Operational title e.g. Senior Faculty, Academic Dean, Batch Mentor",
    )
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Institution Membership"
        verbose_name_plural = "Institution Memberships"
        unique_together = ("user", "institution")
        indexes = [
            models.Index(fields=["user", "institution"]),
            models.Index(fields=["institution", "role"]),
            models.Index(fields=["institution", "is_active"]),
        ]

    def __str__(self):
        user_name = self.user.get_full_name() or self.user.username
        return f"{user_name} @ {self.institution.name} ({self.get_role_display()})"

    def clean(self):
        if self.branch and self.branch.institution_id != self.institution_id:
            raise ValidationError({"branch": "The assigned branch must belong to the selected institution."})


class InvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    EXPIRED = "expired", "Expired"


class InstitutionInvitation(models.Model):
    """
    Invitation workflow to onboard staff, teachers, students, or parents into an institute.
    """

    institution = models.ForeignKey(
        Institution,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invitations",
    )
    email = models.EmailField(help_text="Email address of the invited user.")
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_institution_invitations",
    )
    token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_invitation_token,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING,
    )
    notes = models.TextField(blank=True, help_text="Optional welcome message or department instructions.")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Institution Invitation"
        verbose_name_plural = "Institution Invitations"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["email", "institution"]),
            models.Index(fields=["status"]),
        ]

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=14)
        super().save(*args, **kwargs)

    def is_valid(self) -> bool:
        """Check if invitation is pending and not expired."""
        if self.status != InvitationStatus.PENDING:
            return False
        return timezone.now() < self.expires_at

    def accept(self, user) -> InstitutionMembership:
        """Accept invitation and activate/create InstitutionMembership."""
        if not self.is_valid():
            raise ValidationError("This invitation is no longer valid or has expired.")

        membership, _ = InstitutionMembership.objects.update_or_create(
            user=user,
            institution=self.institution,
            defaults={
                "branch": self.branch,
                "role": self.role,
                "is_active": True,
            },
        )
        self.status = InvitationStatus.ACCEPTED
        self.accepted_at = timezone.now()
        self.save(update_fields=["status", "accepted_at"])
        return membership

    def __str__(self):
        return f"Invite for {self.email} -> {self.institution.name} as {self.get_role_display()} ({self.get_status_display()})"

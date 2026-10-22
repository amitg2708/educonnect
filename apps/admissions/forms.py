"""
EduConnect Admissions Management Forms.
Handles applicant submission, permitted updates, document uploads,
duplicate prevention, and administrative decision recording.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from apps.core.models import Course
from .models import (
    AdmissionApplication,
    ApplicationDocument,
    ApplicationStatus,
    DocumentType,
    Enquiry,
    EnquiryFollowUp,
    EnquirySource,
    EnquiryStatus,
    validate_document_file,
)


class AdmissionApplicationForm(forms.ModelForm):
    """
    Applicant-facing form to submit an admission application with required documents.
    """

    identity_proof_file = forms.FileField(
        required=True,
        validators=[validate_document_file],
        help_text="National ID, Passport, or Birth Certificate (PDF, JPG, PNG, max 5 MB).",
        widget=forms.FileInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
    )
    transcript_file = forms.FileField(
        required=True,
        validators=[validate_document_file],
        help_text="Official academic transcript or marksheet (PDF, JPG, PNG, max 5 MB).",
        widget=forms.FileInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
    )
    passport_photo_file = forms.FileField(
        required=False,
        validators=[validate_document_file],
        help_text="Recent passport-style photograph (optional, max 5 MB).",
        widget=forms.FileInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
    )

    class Meta:
        model = AdmissionApplication
        fields = [
            "course",
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "date_of_birth",
            "gender",
            "nationality",
            "address_line1",
            "city",
            "state",
            "postal_code",
            "country",
            "guardian_name",
            "guardian_relationship",
            "guardian_phone",
            "guardian_email",
            "previous_institution",
            "previous_qualification",
            "previous_grade_or_percentage",
            "year_of_passing",
            "statement_of_purpose",
        ]
        widgets = {
            "course": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "first_name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "last_name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": "form-control bg-dark text-light border-secondary-subtle"}),
            "gender": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "nationality": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "address_line1": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "city": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "state": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "postal_code": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "country": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "guardian_name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "guardian_relationship": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "guardian_phone": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "guardian_email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "previous_institution": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "previous_qualification": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "previous_grade_or_percentage": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "year_of_passing": forms.NumberInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "statement_of_purpose": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        self.applicant_user = kwargs.pop("applicant_user", None)
        super().__init__(*args, **kwargs)
        self.fields["course"].queryset = Course.objects.filter(is_active=True)

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get("date_of_birth")
        if dob:
            today = timezone.now().date()
            if dob >= today:
                raise ValidationError("Date of birth must be in the past.")
            age = (today - dob).days // 365
            if age < 4:
                raise ValidationError("Applicant must be at least 4 years of age for academic enrollment.")
        return dob

    def clean_year_of_passing(self):
        yop = self.cleaned_data.get("year_of_passing")
        current_year = timezone.now().year
        if yop and (yop < 1980 or yop > current_year + 1):
            raise ValidationError(f"Please provide a realistic graduation year (1980 - {current_year + 1}).")
        return yop

    def clean(self):
        cleaned_data = super().clean()
        course = cleaned_data.get("course")

        # Duplicate active application check
        if self.applicant_user and course:
            active_statuses = [
                ApplicationStatus.SUBMITTED,
                ApplicationStatus.UNDER_REVIEW,
                ApplicationStatus.ACTION_REQUIRED,
                ApplicationStatus.APPROVED,
            ]
            duplicate = AdmissionApplication.objects.filter(
                applicant=self.applicant_user,
                course=course,
                status__in=active_statuses,
            ).first()

            if duplicate:
                raise ValidationError(
                    f"You already have an active application ({duplicate.application_number}) "
                    f"for {course.title}. You cannot submit a duplicate application for the same course."
                )

        return cleaned_data


class AdmissionApplicationUpdateForm(forms.ModelForm):
    """
    Form for updating permitted fields when an application is in editable state
    (Draft or Action Required). Explicitly excludes course, status, decision, and staff notes.
    """

    class Meta:
        model = AdmissionApplication
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone_number",
            "date_of_birth",
            "gender",
            "nationality",
            "address_line1",
            "city",
            "state",
            "postal_code",
            "country",
            "guardian_name",
            "guardian_relationship",
            "guardian_phone",
            "guardian_email",
            "previous_institution",
            "previous_qualification",
            "previous_grade_or_percentage",
            "year_of_passing",
            "statement_of_purpose",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "last_name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "phone_number": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": "form-control bg-dark text-light border-secondary-subtle"}),
            "gender": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "nationality": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "address_line1": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "city": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "state": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "postal_code": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "country": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "guardian_name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "guardian_relationship": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "guardian_phone": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "guardian_email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "previous_institution": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "previous_qualification": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "previous_grade_or_percentage": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "year_of_passing": forms.NumberInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "statement_of_purpose": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "rows": 4}),
        }

    def clean_year_of_passing(self):
        yop = self.cleaned_data.get("year_of_passing")
        current_year = timezone.now().year
        if yop and (yop < 1980 or yop > current_year + 1):
            raise ValidationError(f"Please provide a realistic graduation year (1980 - {current_year + 1}).")
        return yop


class ApplicationDocumentUploadForm(forms.ModelForm):
    """
    Form for uploading additional or missing documents.
    """

    class Meta:
        model = ApplicationDocument
        fields = ["document_type", "title", "file"]
        widgets = {
            "document_type": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "title": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "e.g. Class 12 Stamped Marksheet"}),
            "file": forms.FileInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
        }


class AdminApplicationDecisionForm(forms.Form):
    """
    Form for administrators to record decisions, request missing information, or review applications.
    """

    status = forms.ChoiceField(
        choices=[
            (ApplicationStatus.UNDER_REVIEW, "Mark as Under Review"),
            (ApplicationStatus.ACTION_REQUIRED, "Request Missing Documents / Action Required"),
            (ApplicationStatus.APPROVED, "Approve Application for Admission"),
            (ApplicationStatus.REJECTED, "Reject Application"),
        ],
        widget=forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
    )
    applicant_remarks = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control bg-dark text-light border-secondary-subtle",
            "rows": 4,
            "placeholder": "Feedback, instructions, or missing documents list visible to the applicant...",
        }),
        required=True,
        help_text="This message is directly displayed to the applicant on their portal.",
    )
    admin_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control bg-dark text-light border-secondary-subtle",
            "rows": 2,
            "placeholder": "Private notes visible only to institutional staff...",
        }),
        required=False,
    )

    def clean(self):
        cleaned_data = super().clean()
        status = cleaned_data.get("status")
        remarks = cleaned_data.get("applicant_remarks", "").strip()

        if status == ApplicationStatus.ACTION_REQUIRED and not remarks:
            raise ValidationError("Please specify the missing documents or actions required from the applicant.")

        return cleaned_data


# ==============================================================================
# ENQUIRY & CRM FORMS
# ==============================================================================

class PublicEnquiryForm(forms.ModelForm):
    """
    Public website inquiry form for prospective students or parents.
    """

    class Meta:
        model = Enquiry
        fields = [
            "name",
            "email",
            "phone",
            "alternate_phone",
            "city",
            "target_class",
            "stream",
            "course",
            "batch_interest",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "Student / Parent Full Name"}),
            "email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "Email Address"}),
            "phone": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "+91 98765 43210"}),
            "alternate_phone": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "Alternate WhatsApp / Phone (Optional)"}),
            "city": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "City / Location"}),
            "target_class": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "e.g. Class 10, Class 11, Class 12"}),
            "stream": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "e.g. Science, Commerce, Arts"}),
            "course": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "batch_interest": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "notes": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "rows": 3, "placeholder": "Tell us what you are looking for (e.g. Weekend batch, Board prep, Entrance exam guidance)..."}),
        }

    def __init__(self, *args, institution=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Course
        from apps.academics.models import Batch
        if institution:
            self.fields["course"].queryset = Course.objects.filter(
                models.Q(institution=institution) | models.Q(institution__isnull=True),
                is_active=True,
            )
            self.fields["batch_interest"].queryset = Batch.objects.filter(
                institution=institution,
                status__in=[Batch.Status.UPCOMING, Batch.Status.ONGOING],
            )
        else:
            self.fields["course"].queryset = Course.objects.filter(is_active=True)
            self.fields["batch_interest"].queryset = Batch.objects.none()
        self.fields["course"].required = False
        self.fields["batch_interest"].required = False


class StaffEnquiryForm(forms.ModelForm):
    """
    Staff / Counselor form to log enquiries received by phone, walk-in, referral, or email.
    """

    class Meta:
        model = Enquiry
        fields = [
            "source",
            "name",
            "email",
            "phone",
            "alternate_phone",
            "city",
            "branch",
            "target_class",
            "stream",
            "course",
            "batch_interest",
            "assigned_to",
            "status",
            "next_follow_up_date",
            "trial_class_date",
            "notes",
        ]
        widgets = {
            "source": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "status": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "name": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "email": forms.EmailInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "phone": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "alternate_phone": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "city": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle"}),
            "branch": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "target_class": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "e.g. Class 10"}),
            "stream": forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "e.g. Science"}),
            "course": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "batch_interest": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "assigned_to": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "next_follow_up_date": forms.DateInput(attrs={"type": "date", "class": "form-control bg-dark text-light border-secondary-subtle"}),
            "trial_class_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control bg-dark text-light border-secondary-subtle"}),
            "notes": forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "rows": 3}),
        }

    def __init__(self, *args, institution=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import Course
        from apps.academics.models import Batch
        from apps.institutions.models import Branch, InstitutionMembership
        from apps.accounts.models import Role, User

        if institution:
            self.fields["course"].queryset = Course.objects.filter(
                models.Q(institution=institution) | models.Q(institution__isnull=True),
                is_active=True,
            )
            self.fields["batch_interest"].queryset = Batch.objects.filter(
                institution=institution,
            )
            self.fields["branch"].queryset = Branch.objects.filter(institution=institution, is_active=True)
            staff_ids = InstitutionMembership.objects.filter(
                institution=institution,
                role__in=[Role.ADMIN, Role.TEACHER, Role.ACCOUNTS],
                is_active=True,
            ).values_list("user_id", flat=True)
            self.fields["assigned_to"].queryset = User.objects.filter(id__in=staff_ids)
        else:
            self.fields["course"].queryset = Course.objects.filter(is_active=True)
            self.fields["batch_interest"].queryset = Batch.objects.none()
            self.fields["branch"].queryset = Branch.objects.none()
            self.fields["assigned_to"].queryset = User.objects.none()


class EnquiryFollowUpForm(forms.ModelForm):
    """
    Form to record an interaction follow-up note, advance status, or reschedule next follow-up.
    """

    new_status = forms.ChoiceField(
        choices=EnquiryStatus.choices,
        required=False,
        widget=forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
        help_text="Update the lead's current pipeline status.",
    )
    scheduled_follow_up_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control bg-dark text-light border-secondary-subtle"}),
        help_text="Next scheduled touchpoint date.",
    )

    class Meta:
        model = EnquiryFollowUp
        fields = [
            "contact_mode",
            "notes",
            "new_status",
            "scheduled_follow_up_date",
        ]
        widgets = {
            "contact_mode": forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
            "notes": forms.Textarea(attrs={
                "class": "form-control bg-dark text-light border-secondary-subtle",
                "rows": 3,
                "placeholder": "Enter detailed notes on discussion, student feedback, or parent decision...",
            }),
        }


class EnquiryAssignStaffForm(forms.Form):
    """
    Form to assign or re-assign an enquiry to a counselor / staff member.
    """

    assigned_to = forms.ModelChoiceField(
        queryset=None,
        required=True,
        widget=forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
        label="Assign Counselor / Staff Member",
    )
    next_follow_up_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control bg-dark text-light border-secondary-subtle"}),
    )
    assignment_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "form-control bg-dark text-light border-secondary-subtle",
            "rows": 2,
            "placeholder": "Instructions or guidance for the assigned counselor...",
        }),
    )

    def __init__(self, *args, institution=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.institutions.models import InstitutionMembership
        from apps.accounts.models import Role, User
        if institution:
            staff_ids = InstitutionMembership.objects.filter(
                institution=institution,
                role__in=[Role.ADMIN, Role.TEACHER, Role.ACCOUNTS],
                is_active=True,
            ).values_list("user_id", flat=True)
            self.fields["assigned_to"].queryset = User.objects.filter(id__in=staff_ids)
        else:
            self.fields["assigned_to"].queryset = User.objects.filter(role__in=[Role.ADMIN, Role.TEACHER])


class ConvertApplicantToStudentForm(forms.Form):
    """
    Form to convert an approved application into an active student and enrol into a batch.
    Supports verified linking of existing accounts to prevent duplicate users.
    """

    target_batch = forms.ModelChoiceField(
        queryset=None,
        required=False,
        widget=forms.Select(attrs={"class": "form-select bg-dark text-light border-secondary-subtle"}),
        help_text="Select coaching cohort batch to enrol student into.",
    )
    roll_number = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "placeholder": "e.g. C10-01"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control bg-dark text-light border-secondary-subtle", "rows": 2}),
    )

    def __init__(self, *args, institution=None, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.academics.models import Batch
        qs = Batch.objects.filter(status__in=[Batch.Status.UPCOMING, Batch.Status.ONGOING])
        if institution:
            qs = qs.filter(institution=institution)
        if course:
            qs = qs.filter(course=course)
        self.fields["target_batch"].queryset = qs


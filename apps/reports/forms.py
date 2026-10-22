"""
Forms for EduConnect Institutional Settings and Administrative Management.
"""

from django import forms

from apps.accounts.models import Role, User
from apps.attendance.models import AcademicSession, ClassEnrollment, ClassRoom, TeacherAssignment
from apps.reports.models import InstitutionSetting


class InstitutionSettingForm(forms.ModelForm):
    """
    Form for updating global institutional operational parameters.
    """

    class Meta:
        model = InstitutionSetting
        fields = [
            "institution_name",
            "institution_code",
            "academic_year",
            "contact_email",
            "contact_phone",
            "campus_address",
            "attendance_minimum_percent",
            "default_complaint_sla_days",
        ]
        widgets = {
            "institution_name": forms.TextInput(attrs={"class": "form-control"}),
            "institution_code": forms.TextInput(attrs={"class": "form-control"}),
            "academic_year": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 2026-2027"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control"}),
            "campus_address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "attendance_minimum_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.5"}),
            "default_complaint_sla_days": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "1"}),
        }


class ClassRoomCreateForm(forms.ModelForm):
    """
    Form for administrators to create or edit classrooms and cohorts.
    """

    class Meta:
        model = ClassRoom
        fields = ["name", "code", "academic_session", "room_number", "capacity", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Grade 10 - Section A"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. G10-A"}),
            "academic_session": forms.Select(attrs={"class": "form-select"}),
            "room_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Room 204"}),
            "capacity": forms.NumberInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ClassEnrollmentCreateForm(forms.ModelForm):
    """
    Form to enroll a registered student into a classroom cohort.
    """

    class Meta:
        model = ClassEnrollment
        fields = ["student", "classroom", "roll_number", "is_active"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "roll_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Roll-101"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = User.objects.filter(role=Role.STUDENT, is_active=True)
        self.fields["classroom"].queryset = ClassRoom.objects.filter(is_active=True)


class TeacherAssignmentCreateForm(forms.ModelForm):
    """
    Form to authorize a faculty member to teach a subject in a classroom.
    """

    class Meta:
        model = TeacherAssignment
        fields = ["teacher", "classroom", "subject_name", "is_active"]
        widgets = {
            "teacher": forms.Select(attrs={"class": "form-select"}),
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "subject_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Advanced Physics"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = User.objects.filter(role=Role.TEACHER, is_active=True)
        self.fields["classroom"].queryset = ClassRoom.objects.filter(is_active=True)

"""
EduConnect Attendance Forms.
"""

from django import forms
from django.contrib.auth import get_user_model
from apps.accounts.models import Role
from .models import (
    AcademicSession,
    ClassRoom,
    ClassEnrollment,
    TeacherAssignment,
    AttendancePolicy,
    AttendanceStatus,
    AttendanceCorrectionRequest,
    CorrectionStatus,
)

User = get_user_model()


class AcademicSessionForm(forms.ModelForm):
    class Meta:
        model = AcademicSession
        fields = ["name", "start_date", "end_date", "is_current"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Fall 2026 Semester"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_current": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ClassRoomForm(forms.ModelForm):
    class Meta:
        model = ClassRoom
        fields = ["name", "code", "course", "academic_session", "room_number", "capacity", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Grade 10 - Section A"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. CLS-10A"}),
            "course": forms.Select(attrs={"class": "form-select"}),
            "academic_session": forms.Select(attrs={"class": "form-select"}),
            "room_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Science Block Room 204"}),
            "capacity": forms.NumberInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ClassEnrollmentForm(forms.ModelForm):
    class Meta:
        model = ClassEnrollment
        fields = ["student", "classroom", "roll_number"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "roll_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 10A-01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["student"].queryset = User.objects.filter(role=Role.STUDENT).order_by("username")


class TeacherAssignmentForm(forms.ModelForm):
    class Meta:
        model = TeacherAssignment
        fields = ["teacher", "classroom", "subject_name"]
        widgets = {
            "teacher": forms.Select(attrs={"class": "form-select"}),
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "subject_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Mathematics"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = User.objects.filter(role=Role.TEACHER).order_by("username")


class AttendancePolicyForm(forms.ModelForm):
    class Meta:
        model = AttendancePolicy
        fields = ["name", "minimum_required_percentage", "present_weight", "late_weight", "excused_weight", "absent_weight"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "minimum_required_percentage": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "present_weight": forms.NumberInput(attrs={"class": "form-control", "step": "0.05"}),
            "late_weight": forms.NumberInput(attrs={"class": "form-control", "step": "0.05"}),
            "excused_weight": forms.NumberInput(attrs={"class": "form-control", "step": "0.05"}),
            "absent_weight": forms.NumberInput(attrs={"class": "form-control", "step": "0.05"}),
        }


class AttendanceCorrectionForm(forms.ModelForm):
    class Meta:
        model = AttendanceCorrectionRequest
        fields = ["requested_status", "reason", "supporting_document"]
        widgets = {
            "requested_status": forms.Select(attrs={"class": "form-select"}),
            "reason": forms.Textarea(attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Explain the reason (medical excuse, approved school duty, or attendance clerical mistake)...",
            }),
            "supporting_document": forms.FileInput(attrs={"class": "form-control"}),
        }


class CorrectionReviewForm(forms.Form):
    decision = forms.ChoiceField(
        choices=[
            ("approved", "Approve & Update Attendance Record"),
            ("rejected", "Reject Request"),
        ],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        initial="approved",
    )
    review_notes = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Administrative review explanation"}),
    )

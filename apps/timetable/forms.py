"""
EduConnect Timetable Forms.
"""

from django import forms
from django.contrib.auth import get_user_model
from apps.accounts.models import Role
from apps.attendance.models import ClassRoom
from .models import TimetableSlot, ScheduleStatus, DayOfWeek
from .services import validate_timetable_conflicts

User = get_user_model()


class TimetableSlotForm(forms.ModelForm):
    class Meta:
        model = TimetableSlot
        fields = [
            "classroom",
            "subject_name",
            "teacher",
            "room_number",
            "day_of_week",
            "start_time",
            "end_time",
            "status",
            "cancellation_reason",
            "is_published",
        ]
        widgets = {
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "subject_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Advanced Calculus"}),
            "teacher": forms.Select(attrs={"class": "form-select"}),
            "room_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Science Block Room 204"}),
            "day_of_week": forms.Select(attrs={"class": "form-select"}),
            "start_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "cancellation_reason": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Optional cancellation rationale"}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["teacher"].queryset = User.objects.filter(role=Role.TEACHER).order_by("username")
        self.fields["classroom"].queryset = ClassRoom.objects.filter(is_active=True).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        classroom = cleaned_data.get("classroom")
        teacher = cleaned_data.get("teacher")
        room_number = cleaned_data.get("room_number", "")
        day_of_week = cleaned_data.get("day_of_week")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        status = cleaned_data.get("status")

        if start_time and end_time and start_time >= end_time:
            self.add_error("end_time", "Class end time must be after start time.")

        # Server-side conflict check if not cancelled
        if classroom and teacher and day_of_week and start_time and end_time and status != ScheduleStatus.CANCELLED:
            try:
                validate_timetable_conflicts(
                    classroom=classroom,
                    teacher=teacher,
                    room_number=room_number,
                    day_of_week=day_of_week,
                    start_time=start_time,
                    end_time=end_time,
                    exclude_slot_id=self.instance.id if self.instance else None,
                )
            except forms.ValidationError as e:
                self.add_error(None, e.message)

        return cleaned_data


class CancelSlotForm(forms.Form):
    cancellation_reason = forms.CharField(
        widget=forms.Textarea(attrs={
            "class": "form-control",
            "rows": 3,
            "placeholder": "Explain the reason for class cancellation (e.g. Faculty medical leave, institutional convocation)...",
        }),
        help_text="Required notification message sent to all enrolled students and parents.",
    )

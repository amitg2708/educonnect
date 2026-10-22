"""
Forms for EduConnect Notifications & Announcements Module.
"""

from django import forms

from apps.attendance.models import ClassRoom
from apps.academics.models import Batch
from apps.notifications.models import Announcement, TargetRole


class AnnouncementForm(forms.ModelForm):
    """
    Form for administrators to create and target institutional announcements.
    """

    class Meta:
        model = Announcement
        fields = [
            "title",
            "content",
            "target_role",
            "target_classroom",
            "target_batch",
            "publish_date",
            "expiry_date",
            "attachment",
            "is_published",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Notice title"}),
            "content": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Announcement content and details...",
                }
            ),
            "target_role": forms.Select(attrs={"class": "form-select"}),
            "target_classroom": forms.Select(attrs={"class": "form-select"}),
            "target_batch": forms.Select(attrs={"class": "form-select"}),
            "publish_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "expiry_date": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["target_classroom"].queryset = ClassRoom.objects.filter(is_active=True)
        self.fields["target_classroom"].required = False
        self.fields["target_batch"].queryset = Batch.objects.filter(status=Batch.Status.ONGOING)
        self.fields["target_batch"].required = False
        self.fields["expiry_date"].required = False
        self.fields["attachment"].required = False


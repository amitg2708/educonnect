"""
Forms for EduConnect Complaint & Request Management Module.
"""

from django import forms

from apps.accounts.models import Role, User
from apps.complaints.models import (
    ComplaintCategory,
    ComplaintTicket,
    TicketComment,
    TicketPriority,
    TicketStatus,
)


class ComplaintTicketForm(forms.ModelForm):
    """
    Form for students and parents to lodge a new complaint or service request.
    """

    class Meta:
        model = ComplaintTicket
        fields = ["category", "subject", "description", "priority", "attachment"]
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "Brief issue summary"}),
            "description": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Provide detailed explanation of the issue, dates, and relevant context...",
                }
            ),
            "priority": forms.Select(attrs={"class": "form-select"}),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = ComplaintCategory.objects.filter(is_active=True)


class TicketCommentForm(forms.ModelForm):
    """
    Form for adding public comments and supporting documents.
    """

    class Meta:
        model = TicketComment
        fields = ["message", "attachment"]
        widgets = {
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Type your message or response...",
                }
            ),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
        }


class StaffInternalNoteForm(forms.Form):
    """
    Staff-only form for adding private internal notes.
    """

    message = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Internal staff note (strictly hidden from students/parents)...",
            }
        ),
        required=True,
    )
    attachment = forms.FileField(
        required=False,
        widget=forms.FileInput(attrs={"class": "form-control"}),
    )


class TicketStatusUpdateForm(forms.Form):
    """
    Staff form for updating complaint ticket status.
    """

    status = forms.ChoiceField(
        choices=TicketStatus.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    resolution_details = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Summary of actions taken and resolution details...",
            }
        ),
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Optional transition remarks or rationale",
            }
        ),
    )


class ReopenTicketForm(forms.Form):
    """
    Form for submitter to reopen a resolved ticket.
    """

    reason = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Explain why this resolution did not satisfy the issue...",
            }
        ),
        required=True,
    )


class TicketFeedbackForm(forms.ModelForm):
    """
    Form for submitter to rate resolution satisfaction.
    """

    class Meta:
        model = ComplaintTicket
        fields = ["satisfaction_rating", "feedback_comment"]
        widgets = {
            "satisfaction_rating": forms.Select(attrs={"class": "form-select"}),
            "feedback_comment": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Share any comments on how our staff handled this request...",
                }
            ),
        }


class AssignTicketForm(forms.Form):
    """
    Form to assign ticket to a specific staff member.
    """

    assigned_to = forms.ModelChoiceField(
        queryset=User.objects.filter(role__in=[Role.ADMIN, Role.ACCOUNTS, Role.TEACHER], is_active=True),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

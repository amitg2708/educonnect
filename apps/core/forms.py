"""
Public contact and admissions inquiry forms.
"""

from django import forms
from .models import ContactInquiry, AdmissionInquiry


class ContactForm(forms.ModelForm):
    """
    Public contact inquiry form with Bootstrap 5 widgets.
    """

    class Meta:
        model = ContactInquiry
        fields = ["name", "email", "phone", "subject", "message"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Your Full Name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "name@example.com"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+1 (555) 000-0000"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "Inquiry Subject"}),
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "How can we assist you?"}),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if len(name) < 2:
            raise forms.ValidationError("Please provide a valid full name (at least 2 characters).")
        return name

    def clean_message(self):
        message = self.cleaned_data.get("message", "").strip()
        if len(message) < 10:
            raise forms.ValidationError("Message must be at least 10 characters long.")
        return message


class AdmissionInquiryForm(forms.ModelForm):
    """
    Public admissions application inquiry form.
    """

    class Meta:
        model = AdmissionInquiry
        fields = ["applicant_name", "email", "phone", "target_program", "prior_school", "comments"]
        widgets = {
            "applicant_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Student's Full Name"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "guardian_or_applicant@example.com"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+1 (555) 000-0000"}),
            "target_program": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Grade 10 or B.Sc. Computer Science"}),
            "prior_school": forms.TextInput(attrs={"class": "form-control", "placeholder": "Current / Previous School or College"}),
            "comments": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Special academic interests, achievements, or requirements"}),
        }

"""
Forms for EduConnect Academics & Subject Teacher Module.
"""

from decimal import Decimal
from django import forms
from django.db import models
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.academics.models import (
    Assessment,
    AssessmentType,
    Assignment,
    AssignmentSubmission,
    Batch,
    BatchEnrollment,
    BatchSchedule,
    BatchTeacherAssignment,
    StudentAssessmentScore,
    StudentDoubt,
    StudyMaterial,
    Subject,
)
from apps.attendance.models import AcademicSession, ClassEnrollment, ClassRoom, TeacherAssignment
from apps.core.models import Course
from apps.institutions.models import Branch, Institution, InstitutionMembership


class StudyMaterialForm(forms.ModelForm):
    """
    Form for subject faculty to upload lecture notes and study resources.
    """

    class Meta:
        model = StudyMaterial
        fields = ["classroom", "subject_name", "title", "description", "file"]
        widgets = {
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "subject_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Mathematics"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Material title"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Overview of materials..."}),
            "file": forms.FileInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher and getattr(teacher, "role", None) == Role.TEACHER:
            assigned_classrooms = TeacherAssignment.objects.filter(
                teacher=teacher, is_active=True
            ).values_list("classroom_id", flat=True)
            self.fields["classroom"].queryset = ClassRoom.objects.filter(id__in=assigned_classrooms, is_active=True)


class AssignmentForm(forms.ModelForm):
    """
    Form for subject faculty to create coursework assignments.
    """

    class Meta:
        model = Assignment
        fields = [
            "classroom",
            "subject_name",
            "title",
            "description",
            "attachment",
            "max_score",
            "due_datetime",
            "is_published",
        ]
        widgets = {
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "subject_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Physics"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Assignment Title"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Detailed instructions..."}),
            "attachment": forms.FileInput(attrs={"class": "form-control"}),
            "max_score": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "min": "1"}),
            "due_datetime": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher and getattr(teacher, "role", None) == Role.TEACHER:
            assigned_classrooms = TeacherAssignment.objects.filter(
                teacher=teacher, is_active=True
            ).values_list("classroom_id", flat=True)
            self.fields["classroom"].queryset = ClassRoom.objects.filter(id__in=assigned_classrooms, is_active=True)


class AssignmentSubmissionForm(forms.ModelForm):
    """
    Form for students to submit completed coursework.
    """

    class Meta:
        model = AssignmentSubmission
        fields = ["submission_file", "notes"]
        widgets = {
            "submission_file": forms.FileInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Additional comments or notes about your submission...",
                }
            ),
        }


class SubmissionGradingForm(forms.ModelForm):
    """
    Form for faculty to grade an assignment submission.
    """

    class Meta:
        model = AssignmentSubmission
        fields = ["score", "feedback"]
        widgets = {
            "score": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "min": "0"}),
            "feedback": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Teacher feedback, corrections, or praise...",
                }
            ),
        }


class AssessmentForm(forms.ModelForm):
    """
    Form for creating examinations, tests, or quizzes.
    """

    class Meta:
        model = Assessment
        fields = [
            "classroom",
            "subject_name",
            "title",
            "assessment_type",
            "max_marks",
            "weightage_percent",
            "date_conducted",
        ]
        widgets = {
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "subject_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Chemistry"}),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Unit 3 Test"}),
            "assessment_type": forms.Select(attrs={"class": "form-select"}),
            "max_marks": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "1"}),
            "weightage_percent": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "min": "0", "max": "100"}),
            "date_conducted": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher and getattr(teacher, "role", None) == Role.TEACHER:
            assigned_classrooms = TeacherAssignment.objects.filter(
                teacher=teacher, is_active=True
            ).values_list("classroom_id", flat=True)
            self.fields["classroom"].queryset = ClassRoom.objects.filter(id__in=assigned_classrooms, is_active=True)


class StudentScoreForm(forms.ModelForm):
    """
    Form for recording an individual student's marks.
    """

    class Meta:
        model = StudentAssessmentScore
        fields = ["marks_obtained", "teacher_remarks"]
        widgets = {
            "marks_obtained": forms.NumberInput(attrs={"class": "form-control", "step": "0.5", "min": "0"}),
            "teacher_remarks": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional remarks"}),
        }


class StudentDoubtForm(forms.ModelForm):
    """
    Form for enrolled students to ask real academic questions to their teachers.
    """

    class Meta:
        model = StudentDoubt
        fields = ["classroom", "subject_name", "assigned_teacher", "question_title", "question_text"]
        widgets = {
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "subject_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Subject name"}),
            "assigned_teacher": forms.Select(attrs={"class": "form-select"}),
            "question_title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Brief title of your question"}),
            "question_text": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Describe what you need help with in detail...",
                }
            ),
        }

    def __init__(self, *args, student=None, **kwargs):
        super().__init__(*args, **kwargs)
        if student:
            enrolled_classroom_ids = ClassEnrollment.objects.filter(
                student=student, is_active=True
            ).values_list("classroom_id", flat=True)
            self.fields["classroom"].queryset = ClassRoom.objects.filter(id__in=enrolled_classroom_ids, is_active=True)
            # Limit assigned_teacher to active teachers
            self.fields["assigned_teacher"].queryset = User.objects.filter(role=Role.TEACHER, is_active=True)


class TeacherDoubtReplyForm(forms.Form):
    """
    Form for assigned faculty to submit an answer to a student question.
    """

    answer_text = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 4,
                "placeholder": "Provide your explanation or guidance here...",
            }
        ),
        required=True,
    )


# ============================================================================
# COACHING BATCHES & ENROLMENT FORMS (TASK 2)
# ============================================================================


class CourseCatalogueForm(forms.ModelForm):
    """
    Form to create or update courses in the coaching curriculum catalogue.
    Supports tuition (Classes 5-10), junior college (Classes 11-12), streams,
    competitive entrance exams, and board preparation.
    """

    class Meta:
        model = Course
        fields = [
            "title",
            "code",
            "category",
            "target_class",
            "stream",
            "board",
            "examination_scheme",
            "department",
            "level",
            "duration",
            "fee_per_term",
            "fee_period",
            "description",
            "eligibility",
            "syllabus_overview",
            "is_active",
            "is_featured",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Class 10 Science & Math Foundation"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. TUITION-C10"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "target_class": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Class 10, Class 11, Class 12"}),
            "stream": forms.Select(attrs={"class": "form-select"}),
            "board": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. CBSE, ICSE, State Board, IB"}),
            "examination_scheme": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Board Exams, JEE Main, NEET"}),
            "department": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Secondary Education"}),
            "level": forms.Select(attrs={"class": "form-select"}),
            "duration": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 1 Year, 6 Months"}),
            "fee_per_term": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "fee_period": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Per Month, Per Term, Full Course"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Comprehensive course description..."}),
            "eligibility": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Prerequisite qualifications..."}),
            "syllabus_overview": forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Key topics covered..."}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_featured": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, institution=None, **kwargs):
        self.institution = institution
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.institution and not instance.institution:
            instance.institution = self.institution
        if commit:
            instance.save()
        return instance


class SubjectForm(forms.ModelForm):
    """
    Form to configure subjects offered by a coaching institute.
    """

    class Meta:
        model = Subject
        fields = ["name", "code", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Physics, Accountancy"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. PHY, ACC"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Subject syllabus details..."}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, institution=None, **kwargs):
        self.institution = institution
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if self.institution:
            qs = Subject.objects.filter(institution=self.institution, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Subject code '{code}' already exists for this institute.")
        return code

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.institution and not instance.institution:
            instance.institution = self.institution
        instance.code = instance.code.strip().upper()
        if commit:
            instance.save()
        return instance


class BatchForm(forms.ModelForm):
    """
    Form to create or update an operational coaching cohort (Batch).
    Enforces tenant branch isolation, academic session, capacity, and waitlist configuration.
    """

    class Meta:
        model = Batch
        fields = [
            "name",
            "code",
            "course",
            "branch",
            "academic_session",
            "classroom",
            "target_class",
            "stream",
            "board",
            "start_date",
            "end_date",
            "capacity",
            "enable_waitlist",
            "max_waitlist_capacity",
            "fee_override",
            "status",
            "notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Class 10 CBSE Math & Science - Evening A"}),
            "code": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. BAT-C10-01"}),
            "course": forms.Select(attrs={"class": "form-select"}),
            "branch": forms.Select(attrs={"class": "form-select"}),
            "academic_session": forms.Select(attrs={"class": "form-select"}),
            "classroom": forms.Select(attrs={"class": "form-select"}),
            "target_class": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Class 10"}),
            "stream": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Science, Commerce, Arts, General"}),
            "board": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. CBSE, ICSE, State Board"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "capacity": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "enable_waitlist": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "max_waitlist_capacity": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "fee_override": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "placeholder": "Leave empty for course fee"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Operational notes or timing remarks..."}),
        }

    def __init__(self, *args, institution=None, **kwargs):
        self.institution = institution
        super().__init__(*args, **kwargs)

        if self.institution:
            self.fields["course"].queryset = Course.objects.filter(
                models.Q(institution=self.institution) | models.Q(institution__isnull=True),
                is_active=True,
            )
            self.fields["branch"].queryset = Branch.objects.filter(institution=self.institution, is_active=True)
            self.fields["academic_session"].queryset = AcademicSession.objects.filter(
                models.Q(institution=self.institution) | models.Q(institution__isnull=True)
            )
            self.fields["classroom"].queryset = ClassRoom.objects.filter(is_active=True)
            self.fields["branch"].required = False
            self.fields["classroom"].required = False

    def clean_code(self):
        code = self.cleaned_data.get("code", "").strip().upper()
        if self.institution:
            qs = Batch.objects.filter(institution=self.institution, code=code)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"Batch code '{code}' is already used in this institute.")
        return code

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.institution and not instance.institution:
            instance.institution = self.institution
        instance.code = instance.code.strip().upper()
        if commit:
            instance.save()
        return instance


class BatchScheduleForm(forms.ModelForm):
    """
    Form to schedule a weekly timetable slot for a coaching batch.
    """

    class Meta:
        model = BatchSchedule
        fields = ["day_of_week", "start_time", "end_time", "subject", "teacher", "room_number"]
        widgets = {
            "day_of_week": forms.Select(attrs={"class": "form-select"}),
            "start_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": "form-control", "type": "time"}),
            "subject": forms.Select(attrs={"class": "form-select"}),
            "teacher": forms.Select(attrs={"class": "form-select"}),
            "room_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. Room 102, Lab B"}),
        }

    def __init__(self, *args, batch=None, **kwargs):
        self.batch = batch
        super().__init__(*args, **kwargs)

        if self.batch:
            inst = self.batch.institution
            self.fields["subject"].queryset = Subject.objects.filter(
                models.Q(institution=inst) | models.Q(institution__isnull=True),
                is_active=True,
            )
            # Find teachers belonging to this institute
            membership_user_ids = InstitutionMembership.objects.filter(
                institution=inst,
                role=Role.TEACHER,
                is_active=True,
            ).values_list("user_id", flat=True)
            self.fields["teacher"].queryset = User.objects.filter(
                models.Q(id__in=membership_user_ids) | models.Q(institution=inst, role=Role.TEACHER),
                is_active=True,
            ).distinct()
            self.fields["subject"].required = False
            self.fields["teacher"].required = False

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_time")
        end = cleaned_data.get("end_time")
        if start and end and start >= end:
            self.add_error("end_time", "End time must be later than start time.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.batch and not instance.batch_id:
            instance.batch = self.batch
        if commit:
            instance.save()
        return instance


class BatchTeacherAssignmentForm(forms.ModelForm):
    """
    Form to assign a Subject Teacher to a Batch for a specific subject.
    """

    class Meta:
        model = BatchTeacherAssignment
        fields = ["teacher", "subject", "is_primary"]
        widgets = {
            "teacher": forms.Select(attrs={"class": "form-select"}),
            "subject": forms.Select(attrs={"class": "form-select"}),
            "is_primary": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, batch=None, **kwargs):
        self.batch = batch
        super().__init__(*args, **kwargs)

        if self.batch:
            inst = self.batch.institution
            self.fields["subject"].queryset = Subject.objects.filter(
                models.Q(institution=inst) | models.Q(institution__isnull=True),
                is_active=True,
            )
            membership_user_ids = InstitutionMembership.objects.filter(
                institution=inst,
                role=Role.TEACHER,
                is_active=True,
            ).values_list("user_id", flat=True)
            self.fields["teacher"].queryset = User.objects.filter(
                models.Q(id__in=membership_user_ids) | models.Q(institution=inst, role=Role.TEACHER),
                is_active=True,
            ).distinct()

    def clean(self):
        cleaned_data = super().clean()
        teacher = cleaned_data.get("teacher")
        subject = cleaned_data.get("subject")
        if self.batch and teacher and subject:
            qs = BatchTeacherAssignment.objects.filter(
                batch=self.batch,
                teacher=teacher,
                subject=subject,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("This teacher is already assigned to this subject in this batch.")
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.batch and not instance.batch_id:
            instance.batch = self.batch
        if commit:
            instance.save()
        return instance


class BatchEnrollmentForm(forms.ModelForm):
    """
    Form for enrolling a student into a coaching batch.
    Validates capacity, waitlisting, duplicate active enrolments, and institute scoping.
    """

    force_waitlist = forms.BooleanField(
        required=False,
        label="Add to Waitlist directly",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = BatchEnrollment
        fields = ["student", "roll_number", "start_date", "notes"]
        widgets = {
            "student": forms.Select(attrs={"class": "form-select"}),
            "roll_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional roll number"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "Admission notes, remarks..."}),
        }

    def __init__(self, *args, batch=None, **kwargs):
        self.batch = batch
        super().__init__(*args, **kwargs)

        if self.batch:
            inst = self.batch.institution
            membership_student_ids = InstitutionMembership.objects.filter(
                institution=inst,
                role=Role.STUDENT,
                is_active=True,
            ).values_list("user_id", flat=True)
            self.fields["student"].queryset = User.objects.filter(
                models.Q(id__in=membership_student_ids) | models.Q(institution=inst, role=Role.STUDENT),
                is_active=True,
            ).distinct()
            self.fields["start_date"].initial = timezone.now().date()


class BatchTransferForm(forms.Form):
    """
    Form to transfer an enrolled student from one batch to another within the institute.
    """

    target_batch = forms.ModelChoiceField(
        queryset=Batch.objects.none(),
        label="Target Batch",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Reason for student transfer (e.g. Schedule adjustment, stream change, branch relocation)...",
            }
        ),
        required=False,
    )

    def __init__(self, *args, current_enrollment=None, **kwargs):
        self.current_enrollment = current_enrollment
        super().__init__(*args, **kwargs)

        if self.current_enrollment:
            inst = self.current_enrollment.institution
            self.fields["target_batch"].queryset = Batch.objects.filter(
                institution=inst,
                status__in=[Batch.Status.UPCOMING, Batch.Status.ONGOING],
            ).exclude(pk=self.current_enrollment.batch_id)


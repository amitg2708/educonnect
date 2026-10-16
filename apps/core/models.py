"""
Public Portal Content and Inquiry Models for EduConnect.
Database-backed models for courses, achievements, gallery, announcements,
facilities, and public inquiries.
"""

from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Course(models.Model):
    """
    Academic program and curriculum offerings.
    """

    class Level(models.TextChoices):
        SECONDARY = "secondary", "Secondary Education (Grades 9-12)"
        UNDERGRADUATE = "undergraduate", "Undergraduate Degree"
        POSTGRADUATE = "postgraduate", "Postgraduate / Master's"
        DIPLOMA = "diploma", "Professional Certificate & Diploma"

    title = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, help_text="Unique course code e.g. CS-101")
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    department = models.CharField(max_length=120)
    level = models.CharField(max_length=30, choices=Level.choices, default=Level.UNDERGRADUATE)
    duration = models.CharField(max_length=60, help_text="e.g. 4 Years / 8 Semesters")
    description = models.TextField()
    eligibility = models.TextField(blank=True, help_text="Academic criteria and prerequisite requirements.")
    syllabus_overview = models.TextField(blank=True, help_text="Key learning modules and milestones.")
    fee_per_term = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    image = models.ImageField(upload_to="courses/", blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Course / Program"
        verbose_name_plural = "Courses / Programs"
        ordering = ["code"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.code}-{self.title}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code}: {self.title} ({self.get_level_display()})"


class Achievement(models.Model):
    """
    Institutional, student, and faculty recognitions.
    """

    class Category(models.TextChoices):
        ACADEMIC = "academic", "Academic & Olympiad Honors"
        SPORTS = "sports", "Athletics & Sports Championships"
        RESEARCH = "research", "Innovation & Science Fairs"
        ARTS = "arts", "Cultural, Debating & Arts"
        ACCREDITATION = "accreditation", "Institutional Accreditations"

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=40, choices=Category.choices, default=Category.ACADEMIC)
    year = models.PositiveIntegerField(default=2026)
    recipient = models.CharField(max_length=200, blank=True, help_text="Individual, team, or department awarded.")
    description = models.TextField()
    image = models.ImageField(upload_to="achievements/", blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Achievement"
        verbose_name_plural = "Achievements"
        ordering = ["-year", "-created_at"]

    def __str__(self):
        return f"{self.title} ({self.year}) - {self.get_category_display()}"


class GalleryItem(models.Model):
    """
    Campus facilities, laboratories, and event photo gallery.
    """

    class Category(models.TextChoices):
        CAMPUS = "campus", "Campus & Architecture"
        LABS = "labs", "Modern STEM Laboratories"
        LIBRARY = "library", "Digital Library & Study Hubs"
        SPORTS = "sports", "Sports Arenas & Gymnasium"
        EVENTS = "events", "Convocations & Annual Events"

    title = models.CharField(max_length=200)
    category = models.CharField(max_length=40, choices=Category.choices, default=Category.CAMPUS)
    caption = models.TextField(blank=True)
    image = models.ImageField(upload_to="gallery/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Gallery Item"
        verbose_name_plural = "Gallery Items"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} [{self.get_category_display()}]"


class Announcement(models.Model):
    """
    Official announcements and notifications.
    """

    class Priority(models.TextChoices):
        STANDARD = "standard", "Standard Announcement"
        HIGH = "high", "High Priority"
        URGENT = "urgent", "Urgent Alert"

    class Category(models.TextChoices):
        GENERAL = "general", "General Institution"
        ACADEMIC = "academic", "Academic Calendar"
        EXAMS = "exams", "Examinations"
        ADMISSIONS = "admissions", "Admissions"
        EVENTS = "events", "Campus Events"

    title = models.CharField(max_length=255)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.GENERAL)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.STANDARD)
    content = models.TextField()
    publish_date = models.DateField(default=timezone.now)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"
        ordering = ["-publish_date", "-created_at"]

    def __str__(self):
        return f"[{self.get_priority_display()}] {self.title}"


class Facility(models.Model):
    """
    Key campus infrastructure items highlighted on public pages.
    """

    title = models.CharField(max_length=150)
    category = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.CharField(max_length=60, default="bi-building", help_text="Bootstrap Icons class (e.g. bi-cpu, bi-book)")
    display_order = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Campus Facility"
        verbose_name_plural = "Campus Facilities"
        ordering = ["display_order", "title"]

    def __str__(self):
        return f"{self.title} ({self.category})"


class ContactInquiry(models.Model):
    """
    Public inquiries submitted via the Contact Us page.
    """

    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Contact Inquiry"
        verbose_name_plural = "Contact Inquiries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.subject} - {self.name} ({self.email})"


class AdmissionInquiry(models.Model):
    """
    Admissions applications and prospective student inquiries.
    """

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Application Received"
        UNDER_REVIEW = "under_review", "Under Review"
        INTERVIEW = "interview", "Interview / Assessment Scheduled"
        ACCEPTED = "accepted", "Admissions Offer Extended"
        WAITLISTED = "waitlisted", "Waitlisted"
        REJECTED = "rejected", "Not Accepted"

    applicant_name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30)
    target_program = models.CharField(max_length=150, help_text="Intended grade or academic course")
    prior_school = models.CharField(max_length=200, blank=True, help_text="Previous institution attended")
    comments = models.TextField(blank=True, help_text="Academic interests or special qualifications")
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SUBMITTED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Admission Inquiry"
        verbose_name_plural = "Admission Inquiries"
        ordering = ["-created_at"]

    def __str__(self):
        return f"App: {self.applicant_name} -> {self.target_program} [{self.get_status_display()}]"

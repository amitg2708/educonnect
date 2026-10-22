"""
EduConnect Notifications, Announcements & Parent Portal Automated Test Suite.
Tests:
- Database-backed in-app notifications
- Atomic deduplication keys preventing duplicate alert spam
- Read receipt updates and unread counts
- Campus announcement role & classroom targeting and expiry windows
- Automated event notifications (absence alerts & fee due reminders)
- Parent-child link verification and strict data isolation
- Confidentiality of unpublished assessment marks in Parent Portal
"""

from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentStudentLink, Role
from apps.attendance.models import (
    AcademicSession,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    ClassEnrollment,
    ClassRoom,
    TeacherAssignment,
)
from apps.academics.models import Assessment, AssessmentType, StudentAssessmentScore
from apps.fees.models import FeeCategory, FeeStructure, FeeStructureItem, StudentFeeAllocation, FeeInstallment
from apps.notifications.models import (
    Announcement,
    Notification,
    NotificationCategory,
    TargetRole,
)
from apps.notifications.services import (
    get_user_announcements,
    get_user_unread_count,
    mark_all_notifications_as_read,
    mark_notification_as_read,
    notify_absence_alert,
    notify_fee_due_alert,
    send_notification,
)

User = get_user_model()


class NotificationAndParentPortalTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin = User.objects.create_superuser(
            username="admin_notif",
            email="admin_notif@educonnect.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
        )
        self.teacher = User.objects.create_user(
            username="prof_faraday",
            email="faraday@educonnect.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            employee_id="FAC-FARADAY",
        )
        self.student1 = User.objects.create_user(
            username="stud_emma",
            email="emma@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            first_name="Emma",
            last_name="Watson",
        )
        self.student2 = User.objects.create_user(
            username="stud_liam",
            email="liam@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            first_name="Liam",
            last_name="Watson",
        )
        self.unrelated_student = User.objects.create_user(
            username="stud_stranger",
            email="stranger@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            first_name="Stranger",
            last_name="Danger",
        )

        # Parents
        self.parent = User.objects.create_user(
            username="parent_watson",
            email="watson_parent@gmail.com",
            password="TestPassword123!",
            role=Role.PARENT,
            first_name="Arthur",
            last_name="Watson",
        )
        self.unrelated_parent = User.objects.create_user(
            username="parent_other",
            email="other_parent@gmail.com",
            password="TestPassword123!",
            role=Role.PARENT,
        )

        # Authorized links: Parent Watson is father to Emma and Liam
        ParentStudentLink.objects.create(
            parent=self.parent,
            student=self.student1,
            relationship_type="father",
            is_authorized=True,
        )
        ParentStudentLink.objects.create(
            parent=self.parent,
            student=self.student2,
            relationship_type="father",
            is_authorized=True,
        )

        # Session & Classrooms
        self.session = AcademicSession.objects.create(
            name="Session 2026-2027",
            start_date=timezone.now().date() - timedelta(days=20),
            end_date=timezone.now().date() + timedelta(days=280),
            is_current=True,
        )
        self.class10a = ClassRoom.objects.create(
            name="Grade 10-A",
            code="G10A",
            academic_session=self.session,
            room_number="R101",
        )
        self.class8b = ClassRoom.objects.create(
            name="Grade 8-B",
            code="G8B",
            academic_session=self.session,
            room_number="R82",
        )

        # Enrollments
        ClassEnrollment.objects.create(student=self.student1, classroom=self.class10a, is_active=True)
        ClassEnrollment.objects.create(student=self.student2, classroom=self.class8b, is_active=True)

    def test_notification_dispatch_and_deduplication(self):
        """Notification dispatch works; deduplication key prevents repeated spam."""
        # 1. First alert
        n1 = send_notification(
            recipient=self.student1,
            title="Lab Exam Schedule",
            message="Your chemistry lab exam is on Friday.",
            category=NotificationCategory.ACADEMICS,
            deduplication_key="exam-chem-101-emma",
        )
        self.assertIsNotNone(n1)
        self.assertEqual(Notification.objects.filter(recipient=self.student1).count(), 1)

        # 2. Duplicate dispatch attempt with same key
        n2 = send_notification(
            recipient=self.student1,
            title="Lab Exam Schedule (Repeated)",
            message="Your chemistry lab exam is on Friday.",
            category=NotificationCategory.ACADEMICS,
            deduplication_key="exam-chem-101-emma",
        )
        # Must return None and NOT create a second record
        self.assertIsNone(n2)
        self.assertEqual(Notification.objects.filter(recipient=self.student1).count(), 1)

    def test_notification_read_receipts(self):
        """Test marking individual and all notifications as read."""
        send_notification(self.student1, "Alert 1", "Msg 1")
        send_notification(self.student1, "Alert 2", "Msg 2")
        self.assertEqual(get_user_unread_count(self.student1), 2)

        # Mark single read
        n1 = Notification.objects.filter(recipient=self.student1).first()
        mark_notification_as_read(n1.id, self.student1)
        self.assertEqual(get_user_unread_count(self.student1), 1)

        # User cannot mark another's alert as read
        with self.assertRaises(PermissionDenied):
            mark_notification_as_read(n1.id, self.student2)

        # Mark all read
        mark_all_notifications_as_read(self.student1)
        self.assertEqual(get_user_unread_count(self.student1), 0)

    def test_announcement_targeting_and_expiry(self):
        """Announcements target roles/classrooms and obey validity windows."""
        now = timezone.now()

        # 1. Campus-wide active notice
        a_all = Announcement.objects.create(
            title="Annual Sports Day",
            content="Sports Day will be held next Monday.",
            target_role=TargetRole.ALL,
            published_by=self.admin,
            publish_date=now - timedelta(days=1),
            is_published=True,
        )

        # 2. Parent-only notice
        a_parent = Announcement.objects.create(
            title="PTA Meeting",
            content="PTA general body meeting this Saturday.",
            target_role=TargetRole.PARENT,
            published_by=self.admin,
            publish_date=now - timedelta(hours=2),
            is_published=True,
        )

        # 3. Class 10A specific notice
        a_class10 = Announcement.objects.create(
            title="Grade 10 Field Trip",
            content="Trip to the Science Museum.",
            target_role=TargetRole.STUDENT,
            target_classroom=self.class10a,
            published_by=self.admin,
            publish_date=now - timedelta(hours=1),
            is_published=True,
        )

        # 4. Expired notice
        a_expired = Announcement.objects.create(
            title="Old Holiday Circular",
            content="Yesterday campus was closed.",
            target_role=TargetRole.ALL,
            published_by=self.admin,
            publish_date=now - timedelta(days=10),
            expiry_date=now - timedelta(days=1),
            is_published=True,
        )

        # Parent Watson should see: Sports Day and PTA Meeting; should NOT see Class10 student trip or expired notice
        parent_notices = get_user_announcements(self.parent)
        self.assertIn(a_all, parent_notices)
        self.assertIn(a_parent, parent_notices)
        self.assertNotIn(a_expired, parent_notices)

        # Student Emma (Grade 10A) should see: Sports Day and Grade 10 trip; should NOT see PTA Meeting
        student_notices = get_user_announcements(self.student1)
        self.assertIn(a_all, student_notices)
        self.assertIn(a_class10, student_notices)
        self.assertNotIn(a_parent, student_notices)
        self.assertNotIn(a_expired, student_notices)

    def test_automated_absence_alert_dispatcher(self):
        """Absence notification alerts both student and authorized linked parents."""
        session_date = timezone.now().date()
        notify_absence_alert(
            student=self.student1,
            session_date=session_date,
            subject_name="Physics",
            classroom_name="Grade 10-A",
        )

        # Student receives alert
        student_alerts = Notification.objects.filter(recipient=self.student1, category=NotificationCategory.ATTENDANCE)
        self.assertEqual(student_alerts.count(), 1)
        self.assertIn("Physics", student_alerts.first().title)

        # Linked parent receives alert
        parent_alerts = Notification.objects.filter(recipient=self.parent, category=NotificationCategory.ATTENDANCE)
        self.assertEqual(parent_alerts.count(), 1)
        self.assertIn("Emma", parent_alerts.first().title)

        # Unrelated parent receives NO alert
        self.assertEqual(Notification.objects.filter(recipient=self.unrelated_parent).count(), 0)

    def test_automated_fee_due_alert_dispatcher(self):
        """Fee due notification alerts student and linked parents."""
        due_date = timezone.now().date() + timedelta(days=5)
        notify_fee_due_alert(
            student=self.student1,
            installment_title="Term 1 Tuition",
            amount=Decimal("1200.00"),
            due_date=due_date,
        )

        self.assertTrue(Notification.objects.filter(recipient=self.student1, category=NotificationCategory.FEES).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.parent, category=NotificationCategory.FEES).exists())

    def test_parent_portal_hub_data_isolation(self):
        """
        Parent Portal Hub verifies parent-child links, enables switching,
        and strictly hides confidential unpublished exam marks.
        """
        # Create published exam score for Emma
        asm_pub = Assessment.objects.create(
            classroom=self.class10a,
            subject_name="English",
            teacher=self.teacher,
            title="English Term Paper",
            max_marks=Decimal("100.00"),
            is_published=True,
        )
        StudentAssessmentScore.objects.create(
            assessment=asm_pub,
            student=self.student1,
            marks_obtained=Decimal("88.00"),
            grade="A",
        )

        # Create confidential unpublished exam score for Emma
        asm_draft = Assessment.objects.create(
            classroom=self.class10a,
            subject_name="History",
            teacher=self.teacher,
            title="History Surprise Quiz",
            max_marks=Decimal("50.00"),
            is_published=False,  # Draft confidential!
        )
        StudentAssessmentScore.objects.create(
            assessment=asm_draft,
            student=self.student1,
            marks_obtained=Decimal("45.00"),
            grade="A",
        )

        # Parent Watson logs into Parent Portal Hub
        self.client.force_login(self.parent)
        res_hub = self.client.get(reverse("notifications:parent_hub"))
        self.assertEqual(res_hub.status_code, 200)

        # Can see Emma's published exam
        self.assertContains(res_hub, "English Term Paper")
        self.assertContains(res_hub, "88.00")

        # Must NOT see History Surprise Quiz (Draft confidential)
        self.assertNotContains(res_hub, "History Surprise Quiz")

        # Switch to Liam
        res_liam = self.client.get(reverse("notifications:parent_hub_child", args=[str(self.student2.id)]))
        self.assertEqual(res_liam.status_code, 200)
        self.assertContains(res_liam, "Liam")

        # Parent cannot access unrelated student stranger
        res_stranger = self.client.get(reverse("notifications:parent_hub_child", args=[str(self.unrelated_student.id)]))
        self.assertEqual(res_stranger.status_code, 404)

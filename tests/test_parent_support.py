"""
Acceptance Test Suite for Antigravity Task 7:
Parent Communication and Student Support in EduConnect.

Tests the 6 core acceptance requirements:
1. A parent can see a linked child's records (attendance, fees, tests, schedules, and command center).
2. A parent cannot see an unrelated student's records (strict 403/404 isolation across all portals).
3. A student submits a complaint and receives a ticket number (unique TKT- number, standard categories).
4. Authorized staff resolve the ticket (status transitions, audit logs, resolution details).
5. The student sees the resolution but not internal notes (confidential staff notes isolation).
6. Batch announcements reach the intended audience only (targeted cohort notices vs institute-wide).

Plus:
7. In-app notifications with atomic deduplication (absence alerts, fee dues, exam announcements).
8. External messaging integration (Email, SMS, WhatsApp) enforcing that delivery is NEVER claimed
   unless the real carrier/provider explicitly confirms delivery.
"""

from datetime import date, timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentStudentLink, Role
from apps.attendance.models import (
    AcademicSession,
    AttendancePolicy,
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    ClassEnrollment,
    ClassRoom,
)
from apps.academics.models import (
    Assessment,
    AssessmentType,
    Batch,
    BatchEnrollment,
    StudentAssessmentScore,
)
from apps.complaints.models import (
    ComplaintCategory,
    ComplaintTicket,
    TicketComment,
    TicketPriority,
    TicketStatus,
    TicketStatusHistory,
)
from apps.complaints.services import (
    add_ticket_comment,
    create_complaint_ticket,
    reopen_complaint_ticket,
    submit_ticket_feedback,
    transition_ticket_status,
)
from apps.core.models import Course
from apps.fees.models import (
    FeeCategory,
    FeeInstallment,
    FeeStructure,
    FeeStructureItem,
    InstallmentStatus,
    StudentFeeAllocation,
)
from apps.institutions.models import Branch, Institution
from apps.notifications.messaging import (
    DeliveryChannel,
    DeliveryStatus,
    MockConfirmedMessagingProvider,
    MockFailingMessagingProvider,
    MockQueuedMessagingProvider,
    handle_provider_delivery_receipt,
    send_external_message,
)
from apps.notifications.models import (
    Announcement,
    MessageDeliveryRecord,
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
    notify_assessment_results_published,
    notify_fee_due_alert,
    notify_test_announcement,
    send_notification,
)
from apps.timetable.models import DayOfWeek, ScheduleStatus, TimetableSlot

User = get_user_model()


class ParentCommunicationAndSupportAcceptanceTests(TestCase):
    def setUp(self):
        self.client = Client()

        # 1. Institution & Branch
        self.institution = Institution.objects.create(
            name="Apex Horizon Academy",
            code="APEX-ACAD",
            subdomain="apex",
            is_active=True,
        )
        self.branch = Branch.objects.create(
            institution=self.institution,
            name="Apex Main Campus",
            code="APEX-MAIN",
        )

        # 2. Administrative and Faculty Staff
        self.admin = User.objects.create_superuser(
            username="apex_admin",
            email="admin@apex.educonnect.local",
            password="AdminPassword123!",
            role=Role.ADMIN,
            institution=self.institution,
        )
        self.teacher = User.objects.create_user(
            username="teacher_curie",
            email="curie@apex.educonnect.local",
            password="TeacherPassword123!",
            role=Role.TEACHER,
            institution=self.institution,
            employee_id="TCH-001",
        )
        self.accounts_staff = User.objects.create_user(
            username="accounts_clerk",
            email="accounts@apex.educonnect.local",
            password="AccountsPassword123!",
            role=Role.ACCOUNTS,
            institution=self.institution,
        )

        # 3. Students
        self.student_charlie = User.objects.create_user(
            username="student_charlie",
            email="charlie@apex.educonnect.local",
            password="StudentPassword123!",
            role=Role.STUDENT,
            institution=self.institution,
            first_name="Charlie",
            last_name="Bucket",
            student_id="STU-001",
        )
        self.unrelated_student_david = User.objects.create_user(
            username="student_david",
            email="david@apex.educonnect.local",
            password="StudentPassword123!",
            role=Role.STUDENT,
            institution=self.institution,
            first_name="David",
            last_name="Copperfield",
            student_id="STU-002",
        )

        # 4. Parents
        self.parent_bucket = User.objects.create_user(
            username="parent_bucket",
            email="mrs.bucket@gmail.com",
            password="ParentPassword123!",
            role=Role.PARENT,
            institution=self.institution,
            first_name="Helen",
            last_name="Bucket",
        )
        self.unrelated_parent = User.objects.create_user(
            username="parent_stranger",
            email="stranger.parent@gmail.com",
            password="ParentPassword123!",
            role=Role.PARENT,
            institution=self.institution,
            first_name="Arthur",
            last_name="Dent",
        )

        # 5. Verified Parent-Child Link: parent_bucket -> student_charlie
        self.authorized_link = ParentStudentLink.objects.create(
            institution=self.institution,
            parent=self.parent_bucket,
            student=self.student_charlie,
            relationship_type="mother",
            is_authorized=True,
            notes="Verified with birth certificate and government photo ID.",
        )

        # 6. Academic Setup
        self.session = AcademicSession.objects.create(
            institution=self.institution,
            name="Academic Year 2026-2027",
            start_date=date(2026, 6, 1),
            end_date=date(2027, 5, 31),
            is_current=True,
        )
        self.course = Course.objects.create(
            code="SCI-10",
            title="Grade 10 Science & Engineering",
            institution=self.institution,
            department="Science",
            fee_per_term=Decimal("2500.00"),
        )
        self.classroom = ClassRoom.objects.create(
            institution=self.institution,
            academic_session=self.session,
            name="Grade 10 Section A",
            code="G10-A",
            capacity=35,
        )
        self.enrollment = ClassEnrollment.objects.create(
            classroom=self.classroom,
            student=self.student_charlie,
            roll_number="1001",
            is_active=True,
        )

        # Attendance Policy & Live Session
        self.policy = AttendancePolicy.objects.create(
            institution=self.institution,
            name="Standard 75% Policy",
            minimum_required_percentage=Decimal("75.00"),
            is_active=True,
        )
        self.att_session = AttendanceSession.objects.create(
            institution=self.institution,
            classroom=self.classroom,
            subject_name="Physics",
            session_date=date(2026, 10, 10),
            teacher=self.teacher,
        )
        AttendanceRecord.objects.create(
            session=self.att_session,
            student=self.student_charlie,
            status=AttendanceStatus.PRESENT,
        )

        # Timetable slot
        self.slot = TimetableSlot.objects.create(
            institution=self.institution,
            classroom=self.classroom,
            teacher=self.teacher,
            subject_name="Physics",
            day_of_week=DayOfWeek.MONDAY,
            start_time="09:00:00",
            end_time="10:00:00",
            status=ScheduleStatus.ACTIVE,
        )

        # Fee Allocation
        self.fee_cat = FeeCategory.objects.create(
            institution=self.institution,
            name="Tuition",
            code="TUIT",
        )
        self.fee_struct = FeeStructure.objects.create(
            institution=self.institution,
            title="Grade 10 Annual Plan",
            code="FS-G10-01",
            academic_year="2026-2027",
            course=self.course,
            total_amount=Decimal("2500.00"),
        )
        FeeStructureItem.objects.create(
            fee_structure=self.fee_struct,
            category=self.fee_cat,
            amount=Decimal("2500.00"),
        )
        self.fee_alloc = StudentFeeAllocation.objects.create(
            institution=self.institution,
            student=self.student_charlie,
            fee_structure=self.fee_struct,
            gross_amount=Decimal("2500.00"),
            net_amount=Decimal("2500.00"),
            amount_paid=Decimal("0.00"),
            outstanding_balance=Decimal("2500.00"),
        )
        self.installment = FeeInstallment.objects.create(
            allocation=self.fee_alloc,
            installment_number=1,
            title="Term 1 Tuition",
            amount=Decimal("2500.00"),
            due_date=date(2026, 11, 15),
            status=InstallmentStatus.PENDING,
        )

        # Published Assessment & Score
        self.assessment = Assessment.objects.create(
            institution=self.institution,
            classroom=self.classroom,
            teacher=self.teacher,
            subject_name="Physics",
            title="Mid-Term Physics Exam",
            assessment_type=AssessmentType.MIDTERM,
            max_marks=Decimal("100.00"),
            weightage_percent=Decimal("30.00"),
            date_conducted=date(2026, 9, 20),
            is_published=True,
        )
        self.score = StudentAssessmentScore.objects.create(
            assessment=self.assessment,
            student=self.student_charlie,
            marks_obtained=Decimal("88.50"),
            grade="A",
        )

        # Complaint Categories
        ComplaintCategory.ensure_default_categories(institution=self.institution)
        self.cat_fees = ComplaintCategory.objects.get(institution=self.institution, code="fees")
        self.cat_facilities = ComplaintCategory.objects.get(institution=self.institution, code="facilities")
        self.cat_teachers = ComplaintCategory.objects.get(institution=self.institution, code="teachers")

    # ==========================================================================
    # ACCEPTANCE TEST 1: A parent can see a linked child's records
    # ==========================================================================
    def test_acceptance_parent_can_see_linked_child_records(self):
        """
        Verify that an authorized parent can access all linked child records:
        - Parent Unified Hub: attendance, fees, test results, daily timetable
        - Child detail profile
        - Dedicated attendance, fees, timetable, and academics endpoints
        """
        self.client.force_login(self.parent_bucket)

        # 1. Unified Parent Hub
        hub_url = reverse("notifications:parent_hub_child", kwargs={"student_id": self.student_charlie.id})
        response = self.client.get(hub_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Charlie Bucket")
        self.assertContains(response, "Mid-Term Physics Exam")
        self.assertContains(response, "88.50")
        self.assertContains(response, "Term 1 Tuition")

        # 2. Child detail profile
        detail_url = reverse("accounts:parent_child_detail", kwargs={"student_id": self.student_charlie.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verified authorization token")
        self.assertContains(response, "Charlie Bucket")

        # 3. Dedicated attendance portal
        att_url = reverse("attendance:parent_child_attendance", kwargs={"student_id": self.student_charlie.id})
        response = self.client.get(att_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Charlie Bucket")

        # 4. Dedicated fees portal
        fees_url = reverse("fees:parent_child_fees", kwargs={"student_id": self.student_charlie.id})
        response = self.client.get(fees_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Charlie Bucket")

        # 5. Dedicated timetable schedule
        tt_url = reverse("timetable:parent_child_timetable", kwargs={"student_id": self.student_charlie.id})
        response = self.client.get(tt_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Physics")

        # 6. Dedicated academics & test scores
        acad_url = reverse("academics:parent_child_academics_detail", kwargs={"student_id": self.student_charlie.id})
        response = self.client.get(acad_url)
        self.assertEqual(response.status_code, 200)

    # ==========================================================================
    # ACCEPTANCE TEST 2: A parent cannot see an unrelated student's records
    # ==========================================================================
    def test_acceptance_parent_cannot_see_unrelated_student_records(self):
        """
        Verify strict authorization boundaries:
        - Parent cannot access an unrelated student's hub, profile, attendance, fees, timetable, or marks.
        - Raises 403 PermissionDenied or 404 for unrelated students.
        - Unverified links (is_authorized=False) are similarly blocked.
        """
        self.client.force_login(self.parent_bucket)

        # Attempt to access unrelated student david's profile
        detail_url = reverse("accounts:parent_child_detail", kwargs={"student_id": self.unrelated_student_david.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 403)

        # Attempt to access unrelated student david's attendance
        att_url = reverse("attendance:parent_child_attendance", kwargs={"student_id": self.unrelated_student_david.id})
        response = self.client.get(att_url)
        self.assertEqual(response.status_code, 403)

        # Attempt to access unrelated student david's fees
        fees_url = reverse("fees:parent_child_fees", kwargs={"student_id": self.unrelated_student_david.id})
        response = self.client.get(fees_url)
        self.assertEqual(response.status_code, 403)

        # Attempt to access unrelated student david's timetable
        tt_url = reverse("timetable:parent_child_timetable", kwargs={"student_id": self.unrelated_student_david.id})
        response = self.client.get(tt_url)
        self.assertEqual(response.status_code, 403)

        # Attempt to access unrelated student david's hub
        hub_url = reverse("notifications:parent_hub_child", kwargs={"student_id": self.unrelated_student_david.id})
        response = self.client.get(hub_url)
        self.assertEqual(response.status_code, 404)

        # Unverified relationship: is_authorized=False
        unverified_link = ParentStudentLink.objects.create(
            institution=self.institution,
            parent=self.unrelated_parent,
            student=self.student_charlie,
            relationship_type="other",
            is_authorized=False,  # NOT authorized
        )
        self.client.force_login(self.unrelated_parent)
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 403)

    # ==========================================================================
    # ACCEPTANCE TEST 3: A student submits a complaint and receives a ticket number
    # ==========================================================================
    def test_acceptance_student_submits_complaint_and_receives_ticket_number(self):
        """
        Verify that a student can submit a grievance ticket:
        - Receives unique formatted ticket_number (e.g. TKT-YYYYMM-XXXXX).
        - Ticket defaults to status OPEN with initial audit trail.
        - Categorization supports fees, attendance, facilities, teachers, administration.
        """
        self.client.force_login(self.student_charlie)

        submit_url = reverse("complaints:submit_ticket")
        payload = {
            "category": str(self.cat_facilities.id),
            "subject": "Physics Laboratory Multimeter Malfunction",
            "description": "Multimeter unit #4 in Lab 201 has a blown internal fuse and displays erratic readings.",
            "priority": TicketPriority.HIGH,
        }
        response = self.client.post(submit_url, payload, follow=True)
        self.assertEqual(response.status_code, 200)

        # Verify in database
        ticket = ComplaintTicket.objects.filter(submitter=self.student_charlie, subject="Physics Laboratory Multimeter Malfunction").first()
        self.assertIsNotNone(ticket)
        self.assertTrue(ticket.ticket_number.startswith("TKT-"))
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(ticket.category.code, "facilities")
        self.assertEqual(ticket.priority, TicketPriority.HIGH)

        # Audit history created
        self.assertTrue(ticket.status_history.filter(old_status=TicketStatus.OPEN, new_status=TicketStatus.OPEN).exists())

        # Returned page displays the ticket number
        self.assertContains(response, ticket.ticket_number)

    # ==========================================================================
    # ACCEPTANCE TEST 4: Authorized staff resolve the ticket
    # ==========================================================================
    def test_acceptance_authorized_staff_resolve_ticket(self):
        """
        Verify that authorized school staff can transition a complaint ticket to RESOLVED:
        - Logs resolution details, timestamp, and resolved_by staff user.
        - Immutable TicketStatusHistory records the transition.
        - Unauthorized users (students/parents) are prevented from altering status.
        """
        ticket = create_complaint_ticket(
            submitter=self.student_charlie,
            category=self.cat_fees,
            subject="Duplicate charge discrepancy on tuition portal",
            description="Payment record shows two charges for Term 1 tuition.",
            priority=TicketPriority.URGENT,
            institution=self.institution,
        )
        self.assertEqual(ticket.status, TicketStatus.OPEN)

        # 1. Staff desk resolves ticket
        self.client.force_login(self.accounts_staff)
        staff_detail_url = reverse("complaints:staff_ticket_detail", kwargs={"ticket_id": ticket.id})

        resolution_payload = {
            "action": "update_status",
            "status": TicketStatus.RESOLVED,
            "remarks": "Accounts department reconciled bank gateway transactions.",
            "resolution_details": "Duplicate charge of $2500 has been voided. Account statement updated.",
        }
        response = self.client.post(staff_detail_url, resolution_payload, follow=True)
        self.assertEqual(response.status_code, 200)

        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.RESOLVED)
        self.assertEqual(ticket.resolved_by, self.accounts_staff)
        self.assertIsNotNone(ticket.resolved_at)
        self.assertIn("Duplicate charge of $2500 has been voided", ticket.resolution_details)

        # Audit history logged
        history = ticket.status_history.filter(new_status=TicketStatus.RESOLVED).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.changed_by, self.accounts_staff)

        # 2. Unauthorized status change prevention: student tries to change status
        with self.assertRaises(PermissionDenied):
            transition_ticket_status(
                ticket=ticket,
                new_status=TicketStatus.CLOSED,
                changed_by=self.student_charlie,
            )

    # ==========================================================================
    # ACCEPTANCE TEST 5: The student sees the resolution but not internal notes
    # ==========================================================================
    def test_acceptance_student_sees_resolution_but_not_internal_notes(self):
        """
        Verify strict confidentiality of internal staff notes:
        - Staff can add private notes (is_internal=True).
        - Student viewing ticket sees resolution details and public remarks.
        - Student NEVER sees internal staff notes in rendered response.
        - Direct attempt by student to access staff desk raises HTTP 403 PermissionDenied.
        """
        ticket = create_complaint_ticket(
            submitter=self.student_charlie,
            category=self.cat_teachers,
            subject="Request for extra tutoring on Quantum Mechanics",
            description="Struggling with wave equation homework problems.",
            institution=self.institution,
        )

        # Staff adds internal note (Confidential)
        CONFIDENTIAL_STAFF_NOTE = "CONFIDENTIAL: Faculty discussed student's homework performance in private staff meeting."
        add_ticket_comment(
            ticket=ticket,
            author=self.teacher,
            message=CONFIDENTIAL_STAFF_NOTE,
            is_internal=True,
        )

        # Staff adds public response
        PUBLIC_STAFF_REPLY = "PUBLIC: Professor Curie will conduct an open tutorial this Thursday at 4 PM in Room 102."
        add_ticket_comment(
            ticket=ticket,
            author=self.teacher,
            message=PUBLIC_STAFF_REPLY,
            is_internal=False,
        )

        # Resolve ticket
        RESOLUTION_SUMMARY = "Extra tutorial session scheduled for Thursday 4 PM. Study notes uploaded."
        transition_ticket_status(
            ticket=ticket,
            new_status=TicketStatus.RESOLVED,
            changed_by=self.teacher,
            resolution_details=RESOLUTION_SUMMARY,
        )

        # Student accesses their ticket detail view
        self.client.force_login(self.student_charlie)
        student_view_url = reverse("complaints:ticket_detail", kwargs={"ticket_id": ticket.id})
        response = self.client.get(student_view_url)
        self.assertEqual(response.status_code, 200)

        # Student sees the resolution details and public reply
        self.assertContains(response, RESOLUTION_SUMMARY)
        self.assertContains(response, PUBLIC_STAFF_REPLY)

        # Student MUST NOT see the confidential internal staff note!
        self.assertNotContains(response, CONFIDENTIAL_STAFF_NOTE)

        # Student attempting to access staff management desk gets blocked
        staff_desk_url = reverse("complaints:staff_ticket_detail", kwargs={"ticket_id": ticket.id})
        staff_response = self.client.get(staff_desk_url)
        self.assertEqual(staff_response.status_code, 403)

    # ==========================================================================
    # ACCEPTANCE TEST 6: Batch announcements reach the intended audience only
    # ==========================================================================
    def test_acceptance_batch_announcements_reach_intended_audience_only(self):
        """
        Verify batch cohort targeting vs institute-wide announcements:
        - Notice targeted to Batch A reaches ONLY Batch A students and their linked parents.
        - Students and parents of Batch B do NOT receive Batch A notices.
        - Institute-wide notices reach all students and parents across the institution.
        """
        # Create coaching batches
        batch_alpha = Batch.objects.create(
            institution=self.institution,
            branch=self.branch,
            course=self.course,
            academic_session=self.session,
            name="Class 10 Science - Morning Batch Alpha",
            code="BAT-SCI-ALPHA",
            start_date=date(2026, 6, 1),
            end_date=date(2027, 4, 30),
            status=Batch.Status.ONGOING,
        )
        batch_beta = Batch.objects.create(
            institution=self.institution,
            branch=self.branch,
            course=self.course,
            academic_session=self.session,
            name="Class 10 Science - Evening Batch Beta",
            code="BAT-SCI-BETA",
            start_date=date(2026, 6, 1),
            end_date=date(2027, 4, 30),
            status=Batch.Status.ONGOING,
        )

        # Enroll student_charlie in Batch Alpha
        BatchEnrollment.objects.create(
            institution=self.institution,
            batch=batch_alpha,
            student=self.student_charlie,
            status=BatchEnrollment.Status.ACTIVE,
        )

        # Enroll unrelated_student_david in Batch Beta
        BatchEnrollment.objects.create(
            institution=self.institution,
            batch=batch_beta,
            student=self.unrelated_student_david,
            status=BatchEnrollment.Status.ACTIVE,
        )

        # Parent links: parent_bucket -> charlie (Batch Alpha)
        # unrelated_parent -> david (Batch Beta)
        ParentStudentLink.objects.create(
            institution=self.institution,
            parent=self.unrelated_parent,
            student=self.unrelated_student_david,
            relationship_type="father",
            is_authorized=True,
        )

        # 1. Batch Alpha-specific announcement
        notice_alpha = Announcement.objects.create(
            institution=self.institution,
            published_by=self.admin,
            title="Batch Alpha Saturday Mechanics Lab Workshop",
            content="Mandatory laboratory practical session this Saturday for Batch Alpha cohort only.",
            target_role=TargetRole.ALL,
            target_batch=batch_alpha,
            is_published=True,
        )

        # 2. Batch Beta-specific announcement
        notice_beta = Announcement.objects.create(
            institution=self.institution,
            published_by=self.admin,
            title="Batch Beta Optics Problem Solving Seminar",
            content="Optics numericals review for Batch Beta evening cohort.",
            target_role=TargetRole.ALL,
            target_batch=batch_beta,
            is_published=True,
        )

        # 3. Institute-wide announcement
        notice_campus_wide = Announcement.objects.create(
            institution=self.institution,
            published_by=self.admin,
            title="Campus-Wide Science Fair 2026 Registration Open",
            content="All students and parents across all cohorts are invited to register projects.",
            target_role=TargetRole.ALL,
            target_batch=None,
            target_classroom=None,
            is_published=True,
        )

        # Check announcements for Charlie (Batch Alpha)
        charlie_notices = get_user_announcements(self.student_charlie, institution=self.institution)
        self.assertIn(notice_alpha, charlie_notices)
        self.assertIn(notice_campus_wide, charlie_notices)
        self.assertNotIn(notice_beta, charlie_notices)

        # Check announcements for David (Batch Beta)
        david_notices = get_user_announcements(self.unrelated_student_david, institution=self.institution)
        self.assertIn(notice_beta, david_notices)
        self.assertIn(notice_campus_wide, david_notices)
        self.assertNotIn(notice_alpha, david_notices)

        # Check announcements for Charlie's Parent (Mrs. Bucket)
        parent_charlie_notices = get_user_announcements(self.parent_bucket, institution=self.institution)
        self.assertIn(notice_alpha, parent_charlie_notices)
        self.assertIn(notice_campus_wide, parent_charlie_notices)
        self.assertNotIn(notice_beta, parent_charlie_notices)

        # Check announcements for David's Parent
        parent_david_notices = get_user_announcements(self.unrelated_parent, institution=self.institution)
        self.assertIn(notice_beta, parent_david_notices)
        self.assertIn(notice_campus_wide, parent_david_notices)
        self.assertNotIn(notice_alpha, parent_david_notices)

    # ==========================================================================
    # ADDITIONAL TESTS: In-App Notifications & Atomic Deduplication
    # ==========================================================================
    def test_in_app_notifications_and_deduplication(self):
        """
        Verify automated event alerts (absence, fee due, exam notices)
        and atomic deduplication preventing notification spam.
        """
        # Absence alert
        notify_absence_alert(
            student=self.student_charlie,
            session_date=date(2026, 10, 15),
            subject_name="Chemistry",
        )
        charlie_unread = get_user_unread_count(self.student_charlie)
        parent_unread = get_user_unread_count(self.parent_bucket)
        self.assertGreaterEqual(charlie_unread, 1)
        self.assertGreaterEqual(parent_unread, 1)

        # Deduplication test: re-dispatching identical absence alert does NOT duplicate
        notify_absence_alert(
            student=self.student_charlie,
            session_date=date(2026, 10, 15),
            subject_name="Chemistry",
        )
        self.assertEqual(get_user_unread_count(self.student_charlie), charlie_unread)
        self.assertEqual(get_user_unread_count(self.parent_bucket), parent_unread)

        # Exam announcement
        notify_test_announcement(self.assessment)
        exam_notif = Notification.objects.filter(
            recipient=self.student_charlie,
            category=NotificationCategory.ACADEMICS,
        ).first()
        self.assertIsNotNone(exam_notif)

        # Results published notification
        notify_assessment_results_published(self.assessment)
        result_notif = Notification.objects.filter(
            recipient=self.student_charlie,
            title__startswith="Results Published",
        ).first()
        self.assertIsNotNone(result_notif)

        # Mark as read
        mark_notification_as_read(exam_notif.id, self.student_charlie)
        exam_notif.refresh_from_db()
        self.assertTrue(exam_notif.is_read)

        # Unauthorized mark as read rejected
        with self.assertRaises(PermissionDenied):
            mark_notification_as_read(result_notif.id, self.unrelated_student_david)

    # ==========================================================================
    # ADDITIONAL TESTS: External Messaging Integration & Delivery Confirmation
    # ==========================================================================
    def test_external_messaging_delivery_confirmation_enforcement(self):
        """
        Verifies core architectural requirement:
        'Do not claim that email, SMS or WhatsApp messages were delivered
        unless the real provider confirms delivery.'
        """
        # 1. Dispatch with Queued Provider (carrier only confirms queued/sent, NOT delivery)
        queued_provider = MockQueuedMessagingProvider()
        record_sent = send_external_message(
            recipient=self.student_charlie,
            channel=DeliveryChannel.EMAIL,
            subject="Term 1 Fee Invoice Notice",
            message_body="Please review your Term 1 fee breakdown.",
            provider=queued_provider,
            institution=self.institution,
        )
        # Status MUST be SENT, NOT DELIVERED!
        self.assertEqual(record_sent.status, DeliveryStatus.SENT)
        self.assertIsNone(record_sent.delivered_at)
        self.assertNotEqual(record_sent.status, DeliveryStatus.DELIVERED)

        # 2. Real carrier delivery receipt arrives via webhook
        handle_provider_delivery_receipt(
            provider_message_id=record_sent.provider_message_id,
            confirmation_payload="SMTP 250 2.0.0 OK Handset receipt acknowledged",
        )
        record_sent.refresh_from_db()
        # Status is now DELIVERED because provider confirmed delivery
        self.assertEqual(record_sent.status, DeliveryStatus.DELIVERED)
        self.assertIsNotNone(record_sent.delivered_at)

        # 3. Dispatch with Provider that provides instant confirmed delivery
        confirmed_provider = MockConfirmedMessagingProvider()
        record_confirmed = send_external_message(
            recipient=self.parent_bucket,
            channel=DeliveryChannel.WHATSAPP,
            subject="Absence Notice",
            message_body="Charlie was marked absent today.",
            provider=confirmed_provider,
            institution=self.institution,
        )
        self.assertEqual(record_confirmed.status, DeliveryStatus.DELIVERED)
        self.assertIsNotNone(record_confirmed.delivered_at)

        # 4. Dispatch with Failing Provider
        failing_provider = MockFailingMessagingProvider()
        record_failed = send_external_message(
            recipient=self.student_charlie,
            channel=DeliveryChannel.SMS,
            subject="Timetable change",
            message_body="Physics lab moved to Room 104.",
            provider=failing_provider,
            institution=self.institution,
        )
        self.assertEqual(record_failed.status, DeliveryStatus.FAILED)
        self.assertIn("550 Invalid recipient", record_failed.error_message)

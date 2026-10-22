"""
EduConnect Complaints & Grievance Request Automated Test Suite.
Tests:
- Ticket creation and unique ticket_number generation
- Strict role and ownership access control
- Internal staff notes confidentiality (never exposed to students/parents)
- Valid and invalid status lifecycle transitions
- Reopening of resolved tickets
- Post-resolution satisfaction ratings and feedback
- SLA overdue tracking calculation
"""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.complaints.models import (
    ComplaintCategory,
    ComplaintTicket,
    TicketComment,
    TicketPriority,
    TicketStatus,
)
from apps.complaints.services import (
    add_ticket_comment,
    create_complaint_ticket,
    reopen_complaint_ticket,
    submit_ticket_feedback,
    transition_ticket_status,
)

User = get_user_model()


class ComplaintsManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Admin & Staff
        self.admin_user = User.objects.create_superuser(
            username="admin_comp",
            email="admin_comp@educonnect.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
        )
        self.staff_user = User.objects.create_user(
            username="staff_officer",
            email="staff@educonnect.edu",
            password="TestPassword123!",
            role=Role.ACCOUNTS,
        )

        # Student & Parent
        self.student = User.objects.create_user(
            username="stud_charlie",
            email="charlie@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
        )
        self.parent = User.objects.create_user(
            username="parent_charlie",
            email="parent_charlie@gmail.com",
            password="TestPassword123!",
            role=Role.PARENT,
        )
        self.unrelated_student = User.objects.create_user(
            username="stud_david",
            email="david@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
        )

        # Categories
        self.cat_fees = ComplaintCategory.objects.create(
            name="Fee Billing & Payments",
            code="fees",
            sla_days=2,
        )
        self.cat_facilities = ComplaintCategory.objects.create(
            name="Campus Facilities & Maintenance",
            code="facilities",
            sla_days=4,
        )

    def test_ticket_creation_and_unique_number(self):
        """Ticket creation generates unique ticket_number with valid defaults."""
        ticket = create_complaint_ticket(
            submitter=self.student,
            category=self.cat_fees,
            subject="Fee receipt not received for online payment",
            description="Paid tuition yesterday but receipt link is missing.",
            priority=TicketPriority.HIGH,
        )
        self.assertTrue(ticket.ticket_number.startswith("TKT-"))
        self.assertEqual(ticket.status, TicketStatus.OPEN)
        self.assertEqual(ticket.submitter, self.student)
        self.assertEqual(ticket.reopen_count, 0)
        # Verify initial history log
        self.assertEqual(ticket.status_history.count(), 1)

    def test_ownership_and_access_control(self):
        """Students can only view their own tickets; unrelated users are rejected."""
        ticket = create_complaint_ticket(
            submitter=self.student,
            category=self.cat_fees,
            subject="Discrepancy in installment 2",
            description="Installment amount listed differs from schedule.",
        )

        # Owner can view
        self.client.force_login(self.student)
        res_owner = self.client.get(reverse("complaints:ticket_detail", args=[str(ticket.id)]))
        self.assertEqual(res_owner.status_code, 200)

        # Unrelated student is denied
        self.client.force_login(self.unrelated_student)
        res_unrelated = self.client.get(reverse("complaints:ticket_detail", args=[str(ticket.id)]))
        self.assertEqual(res_unrelated.status_code, 403)

        # Staff can view
        self.client.force_login(self.staff_user)
        res_staff = self.client.get(reverse("complaints:staff_ticket_detail", args=[str(ticket.id)]))
        self.assertEqual(res_staff.status_code, 200)

    def test_internal_staff_notes_confidentiality(self):
        """Internal notes are strictly isolated and never visible to student/parent views."""
        ticket = create_complaint_ticket(
            submitter=self.student,
            category=self.cat_facilities,
            subject="Air conditioner malfunctioning in Room 101",
            description="AC unit leaking water during class.",
        )

        # Staff adds a public reply
        add_ticket_comment(
            ticket=ticket,
            author=self.staff_user,
            message="We have contacted the technician.",
            is_internal=False,
        )

        # Staff adds an internal confidential note
        add_ticket_comment(
            ticket=ticket,
            author=self.staff_user,
            message="CONFIDENTIAL_INVESTIGATION: Replacement compressor requested under warranty PO-9912.",
            is_internal=True,
        )

        # Student views ticket detail: must see public reply, MUST NOT see internal note
        self.client.force_login(self.student)
        res_stud = self.client.get(reverse("complaints:ticket_detail", args=[str(ticket.id)]))
        self.assertContains(res_stud, "We have contacted the technician.")
        self.assertNotContains(res_stud, "CONFIDENTIAL_INVESTIGATION")
        self.assertNotContains(res_stud, "PO-9912")

        # Staff views ticket detail: sees both public and internal notes
        self.client.force_login(self.staff_user)
        res_staff = self.client.get(reverse("complaints:staff_ticket_detail", args=[str(ticket.id)]))
        self.assertContains(res_staff, "We have contacted the technician.")
        self.assertContains(res_staff, "CONFIDENTIAL_INVESTIGATION")

    def test_status_lifecycle_and_invalid_transitions(self):
        """Test authorized status transitions and prevention of illegal status jumps."""
        ticket = create_complaint_ticket(
            submitter=self.parent,
            category=self.cat_fees,
            subject="Transportation fee query",
            description="Bus route change inquiry.",
        )
        self.assertEqual(ticket.status, TicketStatus.OPEN)

        # Valid: OPEN -> UNDER_REVIEW
        transition_ticket_status(ticket, TicketStatus.UNDER_REVIEW, self.staff_user, "Reviewing bus records")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.UNDER_REVIEW)

        # Valid: UNDER_REVIEW -> IN_PROGRESS
        transition_ticket_status(ticket, TicketStatus.IN_PROGRESS, self.staff_user, "Assigned to transport coordinator")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.IN_PROGRESS)

        # Valid: IN_PROGRESS -> RESOLVED
        transition_ticket_status(
            ticket,
            TicketStatus.RESOLVED,
            self.staff_user,
            "Resolved route",
            resolution_details="Bus stop assigned to Stop #4 at 7:45 AM.",
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.RESOLVED)
        self.assertIsNotNone(ticket.resolved_at)
        self.assertEqual(ticket.resolved_by, self.staff_user)

        # Invalid transition: Non-admin cannot transition RESOLVED directly back to UNDER_REVIEW
        with self.assertRaises(ValidationError):
            transition_ticket_status(ticket, TicketStatus.UNDER_REVIEW, self.staff_user)

    def test_reopen_ticket_workflow(self):
        """Owner can reopen resolved ticket; unauthorized users or un-resolved tickets cannot be reopened."""
        ticket = create_complaint_ticket(
            submitter=self.student,
            category=self.cat_facilities,
            subject="Library light flickering",
            description="Row 4 desk light flickers.",
        )
        # Cannot reopen an OPEN ticket
        with self.assertRaises(ValidationError):
            reopen_complaint_ticket(ticket, self.student, "Not resolved yet")

        # Resolve ticket
        transition_ticket_status(ticket, TicketStatus.RESOLVED, self.staff_user, "Bulb replaced")

        # Unrelated user cannot reopen
        with self.assertRaises(PermissionDenied):
            reopen_complaint_ticket(ticket, self.unrelated_student, "I want to reopen")

        # Owner reopens ticket
        reopen_complaint_ticket(ticket, self.student, "Light is still flickering after replacement.")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.REOPENED)
        self.assertEqual(ticket.reopen_count, 1)

    def test_satisfaction_feedback_and_rating(self):
        """Owner can submit 1-5 star satisfaction feedback only when resolved or closed."""
        ticket = create_complaint_ticket(
            submitter=self.student,
            category=self.cat_fees,
            subject="Online fee discount",
            description="Sibling discount application.",
        )

        # Cannot submit feedback on open ticket
        with self.assertRaises(ValidationError):
            submit_ticket_feedback(ticket, self.student, 5, "Great")

        # Resolve ticket
        transition_ticket_status(
            ticket, TicketStatus.RESOLVED, self.staff_user, resolution_details="Discount applied to installment 2."
        )

        # Submit feedback
        submit_ticket_feedback(ticket, self.student, 5, "Extremely prompt and helpful response. Thank you!")
        ticket.refresh_from_db()
        self.assertEqual(ticket.satisfaction_rating, 5)
        self.assertEqual(ticket.feedback_comment, "Extremely prompt and helpful response. Thank you!")

    def test_sla_overdue_flag(self):
        """Ticket is flagged as overdue when unresolved after SLA days."""
        ticket = create_complaint_ticket(
            submitter=self.student,
            category=self.cat_fees,  # SLA = 2 days
            subject="Urgent fee clarification",
            description="Due date tomorrow.",
        )
        # Newly created ticket is not overdue
        self.assertFalse(ticket.is_overdue)

        # Simulate ticket created 3 days ago (exceeding 2 days SLA)
        past_time = timezone.now() - timedelta(days=3)
        ComplaintTicket.objects.filter(id=ticket.id).update(created_at=past_time)
        ticket.refresh_from_db()
        self.assertTrue(ticket.is_overdue)

        # Once resolved, it is no longer flagged as overdue
        transition_ticket_status(ticket, TicketStatus.RESOLVED, self.staff_user)
        ticket.refresh_from_db()
        self.assertFalse(ticket.is_overdue)

"""
Complaint & Issue Tracking Services for EduConnect.
Handles status transitions, SLA checks, reopening workflows,
internal notes protection, and satisfaction ratings.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from apps.accounts.models import Role
from apps.complaints.models import (
    ComplaintCategory,
    ComplaintTicket,
    TicketComment,
    TicketPriority,
    TicketStatus,
    TicketStatusHistory,
)

# Permitted status state transitions
VALID_TRANSITIONS = {
    TicketStatus.OPEN: [TicketStatus.UNDER_REVIEW, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.UNDER_REVIEW: [TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.IN_PROGRESS: [TicketStatus.UNDER_REVIEW, TicketStatus.RESOLVED, TicketStatus.CLOSED],
    TicketStatus.RESOLVED: [TicketStatus.CLOSED, TicketStatus.REOPENED],
    TicketStatus.CLOSED: [TicketStatus.REOPENED],
    TicketStatus.REOPENED: [TicketStatus.UNDER_REVIEW, TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.CLOSED],
}


def create_complaint_ticket(
    submitter,
    category: ComplaintCategory,
    subject: str,
    description: str,
    priority: str = TicketPriority.MEDIUM,
    attachment=None,
    institution=None,
) -> ComplaintTicket:
    """
    Submits a new complaint or issue ticket:
    - Enforces student or parent submitter
    - Creates ticket and initial status history log
    """
    if submitter.role not in [Role.STUDENT, Role.PARENT, Role.ADMIN]:
        raise PermissionDenied("Only students, parents, or administrators can submit grievances.")

    if not subject.strip():
        raise ValidationError("Subject cannot be blank.")
    if not description.strip():
        raise ValidationError("Description cannot be blank.")

    ticket = ComplaintTicket.objects.create(
        institution=institution or getattr(category, "institution", None),
        submitter=submitter,
        category=category,
        subject=subject.strip(),
        description=description.strip(),
        priority=priority,
        status=TicketStatus.OPEN,
        attachment=attachment,
    )

    TicketStatusHistory.objects.create(
        ticket=ticket,
        old_status=TicketStatus.OPEN,
        new_status=TicketStatus.OPEN,
        changed_by=submitter,
        remarks="Ticket created.",
    )
    return ticket


def transition_ticket_status(
    ticket: ComplaintTicket,
    new_status: str,
    changed_by,
    remarks: str = "",
    resolution_details: str = "",
) -> ComplaintTicket:
    """
    Updates the status of a complaint ticket through authorized state transitions:
    - Validates transition path
    - Records resolution timestamp and agent when resolved
    - Creates an immutable TicketStatusHistory audit entry
    """
    old_status = ticket.status

    if new_status == old_status:
        return ticket

    # Permission check: Only authorized staff/admin can change ticket status,
    # except for the ticket submitter reopening a resolved ticket.
    is_staff = getattr(changed_by, "role", None) in [Role.ADMIN, Role.ACCOUNTS, Role.TEACHER] or getattr(changed_by, "is_superuser", False)
    is_submitter_reopen = (changed_by == ticket.submitter and new_status == TicketStatus.REOPENED and old_status in [TicketStatus.RESOLVED, TicketStatus.CLOSED])

    if not is_staff and not is_submitter_reopen:
        raise PermissionDenied("Only authorized school staff or administrators can update complaint ticket status.")

    allowed = VALID_TRANSITIONS.get(old_status, [])
    # Admin can force transitions
    if new_status not in allowed and not (getattr(changed_by, "role", None) == Role.ADMIN or getattr(changed_by, "is_superuser", False)):
        raise ValidationError(
            f"Invalid status transition from '{ticket.get_status_display()}' to '{new_status}'."
        )

    now = timezone.now()
    ticket.status = new_status

    if new_status == TicketStatus.RESOLVED:
        ticket.resolved_at = now
        ticket.resolved_by = changed_by
        if resolution_details.strip():
            ticket.resolution_details = resolution_details.strip()

    elif new_status == TicketStatus.CLOSED:
        ticket.closed_at = now

    ticket.save()

    TicketStatusHistory.objects.create(
        ticket=ticket,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        remarks=remarks.strip(),
    )
    return ticket


def reopen_complaint_ticket(ticket: ComplaintTicket, requester, reason: str) -> ComplaintTicket:
    """
    Reopens a resolved complaint ticket:
    - Only the original submitter or admin can reopen
    - Ticket must currently be in RESOLVED state
    - Increments reopen_count and transitions to REOPENED
    """
    if requester != ticket.submitter and requester.role != Role.ADMIN:
        raise PermissionDenied("You can only reopen your own complaint tickets.")

    if ticket.status != TicketStatus.RESOLVED:
        raise ValidationError("Only resolved tickets can be reopened.")

    if not reason.strip():
        raise ValidationError("Please provide a reason for reopening this ticket.")

    ticket.reopen_count += 1
    ticket = transition_ticket_status(
        ticket=ticket,
        new_status=TicketStatus.REOPENED,
        changed_by=requester,
        remarks=f"Reopened by user: {reason.strip()}",
    )

    # Also log a public comment with the reason
    TicketComment.objects.create(
        ticket=ticket,
        author=requester,
        message=f"Ticket Reopened. Reason: {reason.strip()}",
        is_internal=False,
    )
    return ticket


def add_ticket_comment(
    ticket: ComplaintTicket,
    author,
    message: str,
    is_internal: bool = False,
    attachment=None,
) -> TicketComment:
    """
    Appends a communication message or internal staff note to a ticket:
    - Internal notes are strictly restricted to admin or staff roles
    """
    if not message.strip():
        raise ValidationError("Comment message cannot be blank.")

    if is_internal and author.role not in [Role.ADMIN, Role.ACCOUNTS, Role.TEACHER]:
        raise PermissionDenied("Only authorized school staff can add internal notes.")

    # Students and parents can only comment on their own tickets
    if author.role in [Role.STUDENT, Role.PARENT] and author != ticket.submitter:
        raise PermissionDenied("You can only comment on your own tickets.")

    comment = TicketComment.objects.create(
        ticket=ticket,
        author=author,
        message=message.strip(),
        is_internal=is_internal,
        attachment=attachment,
    )
    return comment


def submit_ticket_feedback(
    ticket: ComplaintTicket,
    submitter,
    rating: int,
    comment: str = "",
) -> ComplaintTicket:
    """
    Records post-resolution user satisfaction rating (1-5) and feedback:
    - Validates ownership
    - Ticket must be resolved or closed
    """
    if submitter != ticket.submitter:
        raise PermissionDenied("Only the original ticket submitter can submit satisfaction feedback.")

    if not ticket.is_resolved_or_closed:
        raise ValidationError("Satisfaction feedback can only be submitted after ticket resolution.")

    if rating not in [1, 2, 3, 4, 5]:
        raise ValidationError("Rating must be an integer between 1 and 5.")

    ticket.satisfaction_rating = rating
    ticket.feedback_comment = comment.strip()
    ticket.save()
    return ticket

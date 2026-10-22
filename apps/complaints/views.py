"""
Views for EduConnect Complaints & Grievance Request Management Module.
Implements student/parent ticketing, communication threads, reopening,
staff resolution workflows, internal notes isolation, and reports.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.models import Role
from apps.complaints.forms import (
    AssignTicketForm,
    ComplaintTicketForm,
    ReopenTicketForm,
    StaffInternalNoteForm,
    TicketCommentForm,
    TicketFeedbackForm,
    TicketStatusUpdateForm,
)
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


# ==============================================================================
# STUDENT & PARENT VIEWS
# ==============================================================================

@login_required
def my_tickets_list(request):
    """
    List tickets submitted by current user (student, parent, or applicant).
    """
    inst = getattr(request, "institution", None)
    tickets = ComplaintTicket.objects.filter(submitter=request.user).select_related("category")
    if inst:
        tickets = tickets.filter(institution=inst)
    status_filter = request.GET.get("status")
    if status_filter:
        tickets = tickets.filter(status=status_filter)

    categories = ComplaintCategory.objects.filter(is_active=True)
    if inst:
        categories = categories.filter(institution=inst)

    context = {
        "tickets": tickets,
        "selected_status": status_filter,
        "categories": categories,
    }
    return render(request, "complaints/student_parent/list.html", context)


@login_required
def submit_ticket_view(request):
    """
    Submit a new complaint or support ticket.
    """
    if request.user.role not in [Role.STUDENT, Role.PARENT, Role.APPLICANT, Role.ADMIN]:
        raise PermissionDenied("Only students and parents can submit grievance requests.")

    inst = getattr(request, "institution", None)
    if request.method == "POST":
        form = ComplaintTicketForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                ticket = create_complaint_ticket(
                    submitter=request.user,
                    category=form.cleaned_data["category"],
                    subject=form.cleaned_data["subject"],
                    description=form.cleaned_data["description"],
                    priority=form.cleaned_data["priority"],
                    attachment=request.FILES.get("attachment"),
                    institution=inst,
                )
                messages.success(
                    request,
                    f"Grievance ticket #{ticket.ticket_number} created successfully. Our team will review it shortly.",
                )
                return redirect("complaints:ticket_detail", ticket_id=str(ticket.id))
            except (ValidationError, PermissionDenied) as e:
                messages.error(request, str(e))
    else:
        form = ComplaintTicketForm()

    return render(request, "complaints/student_parent/submit.html", {"form": form})


@login_required
def ticket_detail_view(request, ticket_id):
    """
    View ticket details, chronological thread, and submit replies.
    Strictly enforces confidentiality: students/parents NEVER see internal staff notes!
    """
    ticket = get_object_or_404(ComplaintTicket.objects.select_related("category", "submitter", "assigned_to"), id=ticket_id)
    inst = getattr(request, "institution", None)
    if inst and ticket.institution and ticket.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to ticket outside your active institution.")

    # Permission check: submitter or staff/admin
    is_staff = request.user.role in [Role.ADMIN, Role.ACCOUNTS, Role.TEACHER]
    if request.user != ticket.submitter and not is_staff:
        raise PermissionDenied("You do not have permission to view this complaint ticket.")

    # If staff, redirect to staff desk detail for full tools
    if is_staff and request.user != ticket.submitter:
        return redirect("complaints:staff_ticket_detail", ticket_id=str(ticket.id))

    # Comments: strictly hide internal notes from student/parent!
    comments = ticket.comments.filter(is_internal=False).select_related("author").order_by("created_at")

    if request.method == "POST" and "post_comment" in request.POST:
        comment_form = TicketCommentForm(request.POST, request.FILES)
        if comment_form.is_valid():
            try:
                add_ticket_comment(
                    ticket=ticket,
                    author=request.user,
                    message=comment_form.cleaned_data["message"],
                    is_internal=False,
                    attachment=request.FILES.get("attachment"),
                )
                messages.success(request, "Your message has been posted.")
                return redirect("complaints:ticket_detail", ticket_id=str(ticket.id))
            except (ValidationError, PermissionDenied) as e:
                messages.error(request, str(e))
    else:
        comment_form = TicketCommentForm()

    reopen_form = ReopenTicketForm()
    feedback_form = TicketFeedbackForm(instance=ticket)

    context = {
        "ticket": ticket,
        "comments": comments,
        "comment_form": comment_form,
        "reopen_form": reopen_form,
        "feedback_form": feedback_form,
    }
    return render(request, "complaints/student_parent/detail.html", context)


@login_required
def reopen_ticket_view(request, ticket_id):
    """
    Reopen a resolved ticket by the owner.
    """
    ticket = get_object_or_404(ComplaintTicket, id=ticket_id)
    if request.method == "POST":
        form = ReopenTicketForm(request.POST)
        if form.is_valid():
            try:
                reopen_complaint_ticket(ticket, request.user, form.cleaned_data["reason"])
                messages.success(request, f"Ticket #{ticket.ticket_number} has been reopened for further investigation.")
            except (ValidationError, PermissionDenied) as e:
                messages.error(request, str(e))
    return redirect("complaints:ticket_detail", ticket_id=str(ticket.id))


@login_required
def submit_feedback_view(request, ticket_id):
    """
    Submit satisfaction rating and feedback after ticket resolution.
    """
    ticket = get_object_or_404(ComplaintTicket, id=ticket_id)
    if request.method == "POST":
        form = TicketFeedbackForm(request.POST, instance=ticket)
        if form.is_valid():
            try:
                rating = int(form.cleaned_data["satisfaction_rating"])
                comment = form.cleaned_data.get("feedback_comment", "")
                submit_ticket_feedback(ticket, request.user, rating, comment)
                messages.success(request, "Thank you for your feedback! It helps us improve institutional services.")
            except (ValidationError, PermissionDenied, ValueError) as e:
                messages.error(request, str(e))
    return redirect("complaints:ticket_detail", ticket_id=str(ticket.id))


# ==============================================================================
# STAFF & ADMIN COMPLAINTS DESK
# ==============================================================================

@login_required
@role_required(Role.ADMIN, Role.ACCOUNTS, Role.TEACHER)
def staff_tickets_desk(request):
    """
    Staff operational desk for managing and prioritizing grievance tickets.
    """
    inst = getattr(request, "institution", None)
    tickets = ComplaintTicket.objects.select_related("category", "submitter", "assigned_to").all()
    if inst:
        tickets = tickets.filter(institution=inst)

    # Filter by category
    category_code = request.GET.get("category")
    if category_code:
        tickets = tickets.filter(category__code=category_code)

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        tickets = tickets.filter(status=status_filter)

    # Filter by priority
    priority_filter = request.GET.get("priority")
    if priority_filter:
        tickets = tickets.filter(priority=priority_filter)

    # Filter assigned to me
    if request.GET.get("assigned_to_me") == "1":
        tickets = tickets.filter(assigned_to=request.user)

    # Metrics
    base_qs = ComplaintTicket.objects.filter(institution=inst) if inst else ComplaintTicket.objects.all()
    total_open = base_qs.filter(status__in=[TicketStatus.OPEN, TicketStatus.UNDER_REVIEW]).count()
    total_in_progress = base_qs.filter(status=TicketStatus.IN_PROGRESS).count()
    total_resolved = base_qs.filter(status__in=[TicketStatus.RESOLVED, TicketStatus.CLOSED]).count()

    categories = ComplaintCategory.objects.filter(is_active=True)
    if inst:
        categories = categories.filter(institution=inst)

    context = {
        "tickets": tickets,
        "total_open": total_open,
        "total_in_progress": total_in_progress,
        "total_resolved": total_resolved,
        "categories": categories,
        "selected_category": category_code,
        "selected_status": status_filter,
        "selected_priority": priority_filter,
    }
    return render(request, "complaints/staff/desk.html", context)


@login_required
@role_required(Role.ADMIN, Role.ACCOUNTS, Role.TEACHER)
def staff_ticket_detail(request, ticket_id):
    """
    Staff full ticket workspace:
    - View full conversation timeline
    - Post public response
    - Add private internal staff notes
    - Update ticket status & log resolution details
    - Assign ticket
    """
    ticket = get_object_or_404(
        ComplaintTicket.objects.select_related("category", "submitter", "assigned_to", "resolved_by"),
        id=ticket_id,
    )
    inst = getattr(request, "institution", None)
    if inst and ticket.institution and ticket.institution != inst and not request.user.is_superuser:
        raise PermissionDenied("Access denied to ticket outside your active institution.")

    # Fetch ALL comments including internal staff notes
    comments = ticket.comments.select_related("author").order_by("created_at")
    status_history = ticket.status_history.select_related("changed_by").order_by("-created_at")

    # Handle Forms
    if request.method == "POST":
        action = request.POST.get("action")

        # 1. Update Status
        if action == "update_status":
            status_form = TicketStatusUpdateForm(request.POST)
            if status_form.is_valid():
                new_status = status_form.cleaned_data["status"]
                remarks = status_form.cleaned_data.get("remarks", "")
                resolution_details = status_form.cleaned_data.get("resolution_details", "")
                try:
                    transition_ticket_status(ticket, new_status, request.user, remarks, resolution_details)
                    messages.success(request, f"Ticket status changed to {new_status}.")
                    return redirect("complaints:staff_ticket_detail", ticket_id=str(ticket.id))
                except (ValidationError, PermissionDenied) as e:
                    messages.error(request, str(e))

        # 2. Add Public Reply
        elif action == "public_reply":
            comment_form = TicketCommentForm(request.POST, request.FILES)
            if comment_form.is_valid():
                try:
                    add_ticket_comment(
                        ticket=ticket,
                        author=request.user,
                        message=comment_form.cleaned_data["message"],
                        is_internal=False,
                        attachment=request.FILES.get("attachment"),
                    )
                    messages.success(request, "Public response posted to student/parent.")
                    return redirect("complaints:staff_ticket_detail", ticket_id=str(ticket.id))
                except (ValidationError, PermissionDenied) as e:
                    messages.error(request, str(e))

        # 3. Add Internal Staff Note
        elif action == "internal_note":
            note_form = StaffInternalNoteForm(request.POST, request.FILES)
            if note_form.is_valid():
                try:
                    add_ticket_comment(
                        ticket=ticket,
                        author=request.user,
                        message=note_form.cleaned_data["message"],
                        is_internal=True,
                        attachment=request.FILES.get("attachment"),
                    )
                    messages.success(request, "Internal note saved (hidden from student/parent).")
                    return redirect("complaints:staff_ticket_detail", ticket_id=str(ticket.id))
                except (ValidationError, PermissionDenied) as e:
                    messages.error(request, str(e))

        # 4. Assign Ticket
        elif action == "assign_ticket":
            assign_form = AssignTicketForm(request.POST)
            if assign_form.is_valid():
                assignee = assign_form.cleaned_data["assigned_to"]
                ticket.assigned_to = assignee
                ticket.save()
                messages.success(
                    request,
                    f"Ticket assigned to {assignee.get_full_name() or assignee.username if assignee else 'Unassigned'}.",
                )
                return redirect("complaints:staff_ticket_detail", ticket_id=str(ticket.id))

    status_form = TicketStatusUpdateForm(
        initial={"status": ticket.status, "resolution_details": ticket.resolution_details}
    )
    comment_form = TicketCommentForm()
    note_form = StaffInternalNoteForm()
    assign_form = AssignTicketForm(initial={"assigned_to": ticket.assigned_to})

    context = {
        "ticket": ticket,
        "comments": comments,
        "status_history": status_history,
        "status_form": status_form,
        "comment_form": comment_form,
        "note_form": note_form,
        "assign_form": assign_form,
    }
    return render(request, "complaints/staff/detail.html", context)


@login_required
@role_required(Role.ADMIN)
def staff_tickets_report(request):
    """
    Analytical reports on grievance volumes, category distribution,
    resolution SLA compliance, and satisfaction ratings.
    """
    inst = getattr(request, "institution", None)
    tickets_qs = ComplaintTicket.objects.filter(institution=inst) if inst else ComplaintTicket.objects.all()

    total_tickets = tickets_qs.count()
    category_breakdown = (
        tickets_qs.values("category__name")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    status_breakdown = (
        tickets_qs.values("status")
        .annotate(total=Count("id"))
        .order_by("-total")
    )

    resolved_tickets = tickets_qs.filter(status__in=[TicketStatus.RESOLVED, TicketStatus.CLOSED])
    feedback_ratings = resolved_tickets.filter(satisfaction_rating__isnull=False)
    avg_rating = 0
    if feedback_ratings.exists():
        total_rating = sum(t.satisfaction_rating for t in feedback_ratings)
        avg_rating = round(total_rating / feedback_ratings.count(), 1)

    # Overdue calculation
    overdue_tickets = [t for t in tickets_qs if t.is_overdue]

    context = {
        "total_tickets": total_tickets,
        "category_breakdown": category_breakdown,
        "status_breakdown": status_breakdown,
        "avg_rating": avg_rating,
        "rated_count": feedback_ratings.count(),
        "overdue_tickets": overdue_tickets,
    }
    return render(request, "complaints/staff/reports.html", context)

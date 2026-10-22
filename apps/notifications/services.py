"""
Notification & Communication Services for EduConnect.
Provides atomic deduplication, automated event dispatchers (absence alerts,
fee dues, coursework notices), announcement targeting, and read status management.
"""

from typing import List, Optional
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import ParentStudentLink, Role
from apps.attendance.models import ClassEnrollment
from apps.notifications.models import (
    Announcement,
    Notification,
    NotificationCategory,
    TargetRole,
)


def send_notification(
    recipient,
    title: str,
    message: str,
    category: str = NotificationCategory.SYSTEM,
    action_url: str = "",
    deduplication_key: Optional[str] = None,
    institution=None,
) -> Optional[Notification]:
    """
    Dispatches a database-backed in-app notification:
    - Avoids duplicate alert spam if deduplication_key already exists for recipient
    """
    if deduplication_key:
        exists = Notification.objects.filter(
            recipient=recipient,
            deduplication_key=deduplication_key,
        ).exists()
        if exists:
            return None

    notification = Notification.objects.create(
        institution=institution,
        recipient=recipient,
        title=title.strip(),
        message=message.strip(),
        category=category,
        action_url=action_url.strip(),
        deduplication_key=deduplication_key,
    )
    return notification


def mark_notification_as_read(notification_id, user) -> Notification:
    """
    Marks a single notification as read, ensuring recipient ownership.
    """
    notification = Notification.objects.get(id=notification_id)
    if notification.recipient != user and user.role != Role.ADMIN:
        raise PermissionDenied("You can only mark your own notifications as read.")

    notification.mark_as_read()
    return notification


def mark_all_notifications_as_read(user) -> int:
    """
    Marks all unread notifications for a user as read.
    """
    now = timezone.now()
    unread_notifications = Notification.objects.filter(recipient=user, is_read=False)
    count = unread_notifications.count()
    for n in unread_notifications:
        n.is_read = True
        n.read_at = now
        n.save(update_fields=["is_read", "read_at"])
    return count


def get_user_unread_count(user) -> int:
    """
    Returns total unread notification count for badge rendering.
    """
    if not user.is_authenticated:
        return 0
    return Notification.objects.filter(recipient=user, is_read=False).count()


def get_user_announcements(user, institution=None) -> List[Announcement]:
    """
    Retrieves active announcements targeted to the specific user:
    - Checks validity window (published, not expired)
    - Matches role target ("all" or user.role)
    - If student/parent, matches target classroom if classroom-specific
    """
    now = timezone.now()
    qs = Announcement.objects.filter(
        is_published=True,
        publish_date__lte=now,
    ).filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=now)
    )

    if institution:
        qs = qs.filter(institution=institution)

    if getattr(user, "role", None) == Role.ADMIN:
        return qs.order_by("-publish_date")

    # Match role
    role_filter = Q(target_role=TargetRole.ALL)
    if getattr(user, "role", None) == Role.STUDENT:
        role_filter |= Q(target_role=TargetRole.STUDENT)
    elif getattr(user, "role", None) == Role.PARENT:
        role_filter |= Q(target_role=TargetRole.PARENT)
    elif getattr(user, "role", None) == Role.TEACHER:
        role_filter |= Q(target_role=TargetRole.TEACHER)

    qs = qs.filter(role_filter)

    # Classroom & Batch cohort targeting
    if getattr(user, "role", None) == Role.STUDENT:
        from apps.attendance.models import ClassEnrollment
        from apps.academics.models import BatchEnrollment

        enrolled_classrooms = ClassEnrollment.objects.filter(
            student=user, is_active=True
        ).values_list("classroom_id", flat=True)

        enrolled_batches = BatchEnrollment.objects.filter(
            student=user,
            status=BatchEnrollment.Status.ACTIVE,
        ).values_list("batch_id", flat=True)

        qs = qs.filter(
            (Q(target_classroom__isnull=True) | Q(target_classroom_id__in=enrolled_classrooms)) &
            (Q(target_batch__isnull=True) | Q(target_batch_id__in=enrolled_batches))
        )

    elif getattr(user, "role", None) == Role.PARENT:
        from apps.attendance.models import ClassEnrollment
        from apps.academics.models import BatchEnrollment

        link_q = {"parent": user, "is_authorized": True}
        if institution:
            link_q["institution"] = institution
        linked_student_ids = ParentStudentLink.objects.filter(**link_q).values_list("student_id", flat=True)

        children_classrooms = ClassEnrollment.objects.filter(
            student_id__in=linked_student_ids, is_active=True
        ).values_list("classroom_id", flat=True)

        children_batches = BatchEnrollment.objects.filter(
            student_id__in=linked_student_ids,
            status=BatchEnrollment.Status.ACTIVE,
        ).values_list("batch_id", flat=True)

        qs = qs.filter(
            (Q(target_classroom__isnull=True) | Q(target_classroom_id__in=children_classrooms)) &
            (Q(target_batch__isnull=True) | Q(target_batch_id__in=children_batches))
        )

    return qs.order_by("-publish_date")


def notify_absence_alert(student, session_date, subject_name: str, classroom_name: str = ""):
    """
    Dispatches automated absence notifications to the absent student
    and all authorized linked parents.
    """
    date_str = session_date.strftime("%b %d, %Y")
    title = f"Absence Notice: {subject_name} ({date_str})"
    student_name = student.get_full_name() or student.username

    # Student message
    student_msg = (
        f"You were marked absent for {subject_name} on {date_str}. "
        f"If this was in error, please submit an attendance correction request through your portal."
    )
    send_notification(
        recipient=student,
        title=title,
        message=student_msg,
        category=NotificationCategory.ATTENDANCE,
        action_url="/attendance/student/",
        deduplication_key=f"abs-{student.id}-{session_date}-{subject_name}",
    )

    # Parent message
    parent_links = ParentStudentLink.objects.filter(student=student, is_authorized=True).select_related("parent")
    for link in parent_links:
        parent_msg = (
            f"Attendance Alert: Your child {student_name} was marked absent for {subject_name} "
            f"on {date_str}. Please review their attendance profile on the Parent Portal."
        )
        send_notification(
            recipient=link.parent,
            title=f"Absence Alert: {student_name} - {subject_name}",
            message=parent_msg,
            category=NotificationCategory.ATTENDANCE,
            action_url=f"/attendance/parent/{student.id}/",
            deduplication_key=f"abs-par-{link.parent.id}-{student.id}-{session_date}-{subject_name}",
        )


def notify_fee_due_alert(student, installment_title: str, amount, due_date):
    """
    Dispatches fee payment due date notifications to student and linked parents.
    """
    due_str = due_date.strftime("%b %d, %Y")
    title = f"Fee Due Reminder: {installment_title} ({amount})"
    student_name = student.get_full_name() or student.username

    msg = f"Upcoming fee installment '{installment_title}' of {amount} is due on {due_str}."
    send_notification(
        recipient=student,
        title=title,
        message=msg,
        category=NotificationCategory.FEES,
        action_url="/fees/student/",
        deduplication_key=f"fee-due-{student.id}-{installment_title}-{due_date}",
    )

    parent_links = ParentStudentLink.objects.filter(student=student, is_authorized=True).select_related("parent")
    for link in parent_links:
        parent_msg = f"Tuition notice for {student_name}: Installment '{installment_title}' of {amount} is due on {due_str}."
        send_notification(
            recipient=link.parent,
            title=f"Fee Due Notice: {student_name} ({installment_title})",
            message=parent_msg,
            category=NotificationCategory.FEES,
            action_url=f"/fees/parent/{student.id}/",
            deduplication_key=f"fee-due-par-{link.parent.id}-{student.id}-{installment_title}-{due_date}",
        )


def notify_test_announcement(assessment, custom_message: str = ""):
    """
    Dispatches test/assessment scheduling announcements to students enrolled in the classroom/cohort
    and their authorized parents.
    """
    from apps.attendance.models import ClassEnrollment

    exam_date_str = assessment.date_conducted.strftime("%b %d, %Y")
    title = f"Exam Scheduled: {assessment.title} ({assessment.subject_name})"
    default_msg = (
        f"Upcoming {assessment.get_assessment_type_display()} for {assessment.subject_name} "
        f"is scheduled on {exam_date_str}. Total Marks: {assessment.max_marks}."
    )
    msg = custom_message.strip() if custom_message.strip() else default_msg

    enrollments = ClassEnrollment.objects.filter(
        classroom=assessment.classroom,
        is_active=True,
    ).select_related("student")

    for enr in enrollments:
        student = enr.student
        student_name = student.get_full_name() or student.username

        # Student notification
        send_notification(
            recipient=student,
            title=title,
            message=msg,
            category=NotificationCategory.ACADEMICS,
            action_url="/academics/student/results/",
            deduplication_key=f"test-sch-{assessment.id}-{student.id}",
            institution=assessment.institution,
        )

        # Parent notifications
        parent_links = ParentStudentLink.objects.filter(student=student, is_authorized=True).select_related("parent")
        for link in parent_links:
            parent_msg = f"Academic Notice for {student_name}: {msg}"
            send_notification(
                recipient=link.parent,
                title=f"Test Schedule: {student_name} ({assessment.subject_name})",
                message=parent_msg,
                category=NotificationCategory.ACADEMICS,
                action_url=f"/academics/parent/{student.id}/",
                deduplication_key=f"test-sch-par-{assessment.id}-{link.parent.id}-{student.id}",
                institution=assessment.institution,
            )


def notify_assessment_results_published(assessment):
    """
    Notifies students and parents when assessment results are formally published.
    """
    from apps.academics.models import StudentAssessmentScore

    title = f"Results Published: {assessment.title} ({assessment.subject_name})"
    scores = StudentAssessmentScore.objects.filter(assessment=assessment).select_related("student")

    for score in scores:
        student = score.student
        student_name = student.get_full_name() or student.username
        grade_display = f" (Grade: {score.grade})" if getattr(score, "grade", None) else ""
        grade_info = f"Score: {score.marks_obtained}/{assessment.max_marks}{grade_display}"

        # Student notification
        send_notification(
            recipient=student,
            title=title,
            message=f"Your grades for {assessment.title} have been published. {grade_info}.",
            category=NotificationCategory.ACADEMICS,
            action_url="/academics/student/results/",
            deduplication_key=f"test-res-{assessment.id}-{student.id}",
            institution=assessment.institution,
        )

        # Parent notification
        parent_links = ParentStudentLink.objects.filter(student=student, is_authorized=True).select_related("parent")
        for link in parent_links:
            parent_msg = f"Academic Report for {student_name}: {assessment.title} results released. {grade_info}."
            send_notification(
                recipient=link.parent,
                title=f"Exam Marks Released: {student_name} ({assessment.subject_name})",
                message=parent_msg,
                category=NotificationCategory.ACADEMICS,
                action_url=f"/academics/parent/{student.id}/",
                deduplication_key=f"test-res-par-{assessment.id}-{link.parent.id}-{student.id}",
                institution=assessment.institution,
            )


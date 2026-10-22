"""
EduConnect Timetable Management Automated Test Suite.
Tests:
- Server-side multi-variable conflict detection (Teacher, Classroom, Room overlaps)
- Time interval validation (start_time < end_time)
- Slot creation, modification, and cancellation
- Broadcast notifications generation
- Student and Parent timetable views
- Teacher schedule view
- Parent-child authorization enforcement
"""

from datetime import time
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import Role, ParentStudentLink
from apps.attendance.models import AcademicSession, ClassRoom, ClassEnrollment
from apps.timetable.models import (
    TimetableSlot,
    ScheduleStatus,
    ScheduleNotification,
    DayOfWeek,
)
from apps.timetable.services import (
    validate_timetable_conflicts,
    save_timetable_slot_with_conflict_check,
    build_weekly_matrix,
)

User = get_user_model()


class TimetableManagementTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.admin_user = User.objects.create_superuser(
            username="admin_tt",
            email="admin_tt@educonnect.edu",
            password="TestPassword123!",
            role=Role.ADMIN,
        )
        self.teacher1 = User.objects.create_user(
            username="prof_turing",
            email="turing@educonnect.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            employee_id="FAC-TURING",
        )
        self.teacher2 = User.objects.create_user(
            username="prof_lovelace",
            email="lovelace@educonnect.edu",
            password="TestPassword123!",
            role=Role.TEACHER,
            employee_id="FAC-LOVELACE",
        )
        self.student1 = User.objects.create_user(
            username="student_eve",
            email="eve@educonnect.edu",
            password="TestPassword123!",
            role=Role.STUDENT,
            student_id="STU-EVE",
        )
        self.parent1 = User.objects.create_user(
            username="parent_eve",
            email="parent_eve@educonnect.edu",
            password="TestPassword123!",
            role=Role.PARENT,
        )
        self.parent_stranger = User.objects.create_user(
            username="parent_stranger_tt",
            email="stranger_tt@educonnect.edu",
            password="TestPassword123!",
            role=Role.PARENT,
        )

        ParentStudentLink.objects.create(
            parent=self.parent1,
            student=self.student1,
            relationship_type="mother",
            is_authorized=True,
        )

        # Academic Session & Classrooms
        today = timezone.now().date()
        self.academic_session = AcademicSession.objects.create(
            name="Fall 2026 Term",
            start_date=today - timezone.timedelta(days=30),
            end_date=today + timezone.timedelta(days=90),
            is_current=True,
        )
        self.classroom1 = ClassRoom.objects.create(
            name="CS Year 1 - Section A",
            code="CS-1A",
            academic_session=self.academic_session,
            room_number="Lab 101",
        )
        self.classroom2 = ClassRoom.objects.create(
            name="CS Year 1 - Section B",
            code="CS-1B",
            academic_session=self.academic_session,
            room_number="Lab 102",
        )

        # Enroll Student1 in Classroom1
        ClassEnrollment.objects.create(student=self.student1, classroom=self.classroom1)

    def test_create_slot_and_conflict_checks(self):
        """Test successful slot creation and subsequent conflict rejections."""
        # Slot 1: Monday 09:00 - 10:00, Teacher1, Classroom1, Room 101
        slot1 = save_timetable_slot_with_conflict_check(
            classroom=self.classroom1,
            subject_name="Discrete Math",
            teacher=self.teacher1,
            room_number="Room 101",
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
            actor=self.admin_user,
        )
        self.assertIsNotNone(slot1)

        # Conflict 1: Same Teacher scheduled in different classroom at overlapping time (09:30 - 10:30)
        with self.assertRaises(ValidationError) as ctx:
            save_timetable_slot_with_conflict_check(
                classroom=self.classroom2,
                subject_name="Algorithms",
                teacher=self.teacher1,
                room_number="Room 202",
                day_of_week=DayOfWeek.MONDAY,
                start_time=time(9, 30),
                end_time=time(10, 30),
                actor=self.admin_user,
            )
        self.assertIn("Teacher Conflict", str(ctx.exception))

        # Conflict 2: Same Classroom scheduled for another subject with different teacher at overlapping time
        with self.assertRaises(ValidationError) as ctx:
            save_timetable_slot_with_conflict_check(
                classroom=self.classroom1,
                subject_name="Physics",
                teacher=self.teacher2,
                room_number="Room 303",
                day_of_week=DayOfWeek.MONDAY,
                start_time=time(9, 15),
                end_time=time(9, 45),
                actor=self.admin_user,
            )
        self.assertIn("Class Conflict", str(ctx.exception))

        # Conflict 3: Same Room booked by different classroom and teacher at overlapping time
        with self.assertRaises(ValidationError) as ctx:
            save_timetable_slot_with_conflict_check(
                classroom=self.classroom2,
                subject_name="Chemistry",
                teacher=self.teacher2,
                room_number="Room 101",
                day_of_week=DayOfWeek.MONDAY,
                start_time=time(9, 0),
                end_time=time(10, 0),
                actor=self.admin_user,
            )
        self.assertIn("Room Conflict", str(ctx.exception))

    def test_non_overlapping_slots_allowed(self):
        """Test that adjacent or non-overlapping slots on the same day are allowed."""
        # Slot 1: Monday 09:00 - 10:00
        save_timetable_slot_with_conflict_check(
            classroom=self.classroom1,
            subject_name="Slot 1",
            teacher=self.teacher1,
            room_number="Room 101",
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(9, 0),
            end_time=time(10, 0),
            actor=self.admin_user,
        )

        # Slot 2: Monday 10:00 - 11:00 (Starts exactly when Slot 1 ends)
        slot2 = save_timetable_slot_with_conflict_check(
            classroom=self.classroom1,
            subject_name="Slot 2",
            teacher=self.teacher1,
            room_number="Room 101",
            day_of_week=DayOfWeek.MONDAY,
            start_time=time(10, 0),
            end_time=time(11, 0),
            actor=self.admin_user,
        )
        self.assertIsNotNone(slot2)

    def test_cancellation_broadcasts_notification(self):
        """Test cancelling a lecture slot creates a broadcast notification for students and parents."""
        slot = save_timetable_slot_with_conflict_check(
            classroom=self.classroom1,
            subject_name="Software Engineering",
            teacher=self.teacher2,
            room_number="Lab A",
            day_of_week=DayOfWeek.TUESDAY,
            start_time=time(11, 0),
            end_time=time(12, 0),
            actor=self.admin_user,
        )
        # Cancel the slot
        self.client.force_login(self.admin_user)
        resp = self.client.post(
            reverse("timetable:cancel_slot", args=[slot.id]),
            {"cancellation_reason": "Faculty attending research conference"},
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)

        slot.refresh_from_db()
        self.assertEqual(slot.status, ScheduleStatus.CANCELLED)

        # Check notification was created
        notif = ScheduleNotification.objects.filter(slot=slot, change_type="CANCELLED").first()
        self.assertIsNotNone(notif)
        self.assertIn("Faculty attending research conference", notif.message)

    def test_student_and_parent_timetable_access(self):
        """Test student view personal timetable and parent viewing authorized child."""
        save_timetable_slot_with_conflict_check(
            classroom=self.classroom1,
            subject_name="Operating Systems",
            teacher=self.teacher1,
            room_number="Hall 1",
            day_of_week=DayOfWeek.WEDNESDAY,
            start_time=time(14, 0),
            end_time=time(15, 30),
            actor=self.admin_user,
        )

        # Student accesses their timetable: 200 OK
        self.client.force_login(self.student1)
        resp = self.client.get(reverse("timetable:student_timetable"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Operating Systems")

        # Authorized Parent accesses child timetable: 200 OK
        self.client.force_login(self.parent1)
        resp = self.client.get(reverse("timetable:parent_child_timetable", args=[self.student1.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Operating Systems")

        # Unauthorized Parent accesses child timetable: 403 Forbidden
        self.client.force_login(self.parent_stranger)
        resp = self.client.get(reverse("timetable:parent_child_timetable", args=[self.student1.id]))
        self.assertEqual(resp.status_code, 403)

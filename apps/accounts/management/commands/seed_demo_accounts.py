"""
Management command to seed comprehensive demonstration accounts and linked operational records.
Creates accounts for all 6 roles with predictable test credentials:
- Admin (admin / Admin@12345)
- Subject Teacher (teacher / Teacher@12345)
- Student (student / Student@12345)
- Parent (parent / Parent@12345)
- Accounts Staff (accounts / Accounts@12345)
- Applicant (applicant / Applicant@12345)
Also seeds linked classrooms, enrollments, fee allocations, timetable slots, attendance,
and grievance tickets so all role dashboards are rich and functional.
"""

from decimal import Decimal
import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.accounts.models import Role, User, ParentStudentLink
from apps.core.models import Course
from apps.attendance.models import (
    AcademicSession,
    ClassRoom,
    ClassEnrollment,
    TeacherAssignment,
    AttendancePolicy,
    AttendanceSession,
    AttendanceRecord,
    AttendanceStatus,
)
from apps.timetable.models import TimetableSlot, DayOfWeek, ScheduleStatus
from apps.academics.models import StudyMaterial, Assignment
from apps.fees.models import (
    FeeCategory,
    FeeStructure,
    FeeStructureItem,
    StudentFeeAllocation,
    FeeInstallment,
    Payment,
    PaymentMethod,
    PaymentStatus,
    AllocationStatus,
    InstallmentStatus,
)
from apps.admissions.models import AdmissionApplication, ApplicationStatus
from apps.complaints.models import ComplaintCategory, ComplaintTicket, TicketPriority, TicketStatus
from apps.notifications.models import Notification, NotificationCategory, Announcement
from apps.reports.models import InstitutionSetting, AdminAuditLog


class Command(BaseCommand):
    help = "Seeds all 6 primary role users and operational link data for interactive testing."

    def handle(self, *args, **options):
        self.stdout.write("--- Provisioning EduConnect Roles & Demonstration Records ---")

        # 0. Global Institution Settings
        settings_obj = InstitutionSetting.get_settings()
        self.stdout.write(f"Verified institution settings: {settings_obj.institution_name}")

        # 1. Provision Users
        # Admin
        admin_user, _ = User.objects.get_or_create(username="admin")
        admin_user.email = "admin@educonnect.local"
        admin_user.first_name = "System"
        admin_user.last_name = "Administrator"
        admin_user.role = Role.ADMIN
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.is_active = True
        admin_user.set_password("Admin@12345")
        admin_user.save()
        self.stdout.write("Created/Updated User: admin (Role: Admin)")

        # Teacher
        teacher_user, _ = User.objects.get_or_create(username="teacher")
        teacher_user.email = "sarah.jenkins@educonnect.local"
        teacher_user.first_name = "Sarah"
        teacher_user.last_name = "Jenkins"
        teacher_user.role = Role.TEACHER
        teacher_user.is_staff = True
        teacher_user.employee_id = "EMP-T-101"
        teacher_user.subject_specialization = "Computer Science & AI"
        teacher_user.bio = "Senior Faculty in Computer Systems & Artificial Intelligence with 10+ years experience."
        teacher_user.is_active = True
        teacher_user.set_password("Teacher@12345")
        teacher_user.save()
        self.stdout.write("Created/Updated User: teacher (Role: Teacher)")

        # Student
        student_user, _ = User.objects.get_or_create(username="student")
        student_user.email = "alex.rivera@educonnect.local"
        student_user.first_name = "Alex"
        student_user.last_name = "Rivera"
        student_user.role = Role.STUDENT
        student_user.student_id = "STU-2026-001"
        student_user.grade_level = "Grade 12-A"
        student_user.phone_number = "+1 (555) 014-9921"
        student_user.address = "742 Evergreen Terrace, Tech District"
        student_user.is_active = True
        student_user.set_password("Student@12345")
        student_user.save()
        self.stdout.write("Created/Updated User: student (Role: Student)")

        # Parent
        parent_user, _ = User.objects.get_or_create(username="parent")
        parent_user.email = "marcus.rivera@educonnect.local"
        parent_user.first_name = "Marcus"
        parent_user.last_name = "Rivera"
        parent_user.role = Role.PARENT
        parent_user.phone_number = "+1 (555) 019-3388"
        parent_user.address = "742 Evergreen Terrace, Tech District"
        parent_user.is_active = True
        parent_user.set_password("Parent@12345")
        parent_user.save()
        self.stdout.write("Created/Updated User: parent (Role: Parent)")

        # Accounts Staff
        accounts_user, _ = User.objects.get_or_create(username="accounts")
        accounts_user.email = "elena.rostova@educonnect.local"
        accounts_user.first_name = "Elena"
        accounts_user.last_name = "Rostova"
        accounts_user.role = Role.ACCOUNTS
        accounts_user.is_staff = True
        accounts_user.employee_id = "EMP-A-201"
        accounts_user.phone_number = "+1 (555) 012-7744"
        accounts_user.is_active = True
        accounts_user.set_password("Accounts@12345")
        accounts_user.save()
        self.stdout.write("Created/Updated User: accounts (Role: Accounts Staff)")

        # Applicant
        applicant_user, _ = User.objects.get_or_create(username="applicant")
        applicant_user.email = "jordan.hayes@educonnect.local"
        applicant_user.first_name = "Jordan"
        applicant_user.last_name = "Hayes"
        applicant_user.role = Role.APPLICANT
        applicant_user.phone_number = "+1 (555) 018-4455"
        applicant_user.address = "12 Oakridge Boulevard, City Center"
        applicant_user.is_active = True
        applicant_user.set_password("Applicant@12345")
        applicant_user.save()
        self.stdout.write("Created/Updated User: applicant (Role: Applicant)")

        # 2. Parent-Student Link
        link, _ = ParentStudentLink.objects.update_or_create(
            parent=parent_user,
            student=student_user,
            defaults={
                "relationship_type": "father",
                "is_authorized": True,
                "notes": "Verified primary biological parent & tuition sponsor.",
            },
        )
        self.stdout.write(f"Linked Parent '{parent_user.username}' to Student '{student_user.username}'")

        # 3. Academic Session & Attendance Policy
        academic_session, _ = AcademicSession.objects.update_or_create(
            name="Academic Year 2026-2027",
            defaults={
                "start_date": datetime.date(2026, 8, 1),
                "end_date": datetime.date(2027, 6, 30),
                "is_current": True,
            },
        )
        policy, _ = AttendancePolicy.objects.update_or_create(
            name="Standard Institutional Attendance Policy",
            defaults={
                "minimum_required_percentage": Decimal("75.00"),
                "present_weight": Decimal("1.00"),
                "late_weight": Decimal("0.50"),
                "excused_weight": Decimal("1.00"),
                "absent_weight": Decimal("0.00"),
                "is_active": True,
            },
        )

        # 4. Target Course & Classroom
        cs_course = Course.objects.filter(code="BS-CS-201").first()
        if not cs_course:
            cs_course = Course.objects.first()

        classroom, _ = ClassRoom.objects.update_or_create(
            code="CLS-12A",
            defaults={
                "name": "Grade 12 - Section A",
                "course": cs_course,
                "academic_session": academic_session,
                "room_number": "Hall 302",
                "capacity": 35,
                "description": "Advanced STEM and Computer Science Senior Cohort.",
                "is_active": True,
            },
        )
        self.stdout.write(f"Classroom ready: {classroom.name} ({classroom.code})")

        # 5. Class Enrollment & Teacher Assignment
        enrollment, _ = ClassEnrollment.objects.update_or_create(
            student=student_user,
            classroom=classroom,
            defaults={
                "roll_number": "12A-01",
                "enrolled_date": datetime.date(2026, 8, 15),
                "is_active": True,
            },
        )
        assignment_auth, _ = TeacherAssignment.objects.update_or_create(
            teacher=teacher_user,
            classroom=classroom,
            subject_name="Computer Science & AI",
            defaults={"is_active": True},
        )
        self.stdout.write("Class enrollment and teacher assignment verified.")

        # 6. Attendance Sessions & Records
        today = timezone.now().date()
        for i, delta in enumerate([3, 2, 1, 0]):
            session_date = today - datetime.timedelta(days=delta)
            session, _ = AttendanceSession.objects.update_or_create(
                classroom=classroom,
                subject_name="Computer Science & AI",
                session_date=session_date,
                session_period="Period 1",
                defaults={
                    "teacher": teacher_user,
                    "topic": f"Module {i+1}: Advanced Systems & Algorithms",
                    "created_by": teacher_user,
                },
            )
            status = AttendanceStatus.PRESENT if delta != 2 else AttendanceStatus.LATE
            remarks = "On time and engaged" if status == AttendanceStatus.PRESENT else "Arrived 10 minutes late due to transit"
            AttendanceRecord.objects.update_or_create(
                session=session,
                student=student_user,
                defaults={
                    "status": status,
                    "remarks": remarks,
                    "marked_by": teacher_user,
                },
            )
        self.stdout.write("Seeded 4 live attendance sessions with verified student records.")

        # 7. Timetable Slots
        slots_data = [
            (DayOfWeek.MONDAY, datetime.time(9, 0), datetime.time(10, 30), "Hall 302"),
            (DayOfWeek.WEDNESDAY, datetime.time(10, 45), datetime.time(12, 15), "Hall 302"),
            (DayOfWeek.FRIDAY, datetime.time(13, 0), datetime.time(14, 30), "Robotics Lab 105"),
        ]
        for day, st, et, room in slots_data:
            TimetableSlot.objects.update_or_create(
                classroom=classroom,
                day_of_week=day,
                start_time=st,
                end_time=et,
                defaults={
                    "subject_name": "Computer Science & AI",
                    "teacher": teacher_user,
                    "room_number": room,
                    "status": ScheduleStatus.ACTIVE,
                },
            )
        self.stdout.write("Created weekly recurring timetable slots.")

        # 8. Academics: Study Materials & Assignment
        study_mat, _ = StudyMaterial.objects.update_or_create(
            classroom=classroom,
            subject_name="Computer Science & AI",
            title="Unit 1: Full-Stack Architecture & MongoDB Backend",
            defaults={
                "teacher": teacher_user,
                "description": "Comprehensive reference notes on document modeling, query indexing, and security policies.",
            },
        )
        assignment, _ = Assignment.objects.update_or_create(
            classroom=classroom,
            subject_name="Computer Science & AI",
            title="Lab Assignment 1: Distributed Data Processing Pipeline",
            defaults={
                "teacher": teacher_user,
                "description": "Design an optimized schema and test data pipeline. Submit your repository link or zip archive.",
                "max_score": Decimal("100.00"),
                "due_datetime": timezone.now() + datetime.timedelta(days=7),
                "is_published": True,
            },
        )
        self.stdout.write("Provisioned active coursework assignment and study notes.")

        # 9. Fees Management: Category, Structure, Allocation, Installments & Payment
        cat_tuition, _ = FeeCategory.objects.update_or_create(
            code="TUI-26",
            defaults={"name": "Annual Tuition Fee", "description": "Core academic tuition.", "is_active": True},
        )
        cat_lab, _ = FeeCategory.objects.update_or_create(
            code="LAB-26",
            defaults={"name": "Specialized STEM Lab Fee", "description": "Lab equipment and consumable fee.", "is_active": True},
        )

        fee_structure, _ = FeeStructure.objects.update_or_create(
            code="FS-CS-2026",
            defaults={
                "title": "Senior Computer Science Academic Package 2026-2027",
                "academic_year": "2026-2027",
                "course": cs_course,
                "total_amount": Decimal("3500.00"),
                "created_by": accounts_user,
                "is_active": True,
            },
        )
        FeeStructureItem.objects.update_or_create(
            fee_structure=fee_structure,
            category=cat_tuition,
            defaults={"amount": Decimal("2800.00"), "is_optional": False},
        )
        FeeStructureItem.objects.update_or_create(
            fee_structure=fee_structure,
            category=cat_lab,
            defaults={"amount": Decimal("700.00"), "is_optional": False},
        )

        allocation, _ = StudentFeeAllocation.objects.update_or_create(
            student=student_user,
            academic_year="2026-2027",
            defaults={
                "fee_structure": fee_structure,
                "gross_amount": Decimal("3500.00"),
                "discount_amount": Decimal("500.00"),
                "discount_reason": "Academic Merit Scholarship Grant",
                "net_amount": Decimal("3000.00"),
                "amount_paid": Decimal("1500.00"),
                "outstanding_balance": Decimal("1500.00"),
                "status": AllocationStatus.PARTIALLY_PAID,
                "created_by": accounts_user,
                "notes": "Tuition split across 2 milestones.",
            },
        )

        inst1, _ = FeeInstallment.objects.update_or_create(
            allocation=allocation,
            installment_number=1,
            defaults={
                "title": "Term 1 Advance Installment",
                "amount": Decimal("1500.00"),
                "due_date": today - datetime.timedelta(days=10),
                "amount_paid": Decimal("1500.00"),
                "status": InstallmentStatus.PAID,
            },
        )
        inst2, _ = FeeInstallment.objects.update_or_create(
            allocation=allocation,
            installment_number=2,
            defaults={
                "title": "Term 2 Final Settlement",
                "amount": Decimal("1500.00"),
                "due_date": today + datetime.timedelta(days=45),
                "amount_paid": Decimal("0.00"),
                "status": InstallmentStatus.PENDING,
            },
        )

        Payment.objects.update_or_create(
            transaction_reference="BANK-TXN-20260901-0982",
            defaults={
                "allocation": allocation,
                "installment": inst1,
                "student": student_user,
                "amount": Decimal("1500.00"),
                "payment_method": PaymentMethod.BANK_TRANSFER,
                "payer_name": "Marcus Rivera",
                "payer_relationship": "Father",
                "idempotency_key": "PAY-IDEM-001-AUTO-SEED",
                "status": PaymentStatus.VERIFIED,
                "verified_by": accounts_user,
                "verification_date": timezone.now() - datetime.timedelta(days=9),
                "notes": "Verified against institutional bank statement ledger.",
            },
        )
        self.stdout.write("Provisioned student fee allocation with verified Term 1 payment receipt.")

        # 10. Admission Application for Applicant Jordan Hayes
        AdmissionApplication.objects.update_or_create(
            application_number="ADM-2026-881290",
            defaults={
                "applicant": applicant_user,
                "course": cs_course or Course.objects.first(),
                "first_name": "Jordan",
                "last_name": "Hayes",
                "email": "jordan.hayes@educonnect.local",
                "phone_number": "+1 (555) 018-4455",
                "date_of_birth": datetime.date(2005, 4, 18),
                "gender": "male",
                "nationality": "American",
                "address_line1": "12 Oakridge Boulevard",
                "city": "New York",
                "state": "NY",
                "postal_code": "10001",
                "country": "United States",
                "guardian_name": "Robert Hayes",
                "guardian_relationship": "Father",
                "guardian_phone": "+1 (555) 018-9900",
                "previous_institution": "Metro STEM Academy",
                "previous_qualification": "High School Diploma",
                "previous_grade_or_percentage": "3.85 GPA",
                "year_of_passing": 2026,
                "statement_of_purpose": "Aspiring to study Computer Science & AI at EduConnect to innovate in distributed intelligence.",
                "status": ApplicationStatus.UNDER_REVIEW,
                "admin_notes": "Strong background in mathematics and algorithmic problem solving.",
            },
        )
        self.stdout.write("Created active admission application for Jordan Hayes.")

        # 11. Complaints / Helpdesk Categories & Ticket
        ComplaintCategory.ensure_default_categories()
        comp_cat = ComplaintCategory.objects.filter(code="facilities").first()
        ComplaintTicket.objects.update_or_create(
            ticket_number="TKT-202609-A001",
            defaults={
                "submitter": student_user,
                "category": comp_cat,
                "subject": "Request for extended GPU cluster access in Lab 302",
                "description": "We are training convolutional models for the upcoming Science Fair and request 2 extra evening hours access.",
                "priority": TicketPriority.MEDIUM,
                "status": TicketStatus.IN_PROGRESS,
                "assigned_to": admin_user,
            },
        )
        self.stdout.write("Created helpdesk ticket TKT-202609-A001.")

        # 12. Notifications & Announcements
        announcement, _ = Announcement.objects.update_or_create(
            title="Fall Term Orientation & Welcome Address",
            defaults={
                "content": "Welcome to the new academic year at EduConnect! Please review your course schedule and lab safety guidelines.",
                "published_by": admin_user,
                "is_published": True,
            },
        )

        # In-app notifications
        notifications_data = [
            (student_user, "Assignment Released", "Lab Assignment 1 has been posted by Prof. Sarah Jenkins.", NotificationCategory.ACADEMICS, "/academics/assignments/"),
            (student_user, "Fee Receipt Confirmed", "Your payment of $1,500.00 has been verified by the Accounts Department.", NotificationCategory.FEES, "/fees/portal/"),
            (parent_user, "Attendance Notification", "Alex Rivera was marked Present in Computer Science & AI today.", NotificationCategory.ATTENDANCE, "/accounts/dashboard/parent/"),
            (teacher_user, "Upcoming Class Today", "Period 1: Computer Science & AI at 09:00 AM in Hall 302.", NotificationCategory.TIMETABLE, "/timetable/teacher/"),
            (accounts_user, "Fee Allocation Reconciled", "Student Alex Rivera (STU-2026-001) completed Term 1 payment.", NotificationCategory.FEES, "/fees/admin/allocations/"),
            (applicant_user, "Application Status: Under Review", "Your application ADM-2026-881290 is currently undergoing faculty review.", NotificationCategory.ADMISSION, "/accounts/dashboard/applicant/"),
        ]
        for user, title, msg, cat, url in notifications_data:
            Notification.objects.update_or_create(
                recipient=user,
                title=title,
                defaults={
                    "message": msg,
                    "category": cat,
                    "action_url": url,
                    "is_read": False,
                },
            )
        self.stdout.write("Created contextual in-app notifications for all role users.")

        # 13. Audit Log
        AdminAuditLog.objects.create(
            actor=admin_user,
            action="SYSTEM_INITIALIZE_DEMO",
            description="System populated with multi-role demonstration accounts and operational data.",
            target_model="All",
            target_id="N/A",
            ip_address="127.0.0.1",
        )

        self.stdout.write(self.style.SUCCESS("\n[SUCCESS] Successfully provisioned all EduConnect roles and live database content!"))
        self.stdout.write(self.style.SUCCESS("----------------------------------------------------------------------"))
        self.stdout.write(self.style.SUCCESS("Available Test Accounts (Password for all: <Username_Capitalized>@12345):"))
        self.stdout.write(" 1. Admin:        username: admin     | password: Admin@12345")
        self.stdout.write(" 2. Teacher:      username: teacher   | password: Teacher@12345")
        self.stdout.write(" 3. Student:      username: student   | password: Student@12345")
        self.stdout.write(" 4. Parent:       username: parent    | password: Parent@12345")
        self.stdout.write(" 5. Accounts:     username: accounts  | password: Accounts@12345")
        self.stdout.write(" 6. Applicant:    username: applicant | password: Applicant@12345")
        self.stdout.write(self.style.SUCCESS("----------------------------------------------------------------------"))

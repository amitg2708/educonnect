"""
Management command to backfill existing records to default institution
and seed a second coaching institute to verify complete multi-tenant isolation.
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import Role, ParentStudentLink
from apps.institutions.models import Institution, Branch, InstitutionMembership
from apps.core.models import Course
from apps.attendance.models import AcademicSession, ClassRoom, ClassEnrollment, TeacherAssignment, AttendancePolicy, AttendanceSession
from apps.timetable.models import TimetableSlot
from apps.academics.models import StudyMaterial, Assignment, Assessment, StudentDoubt
from apps.fees.models import FeeCategory, FeeStructure, FeeStructureItem, StudentFeeAllocation, FeeInstallment, Payment, PaymentMethod, PaymentStatus
from apps.admissions.models import AdmissionApplication
from apps.complaints.models import ComplaintCategory, ComplaintTicket
from apps.notifications.models import Notification, Announcement
from apps.reports.models import InstitutionSetting, AdminAuditLog

User = get_user_model()


class Command(BaseCommand):
    help = "Backfill default institution for existing data and seed secondary coaching institute"

    def handle(self, *args, **options):
        self.stdout.write("Initializing multi-tenant provisioning...")

        # 1. Primary Institution
        educonnect, _ = Institution.objects.get_or_create(
            code="EDUCONNECT",
            defaults={
                "name": "EduConnect International Academy",
                "tagline": "Empowering Future Leaders & Scholars",
                "contact_email": "admin@educonnect.local",
                "contact_phone": "+1-800-555-0100",
                "address": "100 Academic Way, Tech City",
                "primary_color": "#1e3a8a",
                "accent_color": "#f59e0b",
                "is_active": True,
            },
        )
        edu_main_branch, _ = Branch.objects.get_or_create(
            institution=educonnect,
            code="MAIN",
            defaults={
                "name": "Main Campus",
                "address": "100 Academic Way, Tech City",
                "phone": "+1-800-555-0101",
                "is_main": True,
            },
        )
        self.stdout.write(f"Default institution: {educonnect.name} ({educonnect.code})")

        # 2. Backfill existing models with default institution
        models_to_backfill = [
            (Course, "courses"),
            (AcademicSession, "academic sessions"),
            (ClassRoom, "classrooms"),
            (AttendanceSession, "attendance sessions"),
            (AttendancePolicy, "attendance policies"),
            (TimetableSlot, "timetable slots"),
            (StudyMaterial, "study materials"),
            (Assignment, "assignments"),
            (Assessment, "assessments"),
            (StudentDoubt, "student doubts"),
            (FeeCategory, "fee categories"),
            (FeeStructure, "fee structures"),
            (StudentFeeAllocation, "fee allocations"),
            (Payment, "payments"),
            (AdmissionApplication, "admissions"),
            (ComplaintCategory, "complaint categories"),
            (ComplaintTicket, "complaint tickets"),
            (Notification, "notifications"),
            (Announcement, "announcements"),
            (AdminAuditLog, "audit logs"),
            (ParentStudentLink, "parent student links"),
        ]

        for model_cls, label in models_to_backfill:
            count = model_cls.objects.filter(institution__isnull=True).update(institution=educonnect)
            if count:
                self.stdout.write(f"  Backfilled {count} {label} to {educonnect.code}")

        # Ensure institution setting
        InstitutionSetting.objects.get_or_create(
            institution=educonnect,
            defaults={
                "institution_name": educonnect.name,
                "academic_year": "2026-2027",
                "attendance_minimum_percent": Decimal("75.00"),
            },
        )

        # 3. Backfill InstitutionMembership for all existing users
        for u in User.objects.all():
            m, created = InstitutionMembership.objects.get_or_create(
                user=u,
                institution=educonnect,
                defaults={
                    "role": u.role,
                    "branch": edu_main_branch,
                    "is_default": True,
                    "is_active": True,
                },
            )
            if created:
                self.stdout.write(f"  Created default membership for {u.username} ({u.role}) at {educonnect.code}")

        # 4. Secondary Institution (Apex Coaching Institute)
        apex, _ = Institution.objects.get_or_create(
            code="APEX",
            defaults={
                "name": "Apex Coaching Institute",
                "tagline": "Pioneering STEM, Medical & Engineering Excellence",
                "contact_email": "desk@apexcoaching.local",
                "contact_phone": "+1-800-555-0200",
                "address": "450 Science Park Avenue, Metro Hub",
                "primary_color": "#dc2626",
                "accent_color": "#f97316",
                "is_active": True,
            },
        )
        apex_north_branch, _ = Branch.objects.get_or_create(
            institution=apex,
            code="NORTH",
            defaults={
                "name": "Apex North Campus",
                "address": "450 Science Park Avenue, Metro Hub",
                "phone": "+1-800-555-0201",
                "is_main": True,
            },
        )
        apex_south_branch, _ = Branch.objects.get_or_create(
            institution=apex,
            code="SOUTH",
            defaults={
                "name": "Apex South Campus",
                "address": "88 Innovation Boulevard",
                "phone": "+1-800-555-0202",
                "is_main": False,
            },
        )
        self.stdout.write(f"Provisioned secondary institution: {apex.name} ({apex.code})")

        # Create dedicated users for Apex Coaching
        def create_apex_user(username, email, role, first, last):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "role": role,
                    "first_name": first,
                    "last_name": last,
                    "phone_number": "+1-555-999-0001",
                    "is_active": True,
                },
            )
            if created:
                user.set_password("Admin@123")
                user.save()
            InstitutionMembership.objects.get_or_create(
                user=user,
                institution=apex,
                defaults={"role": role, "branch": apex_north_branch, "is_default": True, "is_active": True},
            )
            return user

        apex_admin = create_apex_user("apex_admin", "admin@apex.local", Role.ADMIN, "Victor", "ApexAdmin")
        apex_teacher = create_apex_user("apex_teacher", "teacher@apex.local", Role.TEACHER, "Dr. Robert", "Hooke")
        apex_student = create_apex_user("apex_student", "student@apex.local", Role.STUDENT, "Elena", "Rostova")
        apex_accounts = create_apex_user("apex_accounts", "accounts@apex.local", Role.ACCOUNTS, "Marcus", "Vance")
        apex_parent = create_apex_user("apex_parent", "parent@apex.local", Role.PARENT, "Dmitri", "Rostov")

        # Link parent and student for Apex
        ParentStudentLink.objects.get_or_create(
            institution=apex,
            parent=apex_parent,
            student=apex_student,
            defaults={"relationship_type": "father", "is_authorized": True},
        )

        # 5. Cross-Institute User:
        # A person holding different roles at different institutes!
        # E.g. "multirole_user" is a Teacher at EduConnect, and a Parent at Apex!
        multi_user, created = User.objects.get_or_create(
            username="multirole_user",
            defaults={
                "email": "multirole@domain.com",
                "role": Role.TEACHER,
                "first_name": "Samantha",
                "last_name": "Cross",
                "phone_number": "+1-555-888-0002",
                "is_active": True,
            },
        )
        if created:
            multi_user.set_password("Admin@123")
            multi_user.save()

        # Membership 1: Teacher at EduConnect
        InstitutionMembership.objects.get_or_create(
            user=multi_user,
            institution=educonnect,
            defaults={"role": Role.TEACHER, "branch": edu_main_branch, "is_default": True, "is_active": True},
        )

        # Membership 2: Parent at Apex
        InstitutionMembership.objects.get_or_create(
            user=multi_user,
            institution=apex,
            defaults={"role": Role.PARENT, "branch": apex_north_branch, "is_default": False, "is_active": True},
        )
        ParentStudentLink.objects.get_or_create(
            institution=apex,
            parent=multi_user,
            student=apex_student,
            defaults={"relationship_type": "mother", "is_authorized": True},
        )

        # 6. Seed Apex domain records (Courses, Classes, Fees, Timetable, Announcements)
        apex_course, _ = Course.objects.get_or_create(
            institution=apex,
            code="APEX-JEE",
            defaults={
                "title": "JEE Advanced Physics & Mathematics",
                "department": "Engineering Sciences",
                "duration": "2 Years",
                "fee_per_term": Decimal("1250.00"),
                "description": "Intensive test preparation cohort for engineering admissions.",
                "level": Course.Level.SECONDARY,
                "is_active": True,
            },
        )

        apex_term, _ = AcademicSession.objects.get_or_create(
            institution=apex,
            name="Apex 2026 Term 1",
            defaults={
                "start_date": timezone.now().date(),
                "end_date": timezone.now().date() + timezone.timedelta(days=180),
                "is_current": True,
            },
        )

        apex_class, _ = ClassRoom.objects.get_or_create(
            institution=apex,
            code="APEX-B1",
            defaults={
                "name": "Batch Alpha - JEE 2026",
                "course": apex_course,
                "branch": apex_north_branch,
                "academic_session": apex_term,
                "capacity": 30,
                "room_number": "Apex Hall 101",
                "is_active": True,
            },
        )

        ClassEnrollment.objects.get_or_create(
            classroom=apex_class,
            student=apex_student,
            defaults={"roll_number": "APX-001", "is_active": True},
        )

        TeacherAssignment.objects.get_or_create(
            classroom=apex_class,
            teacher=apex_teacher,
            subject_name="Advanced Physics",
            defaults={"is_active": True},
        )

        # Apex Fee Structure & Payment
        apex_fee_cat, _ = FeeCategory.objects.get_or_create(
            institution=apex,
            name="Tuition Fee",
            defaults={"code": "APX-TUI", "is_active": True},
        )

        apex_fee_struct, _ = FeeStructure.objects.get_or_create(
            institution=apex,
            code="APX-JEE-2026",
            defaults={
                "title": "JEE Advanced Complete Course Fee",
                "course": apex_course,
                "academic_year": "2026",
                "total_amount": Decimal("2500.00"),
                "created_by": apex_admin,
            },
        )

        FeeStructureItem.objects.get_or_create(
            fee_structure=apex_fee_struct,
            category=apex_fee_cat,
            defaults={"amount": Decimal("2500.00")},
        )

        apex_alloc, _ = StudentFeeAllocation.objects.get_or_create(
            institution=apex,
            student=apex_student,
            fee_structure=apex_fee_struct,
            academic_year="2026",
            defaults={
                "gross_amount": Decimal("2500.00"),
                "net_amount": Decimal("2500.00"),
                "amount_paid": Decimal("1000.00"),
                "outstanding_balance": Decimal("1500.00"),
                "created_by": apex_accounts,
            },
        )

        apex_payment, _ = Payment.objects.get_or_create(
            institution=apex,
            transaction_reference="APX-PAY-1001",
            defaults={
                "allocation": apex_alloc,
                "student": apex_student,
                "amount": Decimal("1000.00"),
                "payment_method": PaymentMethod.BANK_TRANSFER,
                "payer_name": "Dmitri Rostov",
                "status": PaymentStatus.VERIFIED,
                "recorded_by": apex_accounts,
            },
        )

        # Apex Announcement
        Announcement.objects.get_or_create(
            institution=apex,
            title="Welcome to Apex Coaching Institute!",
            defaults={
                "content": "Orientation for JEE Advanced 2026 batches commences this Monday at North Campus.",
                "target_role": "all",
                "is_published": True,
                "published_by": apex_admin,
            },
        )

        self.stdout.write(self.style.SUCCESS("Multi-tenant seeding and backfill completed successfully!"))

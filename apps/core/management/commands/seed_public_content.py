"""
Management command to seed realistic, production-oriented public portal content into MongoDB.
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from apps.core.models import Course, Achievement, GalleryItem, Announcement, Facility


class Command(BaseCommand):
    help = "Seeds database-backed public courses, achievements, gallery items, announcements, and facilities."

    def handle(self, *args, **options):
        # 1. Seed Courses
        courses_data = [
            {
                "code": "SEC-STEM-101",
                "title": "Secondary STEM & Computational Thinking",
                "department": "School of Secondary Studies",
                "level": Course.Level.SECONDARY,
                "duration": "2 Years (Grades 11-12)",
                "description": "Rigorous college-preparatory program emphasizing physics, calculus, computer programming, and experimental design.",
                "eligibility": "Successful completion of Grade 10 with minimum 80% in Mathematics and Science.",
                "syllabus_overview": "Term 1: Advanced Calculus & Mechanics\nTerm 2: Electromagnetism & Data Structures\nTerm 3: Applied Chemistry & Algorithms\nTerm 4: Capstone Science Exhibition Project",
                "fee_per_term": Decimal("1850.00"),
                "is_featured": True,
            },
            {
                "code": "BS-CS-201",
                "title": "B.Sc. in Computer Science & Artificial Intelligence",
                "department": "School of Computing & Engineering",
                "level": Course.Level.UNDERGRADUATE,
                "duration": "4 Years (8 Semesters)",
                "description": "Comprehensive undergraduate program covering software architecture, machine learning, cloud databases, and cybersecurity.",
                "eligibility": "Senior secondary graduation with mathematics prerequisites and competitive entrance assessment score.",
                "syllabus_overview": "Year 1: Programming Fundamentals & Discrete Mathematics\nYear 2: Algorithms, Computer Architecture & Database Systems\nYear 3: Distributed Systems, Deep Learning & Web Technologies\nYear 4: Enterprise Practicum & Industry Capstone",
                "fee_per_term": Decimal("3200.00"),
                "is_featured": True,
            },
            {
                "code": "BA-COMM-105",
                "title": "B.A. in Media Studies & Strategic Communication",
                "department": "School of Humanities & Social Sciences",
                "level": Course.Level.UNDERGRADUATE,
                "duration": "3 Years (6 Semesters)",
                "description": "Interdisciplinary degree in investigative journalism, digital media production, corporate communications, and media ethics.",
                "eligibility": "Secondary school certificate with high proficiency in English literature and social sciences.",
                "syllabus_overview": "Sem 1: History of Mass Communication\nSem 2: News Writing & Digital Storytelling\nSem 3: Broadcast Journalism & Podcasting\nSem 4: Media Law, Ethics & Public Relations\nSem 5-6: Professional Media Internship",
                "fee_per_term": Decimal("2450.00"),
                "is_featured": True,
            },
            {
                "code": "DIP-BUS-301",
                "title": "Diploma in Business Analytics & FinTech",
                "department": "School of Business & Administration",
                "level": Course.Level.DIPLOMA,
                "duration": "1 Year (2 Semesters)",
                "description": "Executive credential in predictive financial modeling, corporate governance, PowerBI reporting, and quantitative risk analysis.",
                "eligibility": "Associate degree or bachelor's diploma in any quantitative or commercial discipline.",
                "syllabus_overview": "Module 1: Corporate Finance & Accounting Principles\nModule 2: Python for Financial Modeling\nModule 3: Business Intelligence Dashboards\nModule 4: FinTech Regulatory Compliance",
                "fee_per_term": Decimal("1600.00"),
                "is_featured": False,
            },
        ]

        for c_data in courses_data:
            course, created = Course.objects.update_or_create(code=c_data["code"], defaults=c_data)
            status = "Created" if created else "Updated"
            self.stdout.write(f"Course: {status} '{course.code} - {course.title}'")

        # 2. Seed Facilities
        facilities_data = [
            {
                "title": "Advanced Robotics & AI Laboratory",
                "category": "STEM Infrastructure",
                "description": "Equipped with NVIDIA GPU training rigs, robotic arms, 3D printing stations, and IoT sensor arrays.",
                "icon": "bi-cpu",
                "display_order": 1,
            },
            {
                "title": "Central Multi-Media Library",
                "category": "Learning Resources",
                "description": "Houses 55,000+ volumes, JSTOR & IEEE database access terminals, sound-isolated group pods, and quiet reading halls.",
                "icon": "bi-book",
                "display_order": 2,
            },
            {
                "title": "Olympic Gymnasium & Aquatic Center",
                "category": "Athletics",
                "description": "Features a heated 25m indoor competition pool, hardwood basketball court, cardio gym, and synthetic athletics track.",
                "icon": "bi-trophy",
                "display_order": 3,
            },
            {
                "title": "Auditorium & Performing Arts Center",
                "category": "Campus Cultural Life",
                "description": "A 750-seat acoustic auditorium with professional stage lighting, dressing wings, and Dolby surround sound.",
                "icon": "bi-music-note-beamed",
                "display_order": 4,
            },
        ]

        for f_data in facilities_data:
            fac, created = Facility.objects.update_or_create(title=f_data["title"], defaults=f_data)
            status = "Created" if created else "Updated"
            self.stdout.write(f"Facility: {status} '{fac.title}'")

        # 3. Seed Achievements
        achievements_data = [
            {
                "title": "National STEM Olympiad First Place Champions",
                "category": Achievement.Category.ACADEMIC,
                "year": 2026,
                "recipient": "EduConnect Senior Robotics Delegation",
                "description": "Secured the first-place gold trophy competing against 180 institutions in autonomous robotics and algorithmic optimization.",
                "is_featured": True,
            },
            {
                "title": "State Interscholastic Cross-Country Champions",
                "category": Achievement.Category.SPORTS,
                "year": 2025,
                "recipient": "Varsity Cross-Country Squad",
                "description": "Captured the regional championship banner with five individual runners placing in the top ten medal positions.",
                "is_featured": True,
            },
            {
                "title": "ISO 21001:2018 Educational Management Certification",
                "category": Achievement.Category.ACCREDITATION,
                "year": 2025,
                "recipient": "EduConnect Institution",
                "description": "Recognized with international standard compliance for pedagogical quality, learner satisfaction, and academic security.",
                "is_featured": True,
            },
        ]

        for a_data in achievements_data:
            ach, created = Achievement.objects.update_or_create(title=a_data["title"], defaults=a_data)
            status = "Created" if created else "Updated"
            self.stdout.write(f"Achievement: {status} '{ach.title}'")

        # 4. Seed Announcements
        announcements_data = [
            {
                "title": "Fall 2026 Admissions Open - Early Application Window",
                "category": Announcement.Category.ADMISSIONS,
                "priority": Announcement.Priority.HIGH,
                "content": "Prospective applicants and parents are invited to apply for upcoming fall enrollment. Early decision deadline is November 30.",
            },
            {
                "title": "Annual Inter-School Science & Innovation Symposium",
                "category": Announcement.Category.EVENTS,
                "priority": Announcement.Priority.STANDARD,
                "content": "Student science and engineering exhibitions will take place in the main auditorium on November 15. All parents and visitors welcome.",
            },
            {
                "title": "Mid-Term Examination Timetable Released",
                "category": Announcement.Category.EXAMS,
                "priority": Announcement.Priority.STANDARD,
                "content": "The official examination schedule is now active. Students and teachers may review individual timetable details in their portal accounts.",
            },
        ]

        for an_data in announcements_data:
            ann, created = Announcement.objects.update_or_create(title=an_data["title"], defaults=an_data)
            status = "Created" if created else "Updated"
            self.stdout.write(f"Announcement: {status} '{ann.title}'")

        # 5. Seed Gallery Items
        gallery_data = [
            {
                "title": "Modern Campus Quad & Architecture",
                "category": GalleryItem.Category.CAMPUS,
                "caption": "The central landscaped campus quad connecting academic faculties and student halls.",
            },
            {
                "title": "Advanced STEM Robotics Studio",
                "category": GalleryItem.Category.LABS,
                "caption": "Students assembling and programming competition robots in the engineering workshop.",
            },
            {
                "title": "Central Reading Room & Digital Archives",
                "category": GalleryItem.Category.LIBRARY,
                "caption": "Quiet study desks and research terminals in the multi-story digital library wing.",
            },
        ]

        for g_data in gallery_data:
            item, created = GalleryItem.objects.update_or_create(title=g_data["title"], defaults=g_data)
            status = "Created" if created else "Updated"
            self.stdout.write(f"Gallery Item: {status} '{item.title}'")

        self.stdout.write(self.style.SUCCESS("Successfully seeded all public portal content!"))

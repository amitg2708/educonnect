"""
Management command to securely provision the initial EduConnect administrator.
Usage:
    python manage.py create_educonnect_admin
    python manage.py create_educonnect_admin --username admin --email admin@educonnect.local --password MySecurePassword123!
"""

import os
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from apps.accounts.models import Role, User


class Command(BaseCommand):
    help = "Securely provision or update the initial EduConnect Administrator account."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            help="Username for the administrator account.",
        )
        parser.add_argument(
            "--email",
            type=str,
            help="Email address for the administrator.",
        )
        parser.add_argument(
            "--password",
            type=str,
            help="Initial administrator password.",
        )
        parser.add_argument(
            "--noinput",
            action="store_true",
            help="Do not prompt for input; read from arguments or environment variables.",
        )

    def handle(self, *args, **options):
        username = options.get("username") or os.getenv("ADMIN_USERNAME")
        email = options.get("email") or os.getenv("ADMIN_EMAIL", "admin@educonnect.local")
        password = options.get("password") or os.getenv("ADMIN_PASSWORD")
        noinput = options.get("noinput", False)

        if not username:
            if noinput:
                username = "admin"
            else:
                username = input("Enter Administrator username [default: admin]: ").strip() or "admin"

        if not email:
            if noinput:
                email = "admin@educonnect.local"
            else:
                email = input("Enter Administrator email [default: admin@educonnect.local]: ").strip() or "admin@educonnect.local"

        if not password:
            if noinput:
                raise CommandError("Password is required when running with --noinput unless ADMIN_PASSWORD is set in environment.")
            import getpass
            password = getpass.getpass("Enter Administrator password: ").strip()
            confirm_password = getpass.getpass("Confirm Administrator password: ").strip()
            if password != confirm_password:
                raise CommandError("Passwords do not match.")

        # Validate password against configured validators
        try:
            validate_password(password)
        except ValidationError as e:
            self.stderr.write(self.style.WARNING("Password validation warnings: " + "; ".join(e.messages)))

        # Create or update Administrator user
        user, created = User.objects.get_or_create(username=username)
        user.email = email
        user.role = Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(password)
        user.save()

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully {action} Administrator '{username}' ({email}) with role '{user.get_role_display()}'."
            )
        )

"""
EduConnect Role-based Authorization Decorators.
Enforces strict server-side access control.
"""

from functools import wraps
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from .models import Role


def role_required(*allowed_roles):
    """
    Decorator to enforce that the logged-in user possesses one of the specified roles.
    Superusers automatically pass all role checks.
    Unauthenticated users are redirected to the login page with the next parameter.
    Authenticated users lacking the required role receive HTTP 403 Forbidden.
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                path = request.get_full_path()
                return redirect(f"/accounts/login/?{REDIRECT_FIELD_NAME}={path}")

            # Superusers always pass
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            # Check user role against allowed roles
            if request.user.role in allowed_roles:
                return view_func(request, *args, **kwargs)

            # Raise 403 PermissionDenied for unauthorized roles
            raise PermissionDenied(
                f"Access denied: You do not have the required permissions for this section. "
                f"Your active role is '{request.user.get_role_display()}'. Required: {', '.join(allowed_roles)}."
            )

        return _wrapped_view

    return decorator


# Convenience role decorators
admin_required = role_required(Role.ADMIN)
teacher_required = role_required(Role.TEACHER, Role.ADMIN)
student_required = role_required(Role.STUDENT, Role.ADMIN)
parent_required = role_required(Role.PARENT, Role.ADMIN)
accounts_required = role_required(Role.ACCOUNTS, Role.ADMIN)
applicant_required = role_required(Role.APPLICANT, Role.ADMIN)

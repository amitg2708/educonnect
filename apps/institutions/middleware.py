"""
EduConnect Multi-Tenant Resolution Middleware.
Resolves and binds the active Institution, Branch, and Role context to every request.
Enforces that multi-role users possess the correct scoped permissions for the selected institute.
"""

from typing import Optional
from django.utils.deprecation import MiddlewareMixin
from apps.accounts.models import Role
from apps.institutions.models import Institution, InstitutionMembership


def resolve_institution_from_request(request) -> Optional[Institution]:
    """
    Resolves the Institution tenant based on:
    1. Custom Domain mapping (e.g. Host: apexacademy.com)
    2. Subdomain mapping (e.g. apex.educonnect.local)
    3. Custom Header: X-Institution-Slug or X-Institution-Domain
    4. Query parameter ?institute=<slug> or ?institution=<slug>
    5. URL path prefix /institute/<slug>/
    6. Session stored 'active_institution_id'
    7. Fallback to first active Institution
    """
    try:
        # 1. Custom domain mapping (strip port)
        host = request.get_host().split(":")[0].lower()
        if host and host not in ["localhost", "127.0.0.1", "testserver"]:
            inst_by_domain = Institution.objects.filter(custom_domain__iexact=host, is_active=True).first()
            if inst_by_domain:
                return inst_by_domain

            # 2. Subdomain mapping
            parts = host.split(".")
            if len(parts) >= 2:
                sub = parts[0]
                inst_by_sub = Institution.objects.filter(subdomain__iexact=sub, is_active=True).first()
                if inst_by_sub:
                    return inst_by_sub

        # 3. Custom Header
        header_slug = request.META.get("HTTP_X_INSTITUTION_SLUG")
        if header_slug:
            inst = Institution.objects.filter(slug=header_slug, is_active=True).first() or \
                   Institution.objects.filter(code__iexact=header_slug, is_active=True).first()
            if inst:
                return inst

        header_domain = request.META.get("HTTP_X_INSTITUTION_DOMAIN")
        if header_domain:
            inst = Institution.objects.filter(custom_domain__iexact=header_domain, is_active=True).first()
            if inst:
                return inst

        # 4. Query param
        query_slug = request.GET.get("institute") or request.GET.get("institution")
        if query_slug:
            inst = Institution.objects.filter(slug=query_slug, is_active=True).first() or \
                   Institution.objects.filter(code__iexact=query_slug, is_active=True).first()
            if inst:
                return inst

        # 5. URL path prefix /institute/<slug>/
        path = request.path_info
        if path.startswith("/institute/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 2:
                inst_slug = parts[1]
                inst = Institution.objects.filter(slug=inst_slug, is_active=True).first() or \
                       Institution.objects.filter(code__iexact=inst_slug, is_active=True).first()
                if inst:
                    return inst

        # 6. Session
        session_id = request.session.get("active_institution_id")
        if session_id:
            inst = Institution.objects.filter(id=session_id, is_active=True).first()
            if inst:
                return inst
    except Exception:
        pass

    # 7. Fallback default active institution
    return Institution.objects.filter(is_active=True).first()


class InstitutionMiddleware(MiddlewareMixin):
    """
    Middleware that attaches:
    - request.institution: Currently active Institution instance (or None)
    - request.active_membership: Currently active InstitutionMembership instance (or None)
    - request.user_role: The user's role specifically within request.institution
    - request.current_branch: Branch associated with membership (or None)
    - request.user_institutions: QuerySet of all institutions the user is actively a member of
    """

    def process_request(self, request):
        request.institution = None
        request.active_membership = None
        request.user_role = None
        request.current_branch = None
        request.user_institutions = Institution.objects.none()

        # Step 1: Detect explicit domain/subdomain/header/URL/session institution
        resolved_inst = resolve_institution_from_request(request)

        if not request.user.is_authenticated:
            # For anonymous visitors on public site, bind resolved institution
            request.institution = resolved_inst
            return None

        # Gather all active institutions for authenticated user
        user_memberships = InstitutionMembership.objects.filter(
            user=request.user,
            is_active=True,
            institution__is_active=True,
        ).select_related("institution", "branch")

        user_inst_ids = [m.institution_id for m in user_memberships]
        if request.user.is_superuser:
            request.user_institutions = Institution.objects.filter(is_active=True)
        else:
            request.user_institutions = Institution.objects.filter(id__in=user_inst_ids, is_active=True)

        session_inst_id = request.session.get("active_institution_id")
        active_membership: Optional[InstitutionMembership] = None

        # 0. Prioritize explicitly requested institute via domain/subdomain/slug
        if resolved_inst:
            explicit_mem = user_memberships.filter(institution_id=resolved_inst.id).first()
            if explicit_mem:
                active_membership = explicit_mem

        # 1. Try resolving membership from session
        if not active_membership and session_inst_id:
            active_membership = user_memberships.filter(institution_id=session_inst_id).first()

        # 2. If not found or not in session, select default membership or first active membership
        if not active_membership:
            active_membership = user_memberships.filter(is_default=True).first() or user_memberships.first()
            if active_membership:
                request.session["active_institution_id"] = str(active_membership.institution_id)

        # 3. Handle platform superusers who might not have an explicit membership
        if not active_membership and request.user.is_superuser:
            target_inst = None
            if session_inst_id:
                target_inst = Institution.objects.filter(id=session_inst_id, is_active=True).first()
            if not target_inst:
                target_inst = Institution.objects.filter(is_active=True).first()

            if target_inst:
                request.institution = target_inst
                request.user_role = Role.ADMIN
                request.user_institutions = Institution.objects.filter(is_active=True)
                request.session["active_institution_id"] = str(target_inst.id)
                return None

        # 4. Bind resolved context to request
        if active_membership:
            request.institution = active_membership.institution
            request.active_membership = active_membership
            request.user_role = active_membership.role
            request.current_branch = active_membership.branch
        else:
            # Fallback for users with legacy account or no assigned membership
            request.user_role = getattr(request.user, "role", None)
            request.institution = Institution.objects.filter(is_active=True).first()

        return None

    def process_response(self, request, response):
        """
        Guarantees that authenticated user sessions, student records, fee details,
        and sensitive responses are marked with strict no-cache headers so they
        are NEVER stored in shared service-worker or browser caches.
        """
        if getattr(request, "user", None) and request.user.is_authenticated:
            response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response

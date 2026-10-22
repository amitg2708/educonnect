"""
EduConnect Template Context Processors for Multi-Tenancy.
Injects current institution branding, active user memberships, and branch context.
"""

def institution_context(request):
    """
    Supplies multi-tenant context variables to all Django templates.
    """
    institution = getattr(request, "institution", None)
    user_institutions = getattr(request, "user_institutions", None)
    active_role = getattr(request, "user_role", None)
    current_branch = getattr(request, "current_branch", None)
    active_membership = getattr(request, "active_membership", None)

    count_inst = user_institutions.count() if user_institutions is not None and hasattr(user_institutions, "count") else 0

    return {
        "current_institution": institution,
        "user_institutions": user_institutions,
        "has_multiple_institutions": count_inst > 1,
        "active_role": active_role,
        "current_branch": current_branch,
        "active_membership": active_membership,
    }

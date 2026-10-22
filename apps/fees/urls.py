"""
EduConnect Fees URL Configuration.
"""

from django.urls import path
from . import views

app_name = "fees"

urlpatterns = [
    # Student & Parent
    path("my-fees/", views.student_fee_overview, name="student_overview"),
    path("parent/child/<str:student_id>/", views.parent_child_fees_view, name="parent_child_fees"),
    path("receipt/<str:receipt_id>/download/", views.download_receipt_pdf, name="download_receipt"),

    # Accounts Staff & Admin
    path("desk/", views.accounts_fees_dashboard, name="dashboard"),
    path("structures/", views.fee_structure_list, name="structure_list"),
    path("structures/create/", views.fee_structure_create, name="structure_create"),
    path("structures/<str:structure_id>/", views.fee_structure_detail, name="structure_detail"),
    path("assign/", views.assign_fees_view, name="assign_fees"),
    path("allocations/", views.student_allocation_list, name="allocation_list"),
    path("allocations/<str:allocation_id>/", views.student_allocation_detail, name="allocation_detail"),
    path("allocations/<str:allocation_id>/pay/", views.record_offline_payment_view, name="record_payment"),
    path("allocations/<str:allocation_id>/adjust/", views.apply_fee_adjustment_view, name="apply_adjustment"),
    path("payments/", views.payment_list_view, name="payment_list"),
    path("payments/<str:payment_id>/verify/", views.verify_payment_view, name="verify_payment"),
    path("reports/overdue/", views.overdue_accounts_report, name="overdue_report"),
]

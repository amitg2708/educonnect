"""
URL Configuration for EduConnect Admissions Management.
"""

from django.urls import path
from . import views

app_name = "admissions"

urlpatterns = [
    # Applicant routes
    path("eligibility/", views.course_eligibility_view, name="eligibility"),
    path("apply/", views.apply_view, name="apply"),
    path("my-applications/", views.my_applications_view, name="my_applications"),
    path("application/<str:application_number>/", views.application_detail_view, name="application_detail"),
    path("application/<str:application_number>/edit/", views.edit_application_view, name="edit_application"),
    path("application/<str:application_number>/upload-document/", views.upload_document_view, name="upload_document"),
    path("application/<str:application_number>/resubmit/", views.resubmit_application_view, name="resubmit_application"),
    path("documents/<str:document_id>/download/", views.download_document_view, name="download_document"),

    # Administrative routes
    path("admin/applications/", views.admin_application_list_view, name="admin_application_list"),
    path("admin/applications/<str:application_number>/", views.admin_application_detail_view, name="admin_application_detail"),
    path("admin/applications/<str:application_number>/decision/", views.admin_application_decision_view, name="admin_application_decision"),
    path("admin/applications/<str:application_number>/convert/", views.admin_convert_to_student_view, name="admin_convert_student"),
    path("admin/documents/<str:document_id>/verify/", views.admin_verify_document_view, name="admin_verify_document"),

    # CRM Enquiries & Leads routes (Task 3)
    path("enquiry/", views.public_enquiry_create_view, name="public_enquiry"),
    path("enquiry/<slug:institution_slug>/", views.public_enquiry_create_view, name="public_enquiry_institution"),
    path("admin/enquiries/", views.admin_enquiries_list_view, name="admin_enquiry_list"),
    path("admin/enquiries/create/", views.admin_enquiry_create_view, name="admin_enquiry_create"),
    path("admin/enquiries/reports/source/", views.admin_enquiries_report_view, name="admin_enquiry_reports"),
    path("admin/enquiries/<str:enquiry_number>/", views.admin_enquiry_detail_view, name="admin_enquiry_detail"),
    path("admin/enquiries/<str:enquiry_number>/follow-up/", views.admin_enquiry_followup_view, name="admin_enquiry_followup"),
    path("admin/enquiries/<str:enquiry_number>/assign/", views.admin_enquiry_assign_view, name="admin_enquiry_assign"),
    path("admin/enquiries/<str:enquiry_number>/convert/", views.admin_enquiry_convert_view, name="admin_enquiry_convert"),
]


"""
EduConnect Fees Admin Configuration.
"""

from django.contrib import admin
from .models import (
    FeeCategory,
    FeeStructure,
    FeeStructureItem,
    StudentFeeAllocation,
    FeeInstallment,
    Payment,
    FeeReceipt,
    FeeAdjustment,
    FeeAuditLog,
)


class FeeStructureItemInline(admin.TabularInline):
    model = FeeStructureItem
    extra = 1


@admin.register(FeeCategory)
class FeeCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "created_at")
    search_fields = ("name", "code")


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ("title", "code", "academic_year", "course", "total_amount", "is_active")
    list_filter = ("academic_year", "is_active")
    search_fields = ("title", "code")
    inlines = [FeeStructureItemInline]


class FeeInstallmentInline(admin.TabularInline):
    model = FeeInstallment
    extra = 0
    readonly_fields = ("amount_paid", "status")


@admin.register(StudentFeeAllocation)
class StudentFeeAllocationAdmin(admin.ModelAdmin):
    list_display = (
        "student",
        "fee_structure",
        "academic_year",
        "net_amount",
        "amount_paid",
        "outstanding_balance",
        "status",
    )
    list_filter = ("status", "academic_year")
    search_fields = ("student__username", "student__student_id", "fee_structure__title")
    inlines = [FeeInstallmentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        "transaction_reference",
        "student",
        "amount",
        "payment_method",
        "status",
        "payment_date",
    )
    list_filter = ("status", "payment_method", "payment_date")
    search_fields = ("transaction_reference", "student__username", "payer_name")


@admin.register(FeeReceipt)
class FeeReceiptAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "payment", "issued_at", "is_cancelled")
    search_fields = ("receipt_number", "payment__transaction_reference")


@admin.register(FeeAdjustment)
class FeeAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("allocation", "adjustment_type", "amount", "authorized_by", "created_at")
    list_filter = ("adjustment_type", "created_at")


@admin.register(FeeAuditLog)
class FeeAuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "action", "actor", "allocation")
    list_filter = ("action", "timestamp")
    search_fields = ("action", "details")

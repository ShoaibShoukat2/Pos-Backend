from django.contrib import admin

from apps.hostel.models import (
    HostelBranch,
    HostelCustomer,
    HostelEmployee,
    HostelPayment,
    HostelReservation,
    HostelRoom,
)


@admin.register(HostelBranch)
class HostelBranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "business", "status")
    search_fields = ("name", "code")


@admin.register(HostelRoom)
class HostelRoomAdmin(admin.ModelAdmin):
    list_display = ("number", "branch", "floor", "capacity", "status")


@admin.register(HostelCustomer)
class HostelCustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "mobile", "branch", "status")
    search_fields = ("full_name", "mobile", "cnic")


@admin.register(HostelReservation)
class HostelReservationAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "status", "check_in_date")


@admin.register(HostelPayment)
class HostelPaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_no", "customer", "amount", "payment_date", "is_void")


@admin.register(HostelEmployee)
class HostelEmployeeAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "branch", "role", "status")

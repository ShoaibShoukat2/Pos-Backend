from django.contrib import admin

from apps.customers.models import Customer, CustomerSale


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "receivable_balance", "loyalty_points", "is_active")


@admin.register(CustomerSale)
class CustomerSaleAdmin(admin.ModelAdmin):
    list_display = ("number", "customer", "total", "paid_amount", "due_amount")

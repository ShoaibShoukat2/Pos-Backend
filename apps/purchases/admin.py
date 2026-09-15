from django.contrib import admin

from apps.purchases.models import GoodsReceipt, PurchaseOrder, Supplier, SupplierPayable


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "phone", "is_active")


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("number", "supplier", "branch", "status")


@admin.register(GoodsReceipt)
class GoodsReceiptAdmin(admin.ModelAdmin):
    list_display = ("number", "supplier", "branch", "status")


@admin.register(SupplierPayable)
class SupplierPayableAdmin(admin.ModelAdmin):
    list_display = ("supplier", "amount", "paid_amount", "status")

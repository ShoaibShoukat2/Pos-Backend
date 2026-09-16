from django.contrib import admin

from apps.pos.models import Sale, SaleLine, SaleReturn, SaleReturnLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0


class SaleReturnLineInline(admin.TabularInline):
    model = SaleReturnLine
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("number", "branch", "total", "net_total", "status", "created_at")
    inlines = [SaleLineInline]


@admin.register(SaleReturn)
class SaleReturnAdmin(admin.ModelAdmin):
    list_display = ("number", "sale", "refund_amount", "refund_method", "created_at")
    inlines = [SaleReturnLineInline]

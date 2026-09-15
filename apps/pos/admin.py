from django.contrib import admin

from apps.pos.models import Sale, SaleLine


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("number", "branch", "total", "status", "created_at")
    inlines = [SaleLineInline]

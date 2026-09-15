from django.contrib import admin

from apps.businesses.models import Branch, Business, Currency, InvoiceSettings, TaxRate


@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "business_type", "city", "country", "is_active")
    search_fields = ("name", "email", "tax_number")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "business", "city", "is_head_office", "is_active")
    list_filter = ("is_active", "is_head_office")


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "symbol", "business", "is_base")


@admin.register(TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "rate", "business", "is_default")


@admin.register(InvoiceSettings)
class InvoiceSettingsAdmin(admin.ModelAdmin):
    list_display = ("business", "prefix", "next_number", "paper_size")

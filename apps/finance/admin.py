from django.contrib import admin

from apps.finance.models import CashSession, Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "is_system")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("number", "category", "amount", "method")


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = ("number", "branch", "status", "opening_cash", "expected_cash", "actual_cash")

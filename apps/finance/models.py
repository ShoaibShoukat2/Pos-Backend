from django.conf import settings
from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel


class ExpenseCategory(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="expense_categories",
    )
    name = models.CharField(max_length=80)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "name")
        verbose_name_plural = "expense categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    CARD = "card", "Card"
    BANK = "bank", "Bank"
    WALLET = "wallet", "Wallet"


class Expense(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="expenses",
    )
    number = models.CharField(max_length=30)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    notes = models.CharField(max_length=255, blank=True)
    cash_session = models.ForeignKey(
        "CashSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]


class CashSession(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="cash_sessions",
    )
    number = models.CharField(max_length=30)
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="cash_sessions",
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="opened_cash_sessions",
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_cash_sessions",
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    opening_cash = models.DecimalField(max_digits=14, decimal_places=2)
    sales_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    customer_received = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expense_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    refund_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    supplier_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    actual_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    difference = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]

    def compute_expected(self):
        return (
            self.opening_cash
            + self.sales_cash
            + self.customer_received
            - self.expense_total
            - self.refund_total
            - self.supplier_paid
        )


class CashKind(models.TextChoices):
    OPENING = "opening", "Opening"
    SALE = "sale", "Sales cash"
    CUSTOMER_PAYMENT = "customer_payment", "Customer payment"
    EXPENSE = "expense", "Expense"
    REFUND = "refund", "Refund"
    SUPPLIER_PAYMENT = "supplier_payment", "Supplier payment"
    ADJUSTMENT = "adjustment", "Adjustment"


class CashMovement(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="cash_movements",
    )
    session = models.ForeignKey(CashSession, on_delete=models.CASCADE, related_name="movements")
    kind = models.CharField(max_length=20, choices=CashKind.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.UUIDField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_movements",
    )

    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]

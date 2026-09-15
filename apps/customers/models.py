from django.conf import settings
from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel
from apps.finance.models import PaymentMethod


class Customer(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="customers",
    )
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    receivable_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_purchases = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    loyalty_points = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    membership_tier = models.ForeignKey(
        "promotions.MembershipTier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customers",
    )
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "phone", "name")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["business", "is_active"], name="cust_biz_active_idx"),
            models.Index(fields=["business", "name"], name="cust_biz_name_idx"),
            models.Index(fields=["phone"], name="cust_phone_idx"),
        ]

    def __str__(self):
        return self.name


class CustomerLedgerType(models.TextChoices):
    SALE = "sale", "Credit sale"
    PAYMENT = "payment", "Payment"
    RETURN = "return", "Sale return"
    ADJUSTMENT = "adjustment", "Adjustment"


class CustomerLedgerEntry(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="customer_ledger",
    )
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="ledger")
    entry_type = models.CharField(max_length=16, choices=CustomerLedgerType.choices)
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
        related_name="customer_ledger_entries",
    )

    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]


class CustomerSale(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="customer_sales",
    )
    number = models.CharField(max_length=30)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="customer_sales",
    )
    total = models.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    due_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_method = models.CharField(
        max_length=12,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    loyalty_points = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_sales",
    )
    pos_sale = models.OneToOneField(
        "pos.Sale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_sale",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]


class CustomerPayment(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="customer_payments",
    )
    number = models.CharField(max_length=30)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="payments")
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="customer_payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_payments",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]

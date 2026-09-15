from django.conf import settings
from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel
from apps.finance.models import PaymentMethod


class SaleStatus(models.TextChoices):
    COMPLETED = "completed", "Completed"
    VOID = "void", "Void"


class Sale(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="pos_sales",
    )
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="pos_sales",
    )
    number = models.CharField(max_length=30)
    client_uuid = models.UUIDField()
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_sales",
    )
    status = models.CharField(max_length=12, choices=SaleStatus.choices, default=SaleStatus.COMPLETED)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    due_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    coupon = models.ForeignKey(
        "promotions.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
    )
    coupon_code = models.CharField(max_length=40, blank=True)
    manual_discount_kind = models.CharField(max_length=12, blank=True)
    manual_discount_value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    loyalty_earned = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    loyalty_redeemed = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    notes = models.CharField(max_length=255, blank=True)
    sold_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pos_sales",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = (("business", "number"), ("business", "client_uuid"))
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status", "created_at"], name="sale_biz_st_dt_idx"),
            models.Index(fields=["branch", "created_at"], name="sale_br_created_idx"),
        ]

    def __str__(self):
        return self.number


class SaleLine(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="pos_sale_lines",
    )
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="pos_sale_lines",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    free_qty = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2)
    promo_price = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    promo_name = models.CharField(max_length=160, blank=True)

    objects = BusinessScopedManager()

    class Meta:
        ordering = ["created_at"]


class SalePayment(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="pos_sale_payments",
    )
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    method = models.CharField(max_length=12, choices=PaymentMethod.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    objects = BusinessScopedManager()


class ScannerSession(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="scanner_sessions",
    )
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.CASCADE,
        related_name="scanner_sessions",
    )
    token = models.CharField(max_length=40, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scanner_sessions",
    )
    expires_at = models.DateTimeField()
    connected_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]


class ScannerEvent(TimeStampedModel):
    session = models.ForeignKey(ScannerSession, on_delete=models.CASCADE, related_name="events")
    code = models.CharField(max_length=120)
    consumed = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]


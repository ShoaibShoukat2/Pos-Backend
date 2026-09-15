from django.conf import settings
from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel


class MovementType(models.TextChoices):
    PURCHASE = "purchase", "Purchase"
    SALE = "sale", "Sale"
    SALE_RETURN = "sale_return", "Sale return"
    PURCHASE_RETURN = "purchase_return", "Purchase return"
    DAMAGE = "damage", "Damaged"
    EXPIRED = "expired", "Expired"
    ADJUSTMENT = "adjustment", "Adjustment"
    STOCK_IN = "stock_in", "Stock in"
    STOCK_OUT = "stock_out", "Stock out"
    TRANSFER_OUT = "transfer_out", "Transfer out"
    TRANSFER_IN = "transfer_in", "Transfer in"
    COUNT = "count", "Stock count"


INBOUND_TYPES = {
    MovementType.PURCHASE,
    MovementType.SALE_RETURN,
    MovementType.STOCK_IN,
    MovementType.TRANSFER_IN,
}

OUTBOUND_TYPES = {
    MovementType.SALE,
    MovementType.PURCHASE_RETURN,
    MovementType.DAMAGE,
    MovementType.EXPIRED,
    MovementType.STOCK_OUT,
    MovementType.TRANSFER_OUT,
}


class StockLevel(TimeStampedModel):
    """Cached on-hand quantity. Only InventoryEngine may write this row."""

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="stock_levels",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        related_name="stock_levels",
    )
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.CASCADE,
        related_name="stock_levels",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("variant", "branch")
        ordering = ["variant__product__name", "variant__name"]
        indexes = [
            models.Index(fields=["business", "branch"], name="stk_biz_branch_idx"),
            models.Index(fields=["business", "variant"], name="stk_biz_var_idx"),
        ]

    def __str__(self):
        return f"{self.variant} @ {self.branch}: {self.quantity}"


class StockMovement(TimeStampedModel):
    """Append-only ledger. On-hand stock is the sum of these rows."""

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        related_name="movements",
    )
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    movement_type = models.CharField(max_length=30, choices=MovementType.choices)
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        help_text="Signed delta applied to on-hand stock",
    )
    balance_after = models.DecimalField(max_digits=14, decimal_places=3)
    reason = models.CharField(max_length=255, blank=True)
    reference_type = models.CharField(max_length=40, blank=True)
    reference_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=80, unique=True, null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_movements",
    )

    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "created_at"], name="mov_biz_created_idx"),
            models.Index(fields=["business", "movement_type", "created_at"], name="mov_biz_type_dt_idx"),
            models.Index(fields=["variant", "created_at"], name="mov_var_created_idx"),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.quantity} {self.variant_id}"


class StockOperation(TimeStampedModel):
    class Kind(models.TextChoices):
        ADJUSTMENT = "adjustment", "Adjustment"
        STOCK_IN = "stock_in", "Stock in"
        STOCK_OUT = "stock_out", "Stock out"
        DAMAGE = "damage", "Damaged"
        EXPIRED = "expired", "Expired"
        COUNT = "count", "Stock count"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        CANCELLED = "cancelled", "Cancelled"

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="stock_operations",
    )
    number = models.CharField(max_length=30)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="stock_operations",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    reason = models.CharField(max_length=255, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_operations",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]


class StockOperationLine(TimeStampedModel):
    operation = models.ForeignKey(StockOperation, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    counted_quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)


class StockTransfer(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        CANCELLED = "cancelled", "Cancelled"

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="stock_transfers",
    )
    number = models.CharField(max_length=30)
    from_branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="transfers_out",
    )
    to_branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="transfers_in",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    reason = models.CharField(max_length=255, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transfers",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]


class StockTransferLine(TimeStampedModel):
    transfer = models.ForeignKey(StockTransfer, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)

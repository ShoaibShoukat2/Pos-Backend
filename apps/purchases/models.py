from django.conf import settings
from django.db import models
from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce

from apps.core.models import BusinessScopedManager, TimeStampedModel


class Supplier(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="suppliers",
    )
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80, blank=True)
    tax_number = models.CharField(max_length=60, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class PurchaseOrder(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ORDERED = "ordered", "Ordered"
        PARTIAL = "partial", "Partially received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="purchase_orders",
    )
    number = models.CharField(max_length=30)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    notes = models.CharField(max_length=255, blank=True)
    expected_date = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    def refresh_status(self):
        if self.status in (self.Status.DRAFT, self.Status.CANCELLED):
            return
        lines = list(self.lines.all())
        if not lines:
            return
        received_all = all(line.received_qty >= line.quantity for line in lines)
        received_any = any(line.received_qty > 0 for line in lines)
        next_status = self.Status.RECEIVED if received_all else (
            self.Status.PARTIAL if received_any else self.Status.ORDERED
        )
        if next_status != self.status:
            self.status = next_status
            self.save(update_fields=["status", "updated_at"])


class PurchaseOrderLine(TimeStampedModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    received_qty = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)

    @property
    def outstanding_qty(self):
        return self.quantity - self.received_qty

    @property
    def line_total(self):
        return self.quantity * self.unit_cost


class GoodsReceipt(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        CANCELLED = "cancelled", "Cancelled"

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="goods_receipts",
    )
    number = models.CharField(max_length=30)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="goods_receipts")
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="goods_receipts",
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipts",
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    notes = models.CharField(max_length=255, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="goods_receipts",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def total_amount(self):
        return self.lines.aggregate(
            total=Coalesce(Sum(F("quantity") * F("unit_cost")), Value(0))
        )["total"]


class GoodsReceiptLine(TimeStampedModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey("catalog.ProductVariant", on_delete=models.PROTECT)
    purchase_order_line = models.ForeignKey(
        PurchaseOrderLine,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="receipt_lines",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = models.DecimalField(max_digits=14, decimal_places=2)


class SupplierPayable(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PARTIAL = "partial", "Partial"
        PAID = "paid", "Paid"

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="supplier_payables",
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="payables")
    goods_receipt = models.OneToOneField(
        GoodsReceipt,
        on_delete=models.PROTECT,
        related_name="payable",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)

    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]

    @property
    def balance(self):
        return self.amount - self.paid_amount

    def refresh_status(self):
        if self.paid_amount <= 0:
            self.status = self.Status.OPEN
        elif self.paid_amount >= self.amount:
            self.status = self.Status.PAID
            self.paid_amount = self.amount
        else:
            self.status = self.Status.PARTIAL
        self.save(update_fields=["status", "paid_amount", "updated_at"])


class SupplierLedgerType(models.TextChoices):
    PURCHASE = "purchase", "Purchase"
    PAYMENT = "payment", "Payment"
    ADJUSTMENT = "adjustment", "Adjustment"


class SupplierLedgerEntry(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="supplier_ledger",
    )
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="ledger")
    entry_type = models.CharField(max_length=16, choices=SupplierLedgerType.choices)
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
        related_name="supplier_ledger_entries",
    )

    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]


class SupplierPayment(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="supplier_payments",
    )
    number = models.CharField(max_length=30)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="payments")
    branch = models.ForeignKey(
        "businesses.Branch",
        on_delete=models.PROTECT,
        related_name="supplier_payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    method = models.CharField(max_length=12, default="cash")
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supplier_payments",
    )

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "number")
        ordering = ["-created_at"]

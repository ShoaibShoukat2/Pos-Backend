from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.inventory.engine import apply_movement
from apps.inventory.models import MovementType
from apps.core.numbering import allocate_number
from apps.finance.cash import apply_cash, require_open_session
from apps.finance.models import CashKind, PaymentMethod
from apps.purchases.ledger import apply_supplier_ledger
from apps.purchases.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    SupplierLedgerType,
    SupplierPayable,
    SupplierPayment,
)

ZERO = Decimal("0")


@transaction.atomic
def create_purchase_order(*, business, user, supplier, branch, notes="", expected_date=None, lines):
    if not lines:
        raise ValidationError("Add at least one purchase line.")
    order = PurchaseOrder.objects.create(
        business=business,
        number=allocate_number(business, "PO", "PO"),
        supplier=supplier,
        branch=branch,
        notes=notes,
        expected_date=expected_date,
        created_by=user,
        status=PurchaseOrder.Status.DRAFT,
    )
    for row in lines:
        PurchaseOrderLine.objects.create(
            order=order,
            variant=row["variant"],
            quantity=row["quantity"],
            unit_cost=row["unit_cost"],
        )
    return order


@transaction.atomic
def mark_ordered(order):
    if order.status != PurchaseOrder.Status.DRAFT:
        raise ValidationError("Only draft purchase orders can be submitted.")
    if not order.lines.exists():
        raise ValidationError("Add lines before submitting the order.")
    order.status = PurchaseOrder.Status.ORDERED
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def cancel_order(order):
    if order.status in (PurchaseOrder.Status.RECEIVED, PurchaseOrder.Status.CANCELLED):
        raise ValidationError("This purchase order cannot be cancelled.")
    if order.lines.filter(received_qty__gt=0).exists():
        raise ValidationError("Cancel is blocked after goods have been received.")
    order.status = PurchaseOrder.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order


@transaction.atomic
def receive_goods(*, business, user, supplier, branch, purchase_order=None, notes="", lines):
    if not lines:
        raise ValidationError("Add at least one received line.")
    if purchase_order and purchase_order.status in (
        PurchaseOrder.Status.DRAFT,
        PurchaseOrder.Status.CANCELLED,
    ):
        raise ValidationError("Submit the purchase order before receiving goods.")

    receipt = GoodsReceipt.objects.create(
        business=business,
        number=allocate_number(business, "GRN", "GRN"),
        supplier=supplier,
        branch=branch,
        purchase_order=purchase_order,
        notes=notes,
        created_by=user,
        status=GoodsReceipt.Status.POSTED,
        posted_at=timezone.now(),
    )
    total = Decimal("0")
    for row in lines:
        variant = row["variant"]
        qty = Decimal(row["quantity"])
        cost = Decimal(row["unit_cost"])
        if qty <= 0:
            raise ValidationError("Received quantity must be greater than zero.")
        po_line = row.get("purchase_order_line")
        if purchase_order and po_line:
            outstanding = po_line.quantity - po_line.received_qty
            if qty > outstanding:
                raise ValidationError(
                    f"{variant.display_name}: receiving {qty} exceeds outstanding {outstanding}."
                )
            po_line.received_qty += qty
            po_line.save(update_fields=["received_qty", "updated_at"])
        line = GoodsReceiptLine.objects.create(
            receipt=receipt,
            variant=variant,
            purchase_order_line=po_line,
            quantity=qty,
            unit_cost=cost,
        )
        apply_movement(
            variant=variant,
            branch=branch,
            movement_type=MovementType.PURCHASE,
            quantity=qty,
            user=user,
            reason=f"Goods received {receipt.number}",
            reference_type="goods_receipt",
            reference_id=receipt.id,
            idempotency_key=f"grn:{receipt.id}:{line.id}",
        )
        total += qty * cost

    SupplierPayable.objects.create(
        business=business,
        supplier=supplier,
        goods_receipt=receipt,
        amount=total,
    )
    apply_supplier_ledger(
        supplier=supplier,
        entry_type=SupplierLedgerType.PURCHASE,
        amount=total,
        user=user,
        reason=f"Goods received {receipt.number}",
        reference_type="goods_receipt",
        reference_id=receipt.id,
    )
    if purchase_order:
        purchase_order.refresh_status()
    return receipt


@transaction.atomic
def pay_supplier(*, business, user, supplier, branch, amount, method="cash", notes=""):
    amount = Decimal(amount)
    if amount <= ZERO:
        raise ValidationError("Payment must be greater than zero.")
    open_payables = list(
        SupplierPayable.objects.select_for_update()
        .filter(business=business, supplier=supplier)
        .exclude(status=SupplierPayable.Status.PAID)
        .order_by("created_at")
    )
    outstanding = sum((p.amount - p.paid_amount for p in open_payables), Decimal("0"))
    if amount > outstanding:
        raise ValidationError(f"Only Rs {outstanding} is payable to {supplier.name}.")

    payment = SupplierPayment.objects.create(
        business=business,
        number=allocate_number(business, "SP", "SP"),
        supplier=supplier,
        branch=branch,
        amount=amount,
        method=method,
        notes=notes,
        created_by=user,
    )
    remaining = amount
    for payable in open_payables:
        if remaining <= 0:
            break
        due = payable.amount - payable.paid_amount
        applied = min(due, remaining)
        payable.paid_amount += applied
        payable.refresh_status()
        remaining -= applied

    apply_supplier_ledger(
        supplier=supplier,
        entry_type=SupplierLedgerType.PAYMENT,
        amount=amount,
        user=user,
        reason=f"Payment {payment.number}",
        reference_type="supplier_payment",
        reference_id=payment.id,
    )
    if method == PaymentMethod.CASH:
        session = require_open_session(branch)
        apply_cash(
            session=session,
            kind=CashKind.SUPPLIER_PAYMENT,
            amount=amount,
            user=user,
            reason=f"Supplier payment {payment.number}",
            reference_type="supplier_payment",
            reference_id=payment.id,
        )
    return payment

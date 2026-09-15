from decimal import Decimal

from django.db.models import F, Sum, Value
from django.db.models.functions import Coalesce
from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.purchases.models import SupplierLedgerEntry, SupplierLedgerType, SupplierPayable

ZERO = Decimal("0")


def supplier_outstanding(supplier) -> Decimal:
    return supplier.payables.aggregate(
        total=Coalesce(Sum(F("amount") - F("paid_amount")), Value(ZERO))
    )["total"] or ZERO


@transaction.atomic
def apply_supplier_ledger(
    *,
    supplier,
    entry_type: str,
    amount,
    user=None,
    reason="",
    reference_type="",
    reference_id=None,
):
    qty = Decimal(amount)
    if entry_type == SupplierLedgerType.ADJUSTMENT:
        delta = qty
    elif entry_type == SupplierLedgerType.PURCHASE:
        if qty <= ZERO:
            raise ValidationError("Purchase amount must be greater than zero.")
        delta = qty
    elif entry_type == SupplierLedgerType.PAYMENT:
        if qty <= ZERO:
            raise ValidationError("Payment amount must be greater than zero.")
        delta = -qty
    else:
        raise ValidationError(f"Unknown supplier ledger type: {entry_type}")

    last = (
        SupplierLedgerEntry.objects.select_for_update()
        .filter(supplier=supplier)
        .order_by("-created_at")
        .first()
    )
    new_balance = (last.balance_after if last else ZERO) + delta
    if new_balance < ZERO:
        raise ValidationError(
            f"Payment exceeds what is owed to {supplier.name}."
        )
    return SupplierLedgerEntry.objects.create(
        business=supplier.business,
        supplier=supplier,
        entry_type=entry_type,
        amount=delta,
        balance_after=new_balance,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=user,
    )

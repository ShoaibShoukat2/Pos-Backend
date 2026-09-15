"""Customer receivable ledger. +due increases what the customer owes."""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.customers.models import Customer, CustomerLedgerEntry, CustomerLedgerType

ZERO = Decimal("0")


def signed_receivable(entry_type: str, amount: Decimal) -> Decimal:
    qty = Decimal(amount)
    if entry_type == CustomerLedgerType.ADJUSTMENT:
        if qty == ZERO:
            raise ValidationError("Adjustment cannot be zero.")
        return qty
    if qty <= ZERO:
        raise ValidationError("Amount must be greater than zero.")
    if entry_type == CustomerLedgerType.SALE:
        return qty
    if entry_type in {CustomerLedgerType.PAYMENT, CustomerLedgerType.RETURN}:
        return -qty
    raise ValidationError(f"Unknown customer ledger type: {entry_type}")


@transaction.atomic
def apply_customer_ledger(
    *,
    customer,
    entry_type: str,
    amount,
    user=None,
    reason="",
    reference_type="",
    reference_id=None,
    allow_negative=False,
) -> CustomerLedgerEntry:
    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    delta = signed_receivable(entry_type, amount)
    new_balance = customer.receivable_balance + delta
    if new_balance < ZERO and not allow_negative:
        raise ValidationError(
            f"{customer.name} only owes {customer.receivable_balance}. Cannot post {delta}."
        )
    customer.receivable_balance = new_balance
    customer.save(update_fields=["receivable_balance", "updated_at"])
    return CustomerLedgerEntry.objects.create(
        business=customer.business,
        customer=customer,
        entry_type=entry_type,
        amount=delta,
        balance_after=new_balance,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=user,
    )

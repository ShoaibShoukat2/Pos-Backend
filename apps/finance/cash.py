"""
Single write path for the cash drawer.

Expected cash = opening + sales + customer receipts − expenses − refunds − supplier payments
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.numbering import allocate_number
from apps.finance.models import CashKind, CashMovement, CashSession

ZERO = Decimal("0")

INFLOW = {CashKind.OPENING, CashKind.SALE, CashKind.CUSTOMER_PAYMENT}
OUTFLOW = {CashKind.EXPENSE, CashKind.REFUND, CashKind.SUPPLIER_PAYMENT}


def signed_cash(kind: str, amount: Decimal) -> Decimal:
    qty = Decimal(amount)
    if kind == CashKind.ADJUSTMENT:
        if qty == ZERO:
            raise ValidationError("Cash adjustment cannot be zero.")
        return qty
    if qty <= ZERO:
        raise ValidationError("Amount must be greater than zero.")
    if kind in INFLOW:
        return qty
    if kind in OUTFLOW:
        return -qty
    raise ValidationError(f"Unknown cash movement: {kind}")


def open_session_for(branch):
    return CashSession.objects.select_for_update().filter(
        business=branch.business,
        branch=branch,
        status=CashSession.Status.OPEN,
    ).first()


@transaction.atomic
def open_shift(*, business, branch, user, opening_cash):
    opening = Decimal(opening_cash)
    if opening < ZERO:
        raise ValidationError("Opening cash cannot be negative.")
    if open_session_for(branch):
        raise ValidationError(f"{branch.name} already has an open cash shift.")
    session = CashSession.objects.create(
        business=business,
        number=allocate_number(business, "CSH", "CSH"),
        branch=branch,
        opened_by=user,
        opening_cash=opening,
        expected_cash=opening,
    )
    if opening > ZERO:
        apply_cash(
            session=session,
            kind=CashKind.OPENING,
            amount=opening,
            user=user,
            reason="Shift opening",
        )
    return session


@transaction.atomic
def apply_cash(
    *,
    session,
    kind: str,
    amount,
    user=None,
    reason="",
    reference_type="",
    reference_id=None,
    skip_zero=False,
):
    if session.status != CashSession.Status.OPEN:
        raise ValidationError("Cash shift is closed.")
    qty = Decimal(amount)
    if skip_zero and qty == ZERO:
        return None
    delta = signed_cash(kind, qty)
    session = CashSession.objects.select_for_update().get(pk=session.pk)
    if kind == CashKind.SALE:
        session.sales_cash += qty
    elif kind == CashKind.CUSTOMER_PAYMENT:
        session.customer_received += qty
    elif kind == CashKind.EXPENSE:
        session.expense_total += qty
    elif kind == CashKind.REFUND:
        session.refund_total += qty
    elif kind == CashKind.SUPPLIER_PAYMENT:
        session.supplier_paid += qty
    session.expected_cash = session.compute_expected()
    if session.expected_cash < ZERO:
        raise ValidationError(
            f"Not enough cash in the drawer. Expected would become {session.expected_cash}."
        )
    movement = CashMovement.objects.create(
        business=session.business,
        session=session,
        kind=kind,
        amount=delta,
        balance_after=session.expected_cash,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        created_by=user,
    )
    session.save(
        update_fields=[
            "sales_cash",
            "customer_received",
            "expense_total",
            "refund_total",
            "supplier_paid",
            "expected_cash",
            "updated_at",
        ]
    )
    return movement


def require_open_session(branch):
    session = open_session_for(branch)
    if not session:
        raise ValidationError(f"Open a cash shift for {branch.name} first.")
    return session


@transaction.atomic
def close_shift(*, session, user, actual_cash, notes=""):
    if session.status != CashSession.Status.CLOSED:
        session = CashSession.objects.select_for_update().get(pk=session.pk)
    if session.status == CashSession.Status.CLOSED:
        raise ValidationError("This shift is already closed.")
    actual = Decimal(actual_cash)
    if actual < ZERO:
        raise ValidationError("Actual cash cannot be negative.")
    session.expected_cash = session.compute_expected()
    session.actual_cash = actual
    session.difference = actual - session.expected_cash
    session.status = CashSession.Status.CLOSED
    session.closed_by = user
    session.closed_at = timezone.now()
    session.notes = notes
    session.save()
    return session

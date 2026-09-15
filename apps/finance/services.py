from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.core.numbering import allocate_number
from apps.finance.cash import apply_cash, require_open_session
from apps.finance.models import CashKind, Expense, PaymentMethod

ZERO = Decimal("0")


@transaction.atomic
def post_expense(*, business, user, category, branch, amount, method="cash", notes=""):
    amount = Decimal(amount)
    if amount <= ZERO:
        raise ValidationError("Expense amount must be greater than zero.")
    session = None
    if method == PaymentMethod.CASH:
        session = require_open_session(branch)
    expense = Expense.objects.create(
        business=business,
        number=allocate_number(business, "EXP", "EXP"),
        category=category,
        branch=branch,
        amount=amount,
        method=method,
        notes=notes,
        cash_session=session,
        created_by=user,
    )
    if session:
        apply_cash(
            session=session,
            kind=CashKind.EXPENSE,
            amount=amount,
            user=user,
            reason=f"Expense {expense.number} · {category.name}",
            reference_type="expense",
            reference_id=expense.id,
        )
    return expense

from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.core.numbering import allocate_number
from apps.customers.ledger import apply_customer_ledger
from apps.customers.models import CustomerLedgerType, CustomerPayment, CustomerSale
from apps.finance.cash import apply_cash, require_open_session
from apps.finance.models import CashKind, PaymentMethod

ZERO = Decimal("0")
LOYALTY_PER = Decimal("100")


def loyalty_points_for(total: Decimal) -> Decimal:
    if total <= ZERO:
        return ZERO
    return (total / LOYALTY_PER).to_integral_value(rounding=ROUND_DOWN)


@transaction.atomic
def post_customer_sale(*, business, user, customer, branch, total, paid_amount=0, payment_method="cash", notes=""):
    if customer.business_id != business.id or branch.business_id != business.id:
        raise ValidationError("Customer or branch does not belong to this business.")
    total = Decimal(total)
    paid = Decimal(paid_amount or 0)
    if total <= ZERO:
        raise ValidationError("Sale total must be greater than zero.")
    if paid < ZERO or paid > total:
        raise ValidationError("Paid amount must be between 0 and the sale total.")
    due = total - paid
    if due > ZERO and customer.credit_limit > ZERO:
        if customer.receivable_balance + due > customer.credit_limit:
            raise ValidationError(
                f"Credit limit Rs {customer.credit_limit} would be exceeded. "
                f"Current due Rs {customer.receivable_balance}."
            )

    sale = CustomerSale.objects.create(
        business=business,
        number=allocate_number(business, "CS", "CS"),
        customer=customer,
        branch=branch,
        total=total,
        paid_amount=paid,
        due_amount=due,
        payment_method=payment_method,
        loyalty_points=loyalty_points_for(total),
        notes=notes,
        created_by=user,
    )
    customer.total_purchases += total
    customer.loyalty_points += sale.loyalty_points
    customer.save(update_fields=["total_purchases", "loyalty_points", "updated_at"])

    if due > ZERO:
        apply_customer_ledger(
            customer=customer,
            entry_type=CustomerLedgerType.SALE,
            amount=due,
            user=user,
            reason=f"Credit sale {sale.number}",
            reference_type="customer_sale",
            reference_id=sale.id,
        )
    if paid > ZERO and payment_method == PaymentMethod.CASH:
        session = require_open_session(branch)
        apply_cash(
            session=session,
            kind=CashKind.SALE,
            amount=paid,
            user=user,
            reason=f"Sale {sale.number}",
            reference_type="customer_sale",
            reference_id=sale.id,
        )
    return sale


@transaction.atomic
def post_customer_payment(*, business, user, customer, branch, amount, method="cash", notes=""):
    if customer.business_id != business.id or branch.business_id != business.id:
        raise ValidationError("Customer or branch does not belong to this business.")
    amount = Decimal(amount)
    if amount <= ZERO:
        raise ValidationError("Payment must be greater than zero.")
    if amount > customer.receivable_balance:
        raise ValidationError(
            f"{customer.name} only owes Rs {customer.receivable_balance}."
        )
    payment = CustomerPayment.objects.create(
        business=business,
        number=allocate_number(business, "CP", "CP"),
        customer=customer,
        branch=branch,
        amount=amount,
        method=method,
        notes=notes,
        created_by=user,
    )
    apply_customer_ledger(
        customer=customer,
        entry_type=CustomerLedgerType.PAYMENT,
        amount=amount,
        user=user,
        reason=f"Payment {payment.number}",
        reference_type="customer_payment",
        reference_id=payment.id,
    )
    if method == PaymentMethod.CASH:
        session = require_open_session(branch)
        apply_cash(
            session=session,
            kind=CashKind.CUSTOMER_PAYMENT,
            amount=amount,
            user=user,
            reason=f"Customer payment {payment.number}",
            reference_type="customer_payment",
            reference_id=payment.id,
        )
    return payment

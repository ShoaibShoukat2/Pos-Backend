from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.core.numbering import allocate_number
from apps.customers.ledger import apply_customer_ledger
from apps.customers.models import Customer, CustomerLedgerType
from apps.finance.cash import apply_cash, require_open_session
from apps.finance.models import CashKind, PaymentMethod
from apps.inventory.engine import record_sale_return
from apps.pos.models import OPEN_SALE_STATUSES, Sale, SaleLine, SaleReturn, SaleReturnLine, SaleStatus
from apps.promotions.engine import ZERO, money

VALID_METHODS = {PaymentMethod.CASH, PaymentMethod.CARD, PaymentMethod.BANK, PaymentMethod.WALLET}


def _line_share(line: SaleLine, qty: Decimal, sale: Sale) -> Decimal:
    if line.quantity <= ZERO or qty <= ZERO:
        return ZERO
    gross = money(line.line_total * qty / line.quantity)
    if sale.subtotal <= ZERO:
        return ZERO
    return money(gross * sale.total / sale.subtotal)


@transaction.atomic
def process_sale_return(*, business, user, payload: dict) -> SaleReturn:
    sale = (
        Sale.objects.select_for_update()
        .select_related("customer", "branch")
        .filter(business=business, pk=payload.get("sale"))
        .first()
    )
    if not sale:
        raise ValidationError({"sale": "Ticket not found."})
    if sale.status not in OPEN_SALE_STATUSES:
        raise ValidationError("This ticket is already fully returned.")

    raw_lines = payload.get("lines") or []
    if not raw_lines:
        raise ValidationError({"lines": "Select at least one item to return."})

    lines = {
        str(row.id): row
        for row in SaleLine.objects.select_for_update().filter(sale=sale).select_related("variant__product")
    }
    planned = []
    for row in raw_lines:
        line = lines.get(str(row.get("sale_line") or row.get("id")))
        if not line:
            raise ValidationError({"lines": "An item on this ticket is missing."})
        qty = Decimal(str(row.get("quantity") or 0))
        remaining = line.quantity - line.returned_qty
        if qty <= ZERO:
            raise ValidationError({"lines": "Return quantity must be greater than zero."})
        if qty > remaining:
            raise ValidationError(
                {"lines": f"Only {remaining} of {line.variant.display_name} can still be returned."}
            )
        planned.append((line, qty, _line_share(line, qty, sale)))

    refund_amount = money(sum((share for _, _, share in planned), ZERO))
    remaining_net = money(sale.total - sale.returned_total)
    leftover = all(
        (row.quantity - row.returned_qty - next((qty for line, qty, _ in planned if line.id == row.id), ZERO)) <= ZERO
        for row in lines.values()
    )
    if leftover:
        refund_amount = remaining_net
        if planned:
            allocated = money(sum((share for _, _, share in planned[:-1]), ZERO))
            last_line, last_qty, _ = planned[-1]
            planned[-1] = (last_line, last_qty, money(max(ZERO, refund_amount - allocated)))
    elif refund_amount > remaining_net:
        refund_amount = remaining_net

    if refund_amount <= ZERO:
        raise ValidationError("Nothing left to refund on this ticket.")

    due_reduce = min(sale.due_amount, refund_amount)
    cash_refund = money(refund_amount - due_reduce)
    method = (payload.get("refund_method") or sale.payment_method or PaymentMethod.CASH).strip().lower()
    if method not in VALID_METHODS:
        raise ValidationError({"refund_method": "Choose cash, card, bank or wallet."})
    if cash_refund > ZERO and method == PaymentMethod.CASH:
        require_open_session(sale.branch)

    sale_return = SaleReturn.objects.create(
        business=business,
        branch=sale.branch,
        sale=sale,
        number=allocate_number(business, "RET", "RET"),
        refund_amount=refund_amount,
        credit_reduced=due_reduce,
        cash_refunded=cash_refund,
        refund_method=method,
        reason=(payload.get("reason") or "")[:255],
        created_by=user,
    )

    for line, qty, share in planned:
        SaleReturnLine.objects.create(
            business=business,
            sale_return=sale_return,
            sale_line=line,
            variant=line.variant,
            quantity=qty,
            amount=share,
        )
        line.returned_qty += qty
        line.returned_amount = money(line.returned_amount + share)
        line.save(update_fields=["returned_qty", "returned_amount", "updated_at"])
        if line.variant.product.track_stock:
            record_sale_return(
                variant=line.variant,
                branch=sale.branch,
                quantity=qty,
                user=user,
                reference_id=sale_return.id,
                reason=f"Return {sale_return.number} · {sale.number}",
            )

    sale.returned_total = money(sale.returned_total + refund_amount)
    sale.refunded_amount = money(sale.refunded_amount + cash_refund)
    sale.due_amount = money(sale.due_amount - due_reduce)
    sale.paid_amount = money(max(ZERO, sale.paid_amount - cash_refund))
    sale.net_total = money(max(ZERO, sale.total - sale.returned_total))
    sale.status = SaleStatus.RETURNED if leftover else SaleStatus.PARTIAL
    sale.save(
        update_fields=[
            "returned_total",
            "refunded_amount",
            "due_amount",
            "paid_amount",
            "net_total",
            "status",
            "updated_at",
        ]
    )

    if cash_refund > ZERO and method == PaymentMethod.CASH:
        session = require_open_session(sale.branch)
        apply_cash(
            session=session,
            kind=CashKind.REFUND,
            amount=cash_refund,
            user=user,
            reason=f"Return {sale_return.number} · {sale.number}",
            reference_type="pos_sale_return",
            reference_id=sale_return.id,
        )

    customer = sale.customer
    if customer:
        customer = Customer.objects.select_for_update().get(pk=customer.pk)
        if due_reduce > ZERO:
            apply_customer_ledger(
                customer=customer,
                entry_type=CustomerLedgerType.RETURN,
                amount=due_reduce,
                user=user,
                reason=f"Return {sale_return.number} · {sale.number}",
                reference_type="pos_sale_return",
                reference_id=sale_return.id,
            )
        if sale.total > ZERO:
            reverse_earned = money(sale.loyalty_earned * refund_amount / sale.total)
        else:
            reverse_earned = ZERO
        remaining_earned = money(max(ZERO, sale.loyalty_earned - sale.loyalty_returned))
        reverse_earned = min(reverse_earned, remaining_earned)
        if leftover:
            reverse_earned = remaining_earned
            customer.loyalty_points += sale.loyalty_redeemed
        customer.loyalty_points = money(max(ZERO, customer.loyalty_points - reverse_earned))
        customer.total_purchases = money(max(ZERO, customer.total_purchases - refund_amount))
        customer.save(update_fields=["loyalty_points", "total_purchases", "updated_at"])
        sale.loyalty_returned = money(sale.loyalty_returned + reverse_earned)
        sale.save(update_fields=["loyalty_returned", "updated_at"])
        cs = getattr(sale, "customer_sale", None)
        if cs:
            cs.total = sale.net_total
            cs.paid_amount = sale.paid_amount
            cs.due_amount = sale.due_amount
            cs.save(update_fields=["total", "paid_amount", "due_amount", "updated_at"])

    return (
        SaleReturn.objects.select_related("sale", "sale__customer", "branch", "created_by")
        .prefetch_related("lines__variant__product", "sale__lines__variant__product", "sale__payments")
        .get(pk=sale_return.pk)
    )

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError

from apps.catalog.models import ProductVariant
from apps.core.branch import accessible_branches
from apps.core.numbering import allocate_number
from apps.customers.ledger import apply_customer_ledger
from apps.customers.models import Customer, CustomerLedgerType, CustomerSale
from apps.finance.cash import apply_cash, require_open_session
from apps.finance.models import CashKind, PaymentMethod
from apps.inventory.engine import record_sale
from apps.pos.models import Sale, SaleLine, SalePayment, SaleStatus
from apps.promotions.engine import (
    ZERO,
    coupon_discount,
    earn_points,
    find_coupon,
    membership_discount,
    money,
    price_lines,
    redeem_value,
    tier_for,
)

TWOPLACES = Decimal("0.01")


def _parse_when(value):
    if not value:
        return timezone.now()
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if parsed is None:
        return timezone.now()
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


@transaction.atomic
def checkout_sale(*, business, user, payload: dict) -> Sale:
    client_uuid = payload.get("client_uuid")
    if not client_uuid:
        raise ValidationError({"client_uuid": "Required for offline sync."})
    existing = Sale.objects.filter(business=business, client_uuid=client_uuid).first()
    if existing:
        return existing

    branch_id = payload.get("branch")
    branch = accessible_branches(user).filter(pk=branch_id).first()
    if not branch:
        raise ValidationError({"branch": "Branch is not available to this user."})

    raw_lines = payload.get("lines") or []
    if not raw_lines:
        raise ValidationError({"lines": "Add at least one item."})

    variants = {
        str(v.id): v
        for v in ProductVariant.objects.filter(
            business=business,
            id__in=[row.get("variant") for row in raw_lines],
            is_active=True,
        ).select_related("product__category")
    }
    items = []
    for row in raw_lines:
        variant = variants.get(str(row.get("variant")))
        if not variant:
            raise ValidationError({"lines": "An item is missing or inactive."})
        items.append({"variant": variant, "quantity": row.get("quantity")})

    when = _parse_when(payload.get("sold_at"))
    priced = price_lines(business, items, when)
    subtotal = sum((row["line_total"] for row in priced), ZERO)

    coupon = find_coupon(business, payload.get("coupon_code"), when) if payload.get("coupon_code") else None
    disc_coupon = coupon_discount(subtotal, coupon)

    customer = None
    if payload.get("customer"):
        customer = Customer.objects.filter(business=business, pk=payload["customer"], is_active=True).first()
        if not customer:
            raise ValidationError({"customer": "Customer not found."})
    disc_member = membership_discount(subtotal - disc_coupon, customer)

    manual_kind = (payload.get("manual_discount_kind") or "").strip()
    manual_value = money(payload.get("manual_discount_value") or 0)
    if manual_kind and not user.has_module_permission("sale.discount"):
        raise ValidationError({"manual_discount_kind": "You cannot apply a manual discount."})
    remaining_after = max(ZERO, subtotal - disc_coupon - disc_member)
    if manual_kind == "percent":
        disc_manual = money(remaining_after * manual_value / Decimal("100"))
    elif manual_kind == "fixed":
        disc_manual = min(manual_value, remaining_after)
    else:
        disc_manual = ZERO
        manual_kind = ""

    after_discounts = max(ZERO, subtotal - disc_coupon - disc_member - disc_manual)
    redeem_requested = Decimal(payload.get("redeem_points") or 0)
    if redeem_requested and not customer:
        raise ValidationError({"redeem_points": "Select a customer to redeem points."})
    if customer and redeem_requested > customer.loyalty_points:
        raise ValidationError({"redeem_points": f"Customer only has {customer.loyalty_points} points."})
    disc_points, used_points = redeem_value(business, redeem_requested, after_discounts)

    discount_total = money(disc_coupon + disc_member + disc_manual + disc_points)
    total = money(max(ZERO, subtotal - discount_total))

    payments = payload.get("payments") or []
    paid = money(sum((Decimal(p.get("amount") or 0) for p in payments), ZERO))
    if paid < ZERO:
        raise ValidationError({"payments": "Payment cannot be negative."})
    if paid > total:
        raise ValidationError({"payments": "Paid amount cannot exceed the total."})
    due = money(total - paid)
    if due > ZERO and not customer:
        raise ValidationError({"customer": "A customer is required for credit."})
    if due > ZERO and customer and customer.credit_limit > ZERO:
        if customer.receivable_balance + due > customer.credit_limit:
            raise ValidationError(
                f"Credit limit Rs {customer.credit_limit} would be exceeded. "
                f"Current due Rs {customer.receivable_balance}."
            )

    methods = [p.get("method") or PaymentMethod.CASH for p in payments if Decimal(p.get("amount") or 0) > ZERO]
    primary_method = methods[0] if methods else PaymentMethod.CASH

    sale = Sale.objects.create(
        business=business,
        branch=branch,
        number=allocate_number(business, "POS", "POS"),
        client_uuid=client_uuid,
        customer=customer,
        status=SaleStatus.COMPLETED,
        subtotal=subtotal,
        discount_total=discount_total,
        total=total,
        paid_amount=paid,
        due_amount=due,
        coupon=coupon,
        coupon_code=coupon.code if coupon else "",
        manual_discount_kind=manual_kind,
        manual_discount_value=manual_value,
        loyalty_earned=ZERO,
        loyalty_redeemed=used_points,
        payment_method=primary_method,
        notes=payload.get("notes") or "",
        sold_at=when,
        created_by=user,
    )

    for row in priced:
        SaleLine.objects.create(
            business=business,
            sale=sale,
            variant=row["variant"],
            quantity=row["quantity"],
            free_qty=row["free_qty"],
            unit_price=row["unit_price"],
            promo_price=row["promo_price"],
            line_total=row["line_total"],
            promo_name=row["promo_name"],
        )
        if row["variant"].product.track_stock:
            record_sale(
                variant=row["variant"],
                branch=branch,
                quantity=row["quantity"],
                user=user,
                reference_id=sale.id,
                reason=f"POS {sale.number}",
            )

    cash_paid = ZERO
    for pay in payments:
        amount = money(pay.get("amount") or 0)
        if amount <= ZERO:
            continue
        method = pay.get("method") or PaymentMethod.CASH
        SalePayment.objects.create(business=business, sale=sale, method=method, amount=amount)
        if method == PaymentMethod.CASH:
            cash_paid += amount

    if cash_paid > ZERO:
        session = require_open_session(branch)
        apply_cash(
            session=session,
            kind=CashKind.SALE,
            amount=cash_paid,
            user=user,
            reason=f"POS {sale.number}",
            reference_type="pos_sale",
            reference_id=sale.id,
        )

    earned = earn_points(business, total) if customer else ZERO
    sale.loyalty_earned = earned
    sale.save(update_fields=["loyalty_earned"])

    if coupon:
        coupon.used_count += 1
        coupon.save(update_fields=["used_count", "updated_at"])

    if customer:
        customer.total_purchases += total
        customer.loyalty_points += earned
        customer.loyalty_points -= used_points
        if customer.loyalty_points < ZERO:
            customer.loyalty_points = ZERO
        auto = tier_for(customer)
        if auto and not customer.membership_tier_id:
            customer.membership_tier = auto
        customer.save(
            update_fields=["total_purchases", "loyalty_points", "membership_tier", "updated_at"]
        )
        if due > ZERO:
            apply_customer_ledger(
                customer=customer,
                entry_type=CustomerLedgerType.SALE,
                amount=due,
                user=user,
                reason=f"POS credit {sale.number}",
                reference_type="pos_sale",
                reference_id=sale.id,
            )
        CustomerSale.objects.create(
            business=business,
            number=sale.number,
            customer=customer,
            branch=branch,
            total=total,
            paid_amount=paid,
            due_amount=due,
            payment_method=primary_method,
            loyalty_points=earned,
            notes=f"POS {sale.number}",
            created_by=user,
            pos_sale=sale,
        )
    return sale

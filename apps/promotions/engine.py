from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.promotions.models import Promotion, PromotionKind

ZERO = Decimal("0")
TWOPLACES = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def active_promotions(business, when=None):
    when = when or timezone.now()
    qs = Promotion.objects.filter(business=business, is_active=True)
    return [
        p
        for p in qs.select_related("product", "category", "variant")
        if (not p.starts_at or p.starts_at <= when) and (not p.ends_at or p.ends_at >= when)
    ]


def _matches(promo: Promotion, variant) -> bool:
    if promo.variant_id:
        return promo.variant_id == variant.id
    if promo.product_id:
        return promo.product_id == variant.product_id
    if promo.category_id:
        return variant.product.category_id == promo.category_id
    return True


def _unit_after_promo(list_price: Decimal, promo: Promotion) -> Decimal:
    if promo.kind == PromotionKind.PRICE:
        return max(ZERO, money(promo.value))
    if promo.kind == PromotionKind.PERCENT:
        return money(list_price * (Decimal("1") - Decimal(promo.value) / Decimal("100")))
    if promo.kind == PromotionKind.FIXED:
        return max(ZERO, money(list_price - Decimal(promo.value)))
    return list_price


def price_lines(business, items, when=None):
    """
    Price each cart line, applying active promotions.
    items: iterable of {variant, quantity}
    """
    promos = active_promotions(business, when)  # load active promotions
    priced = []
    for item in items:
        variant = item["variant"]
        qty = Decimal(item["quantity"])
        if qty <= ZERO:
            raise ValidationError("Line quantity must be greater than zero.")
        list_price = money(variant.selling_price)
        unit = list_price
        applied = ""
        free_qty = ZERO
        for promo in promos:
            if not _matches(promo, variant):
                continue
            if promo.kind == PromotionKind.BOGO:
                cycle = Decimal(promo.buy_qty) + Decimal(promo.get_qty)
                if cycle > ZERO:
                    free_qty = max(free_qty, (qty // cycle) * Decimal(promo.get_qty))
                    applied = promo.name
                continue
            next_unit = _unit_after_promo(list_price, promo)
            if next_unit < unit:
                unit = next_unit
                applied = promo.name
        paid_qty = qty - free_qty
        line_total = money(paid_qty * unit)
        priced.append(
            {
                "variant": variant,
                "quantity": qty,
                "free_qty": free_qty,
                "unit_price": list_price,
                "promo_price": unit,
                "line_total": line_total,
                "promo_name": applied,
            }
        )
    return priced

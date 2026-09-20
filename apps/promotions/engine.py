from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.promotions.models import Coupon, CouponKind, LoyaltySettings, MembershipTier, Promotion, PromotionKind

ZERO = Decimal("0")
TWOPLACES = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def loyalty_settings(business) -> LoyaltySettings:
    settings, _ = LoyaltySettings.objects.get_or_create(business=business)
    return settings


def tier_for(customer):
    if not customer:
        return None
    if customer.membership_tier_id and customer.membership_tier.is_active:
        return customer.membership_tier
    return (
        MembershipTier.objects.filter(
            business=customer.business,
            is_active=True,
            min_points__lte=customer.loyalty_points,
        )
        .order_by("-min_points")
        .first()
    )


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
    items: iterable of {variant, quantity}
    """
    promos = []
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


def find_coupon(business, code, when=None):
    if not code:
        return None
    when = when or timezone.now()
    coupon = Coupon.objects.filter(business=business, code__iexact=code.strip()).first()
    if not coupon or not coupon.is_active:
        raise ValidationError({"coupon_code": "Coupon is not valid."})
    if coupon.starts_at and coupon.starts_at > when:
        raise ValidationError({"coupon_code": "Coupon is not active yet."})
    if coupon.ends_at and coupon.ends_at < when:
        raise ValidationError({"coupon_code": "Coupon has expired."})
    if coupon.usage_limit and coupon.used_count >= coupon.usage_limit:
        raise ValidationError({"coupon_code": "Coupon usage limit reached."})
    return coupon


def coupon_discount(subtotal: Decimal, coupon: Coupon | None) -> Decimal:
    if not coupon:
        return ZERO
    if subtotal < Decimal(coupon.min_spend):
        raise ValidationError({"coupon_code": f"Minimum spend for this coupon is Rs {coupon.min_spend}."})
    if coupon.kind == CouponKind.PERCENT:
        amount = money(subtotal * Decimal(coupon.value) / Decimal("100"))
    else:
        amount = money(coupon.value)
    if coupon.max_discount and coupon.max_discount > ZERO:
        amount = min(amount, money(coupon.max_discount))
    return min(amount, subtotal)


def membership_discount(subtotal: Decimal, customer) -> Decimal:
    tier = tier_for(customer)
    if not tier or Decimal(tier.discount_percent) <= ZERO:
        return ZERO
    return money(subtotal * Decimal(tier.discount_percent) / Decimal("100"))


def redeem_value(business, points, remaining: Decimal) -> tuple[Decimal, Decimal]:
    settings = loyalty_settings(business)
    pts = Decimal(points or 0)
    if pts <= ZERO:
        return ZERO, ZERO
    if not settings.is_active:
        raise ValidationError({"redeem_points": "Loyalty redemption is turned off."})
    if pts < Decimal(settings.min_redeem_points):
        raise ValidationError({"redeem_points": f"Redeem at least {settings.min_redeem_points} points."})
    value = money(pts * Decimal(settings.redemption_rate))
    value = min(value, remaining)
    used_points = ZERO if Decimal(settings.redemption_rate) == ZERO else money(value / Decimal(settings.redemption_rate))
    return value, used_points


def earn_points(business, amount: Decimal) -> Decimal:
    settings = loyalty_settings(business)
    if not settings.is_active or Decimal(settings.points_per_amount) <= ZERO or amount <= ZERO:
        return ZERO
    return (amount / Decimal(settings.points_per_amount)).to_integral_value()

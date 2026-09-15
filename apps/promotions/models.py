from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel


class LoyaltySettings(TimeStampedModel):
    business = models.OneToOneField(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="loyalty_settings",
    )
    points_per_amount = models.DecimalField(max_digits=14, decimal_places=2, default=100)
    redemption_rate = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=1,
        help_text="Rupees one loyalty point is worth when redeemed.",
    )
    min_redeem_points = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    def __str__(self):
        return f"Loyalty · {self.business.name}"


class MembershipTier(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="membership_tiers",
    )
    name = models.CharField(max_length=80)
    min_points = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "name")
        ordering = ["min_points", "name"]

    def __str__(self):
        return self.name


class CouponKind(models.TextChoices):
    PERCENT = "percent", "Percentage"
    FIXED = "fixed", "Fixed amount"


class Coupon(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="coupons",
    )
    code = models.CharField(max_length=40)
    kind = models.CharField(max_length=12, choices=CouponKind.choices, default=CouponKind.PERCENT)
    value = models.DecimalField(max_digits=14, decimal_places=2)
    min_spend = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    max_discount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(default=0)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "code")
        ordering = ["code"]

    def __str__(self):
        return self.code


class PromotionKind(models.TextChoices):
    PERCENT = "percent", "Percentage off"
    FIXED = "fixed", "Fixed off"
    BOGO = "bogo", "Buy X get Y"
    PRICE = "price", "Promotional price"


class Promotion(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="promotions",
    )
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=PromotionKind.choices)
    value = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    buy_qty = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    get_qty = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="promotions",
    )
    category = models.ForeignKey(
        "catalog.Category",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="promotions",
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="promotions",
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

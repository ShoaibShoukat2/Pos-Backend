from django.contrib import admin

from apps.promotions.models import Coupon, LoyaltySettings, MembershipTier, Promotion


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "kind", "value", "is_active", "used_count")


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "value", "is_active")


@admin.register(MembershipTier)
class MembershipTierAdmin(admin.ModelAdmin):
    list_display = ("name", "min_points", "discount_percent")


@admin.register(LoyaltySettings)
class LoyaltySettingsAdmin(admin.ModelAdmin):
    list_display = ("business", "points_per_amount", "is_active")

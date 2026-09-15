from rest_framework import serializers

from apps.promotions.models import Coupon, LoyaltySettings, MembershipTier, Promotion


class LoyaltySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltySettings
        fields = (
            "id",
            "points_per_amount",
            "redemption_rate",
            "min_redeem_points",
            "is_active",
        )
        read_only_fields = ("id",)


class MembershipTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipTier
        fields = ("id", "name", "min_points", "discount_percent", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = (
            "id",
            "code",
            "kind",
            "value",
            "min_spend",
            "max_discount",
            "starts_at",
            "ends_at",
            "usage_limit",
            "used_count",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "used_count", "created_at")

    def validate_code(self, value):
        return value.strip().upper()


class PromotionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)

    class Meta:
        model = Promotion
        fields = (
            "id",
            "name",
            "kind",
            "value",
            "buy_qty",
            "get_qty",
            "product",
            "product_name",
            "category",
            "category_name",
            "variant",
            "variant_name",
            "starts_at",
            "ends_at",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

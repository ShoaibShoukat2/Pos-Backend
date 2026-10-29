from rest_framework import serializers

from apps.promotions.models import Promotion


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

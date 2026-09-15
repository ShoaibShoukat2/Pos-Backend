from decimal import Decimal

from rest_framework import serializers

from apps.businesses.models import Branch
from apps.catalog.models import ProductVariant
from apps.inventory.models import StockLevel, StockMovement, StockOperation, StockOperationLine, StockTransfer, StockTransferLine


class StockLevelSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    barcode = serializers.CharField(source="variant.barcode", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    min_stock = serializers.DecimalField(source="variant.min_stock", max_digits=14, decimal_places=3, read_only=True)
    cost_price = serializers.DecimalField(source="variant.cost_price", max_digits=14, decimal_places=2, read_only=True)
    stock_value = serializers.SerializerMethodField()
    is_low = serializers.SerializerMethodField()

    class Meta:
        model = StockLevel
        fields = (
            "id",
            "variant",
            "product_name",
            "variant_name",
            "sku",
            "barcode",
            "branch",
            "branch_name",
            "quantity",
            "min_stock",
            "cost_price",
            "stock_value",
            "is_low",
            "updated_at",
        )

    def get_stock_value(self, obj):
        return obj.quantity * obj.variant.cost_price

    def get_is_low(self, obj):
        return obj.quantity < obj.variant.min_stock


class StockMovementSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    created_by_name = serializers.CharField(source="created_by.full_name", read_only=True)

    class Meta:
        model = StockMovement
        fields = (
            "id",
            "variant",
            "product_name",
            "variant_name",
            "sku",
            "branch",
            "branch_name",
            "movement_type",
            "quantity",
            "balance_after",
            "reason",
            "reference_type",
            "reference_id",
            "created_by_name",
            "created_at",
        )


class OperationLineSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)

    class Meta:
        model = StockOperationLine
        fields = ("id", "variant", "variant_name", "sku", "quantity", "counted_quantity")
        read_only_fields = ("id",)


class StockOperationSerializer(serializers.ModelSerializer):
    lines = OperationLineSerializer(many=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = StockOperation
        fields = (
            "id",
            "number",
            "kind",
            "branch",
            "branch_name",
            "status",
            "reason",
            "lines",
            "posted_at",
            "created_at",
        )
        read_only_fields = ("id", "number", "status", "posted_at", "created_at")

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("Add at least one line.")
        return lines

    def create(self, validated):
        from apps.inventory.services import create_and_post_operation

        validated.pop("business", None)
        return create_and_post_operation(
            business=self.context["request"].user.business,
            user=self.context["request"].user,
            **validated,
        )


class TransferLineSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)

    class Meta:
        model = StockTransferLine
        fields = ("id", "variant", "variant_name", "sku", "quantity")
        read_only_fields = ("id",)


class StockTransferSerializer(serializers.ModelSerializer):
    lines = TransferLineSerializer(many=True)
    from_branch_name = serializers.CharField(source="from_branch.name", read_only=True)
    to_branch_name = serializers.CharField(source="to_branch.name", read_only=True)

    class Meta:
        model = StockTransfer
        fields = (
            "id",
            "number",
            "from_branch",
            "to_branch",
            "from_branch_name",
            "to_branch_name",
            "status",
            "reason",
            "lines",
            "posted_at",
            "created_at",
        )
        read_only_fields = ("id", "number", "status", "posted_at", "created_at")

    def validate(self, attrs):
        if attrs["from_branch"] == attrs["to_branch"]:
            raise serializers.ValidationError("Source and destination branches must be different.")
        return attrs

    def create(self, validated):
        from apps.inventory.services import create_and_post_transfer

        validated.pop("business", None)
        return create_and_post_transfer(
            business=self.context["request"].user.business,
            user=self.context["request"].user,
            **validated,
        )


class VariantField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return ProductVariant.objects.filter(business=self.context["request"].user.business)


class BranchField(serializers.PrimaryKeyRelatedField):
    def get_queryset(self):
        return Branch.objects.filter(business=self.context["request"].user.business)

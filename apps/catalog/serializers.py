from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.catalog.models import Brand, Category, Product, ProductVariant, Unit
from apps.inventory.engine import apply_movement
from apps.inventory.models import MovementType, StockLevel


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "kind", "is_active", "product_count", "created_at")
        read_only_fields = ("id", "created_at")


class BrandSerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Brand
        fields = ("id", "name", "is_active", "product_count", "created_at")
        read_only_fields = ("id", "created_at")


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ("id", "name", "short_code", "is_active")
        read_only_fields = ("id",)


class VariantStockSerializer(serializers.ModelSerializer):
    branch_id = serializers.UUIDField(source="branch.id", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    is_low = serializers.SerializerMethodField()

    class Meta:
        model = StockLevel
        fields = ("branch_id", "branch_name", "quantity", "is_low")

    def get_is_low(self, obj):
        return obj.quantity < obj.variant.min_stock


class ProductVariantSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    total_stock = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, allow_null=True)
    stock_by_branch = VariantStockSerializer(source="stock_levels", many=True, read_only=True)
    opening_stock = serializers.ListField(child=serializers.DictField(), write_only=True, required=False)

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "product",
            "product_name",
            "name",
            "display_name",
            "sku",
            "barcode",
            "attributes",
            "cost_price",
            "selling_price",
            "min_stock",
            "is_default",
            "is_active",
            "total_stock",
            "stock_by_branch",
            "opening_stock",
        )
        read_only_fields = ("id",)
        extra_kwargs = {"product": {"required": False}}

    def validate_sku(self, value):
        business = self.context["request"].user.business
        qs = ProductVariant.objects.filter(business=business, sku__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A variant with this SKU already exists.")
        return value

    def create(self, validated):
        request = self.context["request"]
        opening = validated.pop("opening_stock", [])
        validated.pop("business", None)
        variant = ProductVariant.objects.create(business=request.user.business, **validated)
        _apply_opening(variant, opening, request.user)
        return variant

    def update(self, instance, validated):
        validated.pop("opening_stock", None)
        return super().update(instance, validated)


class VariantListSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    total_stock = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, allow_null=True)

    class Meta:
        model = ProductVariant
        fields = (
            "id",
            "product",
            "product_name",
            "name",
            "display_name",
            "sku",
            "barcode",
            "cost_price",
            "selling_price",
            "min_stock",
            "is_default",
            "is_active",
            "total_stock",
        )
        read_only_fields = ("id",)


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    unit_code = serializers.CharField(source="unit.short_code", read_only=True)
    variant_count = serializers.IntegerField(read_only=True, allow_null=True)
    total_stock = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "unit",
            "unit_code",
            "tax_rate",
            "sku",
            "barcode",
            "cost_price",
            "selling_price",
            "min_stock",
            "has_variants",
            "track_stock",
            "item_kind",
            "duration_minutes",
            "warranty_days",
            "is_active",
            "variant_count",
            "total_stock",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    unit_code = serializers.CharField(source="unit.short_code", read_only=True)
    variant_count = serializers.IntegerField(read_only=True, allow_null=True)
    total_stock = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True, allow_null=True)
    variants = ProductVariantSerializer(many=True, required=False)
    opening_stock = serializers.ListField(child=serializers.DictField(), write_only=True, required=False)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "description",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "unit",
            "unit_code",
            "tax_rate",
            "sku",
            "barcode",
            "cost_price",
            "selling_price",
            "min_stock",
            "has_variants",
            "track_stock",
            "item_kind",
            "duration_minutes",
            "warranty_days",
            "is_active",
            "variant_count",
            "total_stock",
            "variants",
            "opening_stock",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

        extra_kwargs = {
            "sku": {"required": False, "allow_blank": True},
        }

    def validate_sku(self, value):
        if not value:
            return value
        business = self.context["request"].user.business
        qs = Product.objects.filter(business=business, sku__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A product or service with this SKU already exists.")
        return value

    def validate(self, attrs):
        kind = attrs.get("item_kind")
        if kind is None and self.instance:
            kind = self.instance.item_kind
        if kind is None:
            kind = Product.ItemKind.PRODUCT
        if kind == Product.ItemKind.SERVICE:
            attrs["item_kind"] = Product.ItemKind.SERVICE
            attrs["track_stock"] = False
            attrs["has_variants"] = False
            attrs["min_stock"] = 0
        sku = (attrs.get("sku") if "sku" in attrs else (self.instance.sku if self.instance else "")) or ""
        sku = sku.strip()
        if not sku:
            if kind == Product.ItemKind.SERVICE:
                attrs["sku"] = _next_service_sku(self.context["request"].user.business)
            else:
                raise serializers.ValidationError({"sku": "SKU is required."})
        return attrs

    @transaction.atomic
    def create(self, validated):
        request = self.context["request"]
        variants_data = validated.pop("variants", [])
        opening = validated.pop("opening_stock", [])
        validated.pop("business", None)
        product = Product.objects.create(business=request.user.business, **validated)
        if product.has_variants:
            if not variants_data:
                raise serializers.ValidationError(
                    {"variants": "Add at least one variant (for example Small / Black)."}
                )
            for row in variants_data:
                row.pop("product", None)
                row_opening = row.pop("opening_stock", [])
                variant = ProductVariant.objects.create(
                    business=product.business,
                    product=product,
                    cost_price=row.get("cost_price", product.cost_price),
                    selling_price=row.get("selling_price", product.selling_price),
                    min_stock=row.get("min_stock", product.min_stock),
                    **{k: v for k, v in row.items() if k not in ("cost_price", "selling_price", "min_stock")},
                )
                _apply_opening(variant, row_opening, request.user)
        else:
            variant = ProductVariant.objects.create(
                business=product.business,
                product=product,
                name=product.name,
                sku=product.sku,
                barcode=product.barcode,
                cost_price=product.cost_price,
                selling_price=product.selling_price,
                min_stock=product.min_stock,
                is_default=True,
            )
            _apply_opening(variant, opening, request.user)
        return product

    def update(self, instance, validated):
        validated.pop("variants", None)
        validated.pop("opening_stock", None)
        product = super().update(instance, validated)
        if not product.has_variants:
            default = product.variants.filter(is_default=True).first() or product.variants.first()
            if default:
                default.name = product.name
                default.sku = product.sku
                default.barcode = product.barcode
                default.cost_price = product.cost_price
                default.selling_price = product.selling_price
                default.min_stock = product.min_stock
                default.is_active = product.is_active
                default.save()
        return product


def _next_service_sku(business):
    n = Product.objects.filter(business=business, item_kind=Product.ItemKind.SERVICE).count() + 1
    while True:
        sku = f"SVC-{n:03d}"
        taken = Product.objects.filter(business=business, sku__iexact=sku).exists()
        if not taken:
            taken = ProductVariant.objects.filter(business=business, sku__iexact=sku).exists()
        if not taken:
            return sku
        n += 1


def _apply_opening(variant, rows, user):
    from apps.businesses.models import Branch

    if not variant.product.track_stock:
        return
    for row in rows or []:
        qty = Decimal(str(row.get("quantity") or 0))
        if qty <= 0:
            continue
        branch = Branch.objects.filter(business=variant.business, pk=row.get("branch")).first()
        if not branch:
            raise serializers.ValidationError({"opening_stock": "Unknown branch for opening stock."})
        apply_movement(
            variant=variant,
            branch=branch,
            movement_type=MovementType.STOCK_IN,
            quantity=qty,
            user=user,
            reason="Opening stock",
            reference_type="opening_stock",
            reference_id=variant.id,
            idempotency_key=f"opening:{variant.id}:{branch.id}",
        )

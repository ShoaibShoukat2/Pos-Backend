from rest_framework import serializers

from apps.pos.checkout import checkout_sale
from apps.pos.models import Sale, SaleLine, SalePayment


class SaleLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)

    class Meta:
        model = SaleLine
        fields = (
            "id",
            "variant",
            "product_name",
            "variant_name",
            "sku",
            "quantity",
            "free_qty",
            "unit_price",
            "promo_price",
            "line_total",
            "promo_name",
        )


class SalePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalePayment
        fields = ("id", "method", "amount")


class SaleSerializer(serializers.ModelSerializer):
    lines = SaleLineSerializer(many=True, read_only=True)
    payments = SalePaymentSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    cashier_name = serializers.CharField(source="created_by.full_name", read_only=True)

    class Meta:
        model = Sale
        fields = (
            "id",
            "number",
            "client_uuid",
            "branch",
            "branch_name",
            "customer",
            "customer_name",
            "status",
            "subtotal",
            "discount_total",
            "total",
            "paid_amount",
            "due_amount",
            "coupon_code",
            "manual_discount_kind",
            "manual_discount_value",
            "loyalty_earned",
            "loyalty_redeemed",
            "payment_method",
            "notes",
            "sold_at",
            "cashier_name",
            "lines",
            "payments",
            "created_at",
        )
        read_only_fields = fields


class CheckoutLineSerializer(serializers.Serializer):
    variant = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)


class CheckoutPaymentSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=["cash", "card", "bank", "wallet"])
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class CheckoutSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField()
    branch = serializers.UUIDField()
    customer = serializers.UUIDField(required=False, allow_null=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True)
    manual_discount_kind = serializers.CharField(required=False, allow_blank=True)
    manual_discount_value = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    redeem_points = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    sold_at = serializers.CharField(required=False, allow_blank=True)
    lines = CheckoutLineSerializer(many=True)
    payments = CheckoutPaymentSerializer(many=True, required=False)

    def create(self, validated):
        request = self.context["request"]
        return checkout_sale(business=request.user.business, user=request.user, payload=validated)


class SyncSerializer(serializers.Serializer):
    sales = CheckoutSerializer(many=True)

    def create(self, validated):
        request = self.context["request"]
        results = []
        for row in validated["sales"]:
            try:
                sale = checkout_sale(business=request.user.business, user=request.user, payload=row)
                results.append(
                    {
                        "client_uuid": str(row["client_uuid"]),
                        "ok": True,
                        "number": sale.number,
                        "id": str(sale.id),
                    }
                )
            except Exception as exc:
                detail = getattr(exc, "detail", None)
                results.append(
                    {
                        "client_uuid": str(row["client_uuid"]),
                        "ok": False,
                        "error": str(detail or exc),
                    }
                )
        return results

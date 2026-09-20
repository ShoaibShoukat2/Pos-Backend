from rest_framework import serializers

from apps.pos.checkout import checkout_sale
from apps.pos.models import Sale, SaleLine, SalePayment, SaleReturn, SaleReturnLine
from apps.pos.returns import process_sale_return


class SaleLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    returnable_qty = serializers.SerializerMethodField()

    class Meta:
        model = SaleLine
        fields = (
            "id",
            "variant",
            "product_name",
            "variant_name",
            "sku",
            "quantity",
            "returned_qty",
            "returned_amount",
            "returnable_qty",
            "free_qty",
            "unit_price",
            "promo_price",
            "line_total",
            "promo_name",
        )

    def get_returnable_qty(self, obj):
        remaining = obj.quantity - obj.returned_qty
        if remaining < 0:
            remaining = 0
        return f"{remaining:.3f}"


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
            "returned_total",
            "refunded_amount",
            "net_total",
            "loyalty_returned",
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
    branch = serializers.UUIDField(required=False)
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


class SaleReturnLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)

    class Meta:
        model = SaleReturnLine
        fields = ("id", "sale_line", "variant", "product_name", "variant_name", "sku", "quantity", "amount")


class SaleReturnSerializer(serializers.ModelSerializer):
    lines = SaleReturnLineSerializer(many=True, read_only=True)
    sale_number = serializers.CharField(source="sale.number", read_only=True)
    sale_detail = SaleSerializer(source="sale", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    cashier_name = serializers.CharField(source="created_by.full_name", read_only=True, default="")
    customer_name = serializers.SerializerMethodField()

    class Meta:
        model = SaleReturn
        fields = (
            "id",
            "number",
            "sale",
            "sale_number",
            "sale_detail",
            "branch",
            "branch_name",
            "customer_name",
            "refund_amount",
            "credit_reduced",
            "cash_refunded",
            "refund_method",
            "reason",
            "cashier_name",
            "lines",
            "created_at",
        )
        read_only_fields = fields

    def get_customer_name(self, obj):
        if obj.sale_id and obj.sale.customer_id:
            return obj.sale.customer.name
        return ""


class ReturnLineInSerializer(serializers.Serializer):
    sale_line = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)


class ReturnSerializer(serializers.Serializer):
    sale = serializers.UUIDField()
    refund_method = serializers.ChoiceField(choices=["cash", "card", "bank", "wallet"], required=False)
    reason = serializers.CharField(required=False, allow_blank=True)
    lines = ReturnLineInSerializer(many=True)

    def create(self, validated):
        request = self.context["request"]
        return process_sale_return(business=request.user.business, user=request.user, payload=validated)


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

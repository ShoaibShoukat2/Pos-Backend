from decimal import Decimal

from rest_framework import serializers

from apps.promotions.engine import money
from apps.purchases.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierLedgerEntry,
    SupplierPayable,
    SupplierPayment,
)
from apps.purchases.services import create_purchase_order, pay_supplier, receive_goods


class SupplierSerializer(serializers.ModelSerializer):
    payable_balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    order_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Supplier
        fields = (
            "id",
            "name",
            "phone",
            "email",
            "address",
            "city",
            "tax_number",
            "notes",
            "is_active",
            "payable_balance",
            "order_count",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    product_name = serializers.CharField(source="variant.product.name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)
    outstanding_qty = serializers.DecimalField(max_digits=14, decimal_places=3, read_only=True)
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = (
            "id",
            "variant",
            "product_name",
            "variant_name",
            "sku",
            "quantity",
            "received_qty",
            "outstanding_qty",
            "unit_cost",
            "line_total",
        )
        read_only_fields = ("id", "received_qty")


class PurchaseOrderSerializer(serializers.ModelSerializer):
    lines = PurchaseOrderLineSerializer(many=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = (
            "id",
            "number",
            "supplier",
            "supplier_name",
            "branch",
            "branch_name",
            "status",
            "notes",
            "expected_date",
            "lines",
            "total",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "number", "status", "created_at", "updated_at")

    def get_total(self, obj):
        annotated = getattr(obj, "annotated_total", None)
        if annotated is not None:
            return annotated
        return sum((money(line.quantity * line.unit_cost) for line in obj.lines.all()), start=Decimal("0"))

    def create(self, validated):
        request = self.context["request"]
        validated.pop("business", None)
        return create_purchase_order(
            business=request.user.business,
            user=request.user,
            **validated,
        )


class ReceiveLineSerializer(serializers.Serializer):
    variant = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3)
    unit_cost = serializers.DecimalField(max_digits=14, decimal_places=2)
    purchase_order_line = serializers.UUIDField(required=False)


class ReceiveGoodsSerializer(serializers.Serializer):
    supplier = serializers.UUIDField(required=False)
    branch = serializers.UUIDField(required=False)
    purchase_order = serializers.UUIDField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    lines = ReceiveLineSerializer(many=True)

    def create(self, validated):
        from apps.businesses.models import Branch
        from apps.catalog.models import ProductVariant
        from apps.purchases.models import PurchaseOrderLine

        request = self.context["request"]
        business = request.user.business
        po = None
        if validated.get("purchase_order"):
            po = PurchaseOrder.objects.filter(business=business, pk=validated["purchase_order"]).first()
            if not po:
                raise serializers.ValidationError({"purchase_order": "Purchase order not found."})
        supplier_id = validated.get("supplier") or (po.supplier_id if po else None)
        branch_id = validated.get("branch") or (po.branch_id if po else None)
        supplier = Supplier.objects.filter(business=business, pk=supplier_id).first()
        branch = Branch.objects.filter(business=business, pk=branch_id).first()
        if not supplier or not branch:
            raise serializers.ValidationError("Supplier and receiving branch are required.")

        resolved = []
        for row in validated["lines"]:
            variant = ProductVariant.objects.filter(business=business, pk=row["variant"]).first()
            if not variant:
                raise serializers.ValidationError({"lines": "Unknown variant."})
            po_line = None
            if row.get("purchase_order_line"):
                po_line = PurchaseOrderLine.objects.filter(
                    order__business=business, pk=row["purchase_order_line"]
                ).first()
            resolved.append(
                {
                    "variant": variant,
                    "quantity": row["quantity"],
                    "unit_cost": row["unit_cost"],
                    "purchase_order_line": po_line,
                }
            )
        return receive_goods(
            business=business,
            user=request.user,
            supplier=supplier,
            branch=branch,
            purchase_order=po,
            notes=validated.get("notes", ""),
            lines=resolved,
        )


class GoodsReceiptLineSerializer(serializers.ModelSerializer):
    variant_name = serializers.CharField(source="variant.display_name", read_only=True)
    sku = serializers.CharField(source="variant.sku", read_only=True)

    class Meta:
        model = GoodsReceiptLine
        fields = ("id", "variant", "variant_name", "sku", "quantity", "unit_cost")


class GoodsReceiptSerializer(serializers.ModelSerializer):
    lines = GoodsReceiptLineSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    purchase_order_number = serializers.CharField(source="purchase_order.number", read_only=True)
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = (
            "id",
            "number",
            "supplier",
            "supplier_name",
            "branch",
            "branch_name",
            "purchase_order",
            "purchase_order_number",
            "status",
            "notes",
            "lines",
            "total_amount",
            "posted_at",
            "created_at",
        )

    def get_total_amount(self, obj):
        return sum((money(line.quantity * line.unit_cost) for line in obj.lines.all()), start=Decimal("0"))


class SupplierPayableSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    receipt_number = serializers.CharField(source="goods_receipt.number", read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = SupplierPayable
        fields = (
            "id",
            "supplier",
            "supplier_name",
            "goods_receipt",
            "receipt_number",
            "amount",
            "paid_amount",
            "balance",
            "status",
            "created_at",
        )


class SupplierLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupplierLedgerEntry
        fields = ("id", "entry_type", "amount", "balance_after", "reason", "created_at")


class SupplierPaymentSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = SupplierPayment
        fields = (
            "id",
            "number",
            "supplier",
            "supplier_name",
            "branch",
            "branch_name",
            "amount",
            "method",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "number", "created_at")

    def create(self, validated):
        request = self.context["request"]
        validated.pop("business", None)
        return pay_supplier(business=request.user.business, user=request.user, **validated)

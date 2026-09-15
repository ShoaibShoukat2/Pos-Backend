from rest_framework import serializers

from apps.customers.models import Customer, CustomerLedgerEntry, CustomerPayment, CustomerSale
from apps.customers.services import post_customer_payment, post_customer_sale


class CustomerSerializer(serializers.ModelSerializer):
    membership_name = serializers.SerializerMethodField()
    membership_discount = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = (
            "id",
            "name",
            "phone",
            "email",
            "address",
            "city",
            "notes",
            "credit_limit",
            "receivable_balance",
            "total_purchases",
            "loyalty_points",
            "membership_tier",
            "membership_name",
            "membership_discount",
            "is_active",
            "created_at",
        )
        read_only_fields = (
            "id",
            "receivable_balance",
            "total_purchases",
            "loyalty_points",
            "membership_name",
            "membership_discount",
            "created_at",
        )

    def get_membership_name(self, obj):
        from apps.promotions.engine import tier_for

        tier = tier_for(obj)
        return tier.name if tier else ""

    def get_membership_discount(self, obj):
        from apps.promotions.engine import tier_for

        tier = tier_for(obj)
        return f"{tier.discount_percent:.2f}" if tier else "0.00"


class CustomerLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerLedgerEntry
        fields = (
            "id",
            "entry_type",
            "amount",
            "balance_after",
            "reason",
            "created_at",
        )


class CustomerSaleSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = CustomerSale
        fields = (
            "id",
            "number",
            "customer",
            "customer_name",
            "branch",
            "branch_name",
            "total",
            "paid_amount",
            "due_amount",
            "payment_method",
            "loyalty_points",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "number", "due_amount", "loyalty_points", "created_at")

    def create(self, validated):
        request = self.context["request"]
        validated.pop("business", None)
        return post_customer_sale(business=request.user.business, user=request.user, **validated)


class CustomerPaymentSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)

    class Meta:
        model = CustomerPayment
        fields = (
            "id",
            "number",
            "customer",
            "customer_name",
            "branch",
            "amount",
            "method",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "number", "created_at")

    def create(self, validated):
        request = self.context["request"]
        validated.pop("business", None)
        return post_customer_payment(business=request.user.business, user=request.user, **validated)

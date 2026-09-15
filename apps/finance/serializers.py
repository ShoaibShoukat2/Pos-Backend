from rest_framework import serializers

from apps.finance.cash import close_shift, open_shift
from apps.finance.models import CashMovement, CashSession, Expense, ExpenseCategory
from apps.finance.services import post_expense


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ("id", "name", "is_system", "is_active")
        read_only_fields = ("id", "is_system")


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = Expense
        fields = (
            "id",
            "number",
            "category",
            "category_name",
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
        return post_expense(business=request.user.business, user=request.user, **validated)


class CashMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashMovement
        fields = ("id", "kind", "amount", "balance_after", "reason", "created_at")







class CashSessionSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    opened_by_name = serializers.CharField(source="opened_by.full_name", read_only=True)
    movements = CashMovementSerializer(many=True, read_only=True)

    class Meta:
        model = CashSession
        fields = (
            "id",
            "number",
            "branch",
            "branch_name",
            "opened_by_name",
            "status",
            "opening_cash",
            "sales_cash",
            "customer_received",
            "expense_total",
            "refund_total",
            "supplier_paid",
            "expected_cash",
            "actual_cash",
            "difference",
            "notes",
            "movements",
            "created_at",
            "closed_at",
        )
        read_only_fields = (
            "id",
            "number",
            "status",
            "sales_cash",
            "customer_received",
            "expense_total",
            "refund_total",
            "supplier_paid",
            "expected_cash",
            "actual_cash",
            "difference",
            "created_at",
            "closed_at",
        )


class OpenShiftSerializer(serializers.Serializer):
    branch = serializers.UUIDField()
    opening_cash = serializers.DecimalField(max_digits=14, decimal_places=2)

    def create(self, validated):
        from apps.businesses.models import Branch

        request = self.context["request"]
        branch = Branch.objects.filter(business=request.user.business, pk=validated["branch"]).first()
        if not branch:
            raise serializers.ValidationError({"branch": "Unknown branch."})
        return open_shift(
            business=request.user.business,
            branch=branch,
            user=request.user,
            opening_cash=validated["opening_cash"],
        )


class CloseShiftSerializer(serializers.Serializer):
    actual_cash = serializers.DecimalField(max_digits=14, decimal_places=2)
    notes = serializers.CharField(required=False, allow_blank=True)

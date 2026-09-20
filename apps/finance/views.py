from django.db.models import DecimalField, ExpressionWrapper, F, Sum
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasAnyPermission, HasPermission
from apps.customers.models import Customer
from apps.finance.cash import apply_cash, close_shift
from apps.finance.models import CashKind, CashSession, Expense, ExpenseCategory
from apps.finance.serializers import (
    CashSessionSerializer,
    CloseShiftSerializer,
    ExpenseCategorySerializer,
    ExpenseSerializer,
    OpenShiftSerializer,
)
from apps.purchases.models import SupplierPayable


class ExpenseCategoryViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = ExpenseCategory.objects.all()
    pagination_class = None

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "expense.view"
        return "expense.manage"


class ExpenseViewSet(
    BusinessQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Expense.objects.all()
    filterset_fields = ("category", "branch", "method")
    search_fields = ("number", "notes", "category__name")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "expense.view"
        return "expense.manage"

    def get_queryset(self):
        return super().get_queryset().select_related("category", "branch")


class CashSessionViewSet(BusinessQuerysetMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = CashSessionSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = CashSession.objects.all()
    filterset_fields = ("branch", "status")

    @property
    def required_permission(self):
        if self.action == "open":
            return "cash.drawer"
        if self.action == "close":
            return "cash.reconcile"
        return "cash.drawer"

    def get_queryset(self):
        qs = super().get_queryset().select_related("branch", "opened_by")
        if self.action == "list":
            return qs
        return qs.prefetch_related("movements")

    @action(detail=False, methods=["get"])
    def current(self, request):
        branch_id = request.query_params.get("branch")
        qs = self.get_queryset().filter(status=CashSession.Status.OPEN)
        session = qs.first()
        if not session:
            return Response({"detail": "No open shift."}, status=404)
        return Response(self.get_serializer(session).data)

    @action(detail=False, methods=["post"])
    def open(self, request):
        serializer = OpenShiftSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        return Response(CashSessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        serializer = CloseShiftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = close_shift(
            session=self.get_object(),
            user=request.user,
            **serializer.validated_data,
        )
        return Response(CashSessionSerializer(session).data)

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        from decimal import Decimal

        amount = request.data.get("amount")
        if amount is None:
            return Response({"detail": "Amount is required."}, status=400)
        session = self.get_object()
        apply_cash(
            session=session,
            kind=CashKind.REFUND,
            amount=Decimal(str(amount)),
            user=request.user,
            reason=request.data.get("reason") or "Refund",
        )
        session.refresh_from_db()
        return Response(CashSessionSerializer(session).data)


class FinanceSummaryView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("ledger.view", "cash.drawer", "expense.view")

    def get(self, request):
        business = request.user.business
        receivables = Customer.objects.filter(business=business, is_active=True).aggregate(
            total=Sum("receivable_balance")
        )["total"] or 0
        money = DecimalField(max_digits=14, decimal_places=2)
        payable_total = (
            SupplierPayable.objects.filter(business=business)
            .exclude(status=SupplierPayable.Status.PAID)
            .aggregate(
                total=Sum(ExpressionWrapper(F("amount") - F("paid_amount"), output_field=money))
            )["total"]
            or 0
        )
        today = timezone.localdate()
        expenses_today = (
            Expense.objects.filter(business=business, created_at__date=today).aggregate(total=Sum("amount"))[
                "total"
            ]
            or 0
        )
        open_shift = CashSession.objects.filter(business=business, status=CashSession.Status.OPEN).first()
        return Response(
            {
                "receivables": str(receivables),
                "payables": str(payable_total),
                "expenses_today": str(expenses_today),
                "open_shift": CashSessionSerializer(open_shift).data if open_shift else None,
            }
        )

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasPermission
from apps.purchases.models import GoodsReceipt, PurchaseOrder, Supplier, SupplierLedgerEntry, SupplierPayable, SupplierPayment
from apps.purchases.serializers import (
    GoodsReceiptSerializer,
    PurchaseOrderSerializer,
    ReceiveGoodsSerializer,
    SupplierLedgerSerializer,
    SupplierPayableSerializer,
    SupplierPaymentSerializer,
    SupplierSerializer,
)
from apps.purchases.services import cancel_order, mark_ordered


class SupplierViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Supplier.objects.all()
    search_fields = ("name", "phone", "email", "city")
    filterset_fields = ("is_active",)

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve", "ledger"):
            return "supplier.view"
        return "supplier.manage"

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        entries = SupplierLedgerEntry.objects.filter(
            business=request.user.business, supplier=self.get_object()
        )
        return Response(SupplierLedgerSerializer(entries, many=True).data)

    def get_queryset(self):
        payable = ExpressionWrapper(
            F("payables__amount") - F("payables__paid_amount"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        return (
            super()
            .get_queryset()
            .annotate(
                payable_balance=Coalesce(Sum(payable), Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))),
                order_count=Count("purchase_orders", distinct=True),
            )
        )


class PurchaseOrderViewSet(
    BusinessQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = PurchaseOrder.objects.all()
    search_fields = ("number", "supplier__name")
    filterset_fields = ("status", "supplier", "branch")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "purchase.view"
        return "purchase.manage"

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("supplier", "branch")
            .annotate(
                annotated_total=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            F("lines__quantity") * F("lines__unit_cost"),
                            output_field=DecimalField(max_digits=14, decimal_places=2),
                        )
                    ),
                    Value(0, output_field=DecimalField(max_digits=14, decimal_places=2)),
                )
            )
        )
        if self.action == "list":
            return qs
        return qs.prefetch_related("lines__variant__product")

    def perform_destroy(self, instance):
        cancel_order(instance)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        order = mark_ordered(self.get_object())
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        order = self.get_object()
        payload = {
            **request.data,
            "purchase_order": str(order.id),
            "supplier": str(order.supplier_id),
            "branch": request.data.get("branch") or str(order.branch_id),
        }
        serializer = ReceiveGoodsSerializer(data=payload, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save()
        return Response(GoodsReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED)


class GoodsReceiptViewSet(
    BusinessQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = GoodsReceiptSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = GoodsReceipt.objects.all()
    search_fields = ("number", "supplier__name")
    filterset_fields = ("status", "supplier", "branch")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "purchase.view"
        return "purchase.manage"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("supplier", "branch", "purchase_order")
            .prefetch_related("lines__variant")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return ReceiveGoodsSerializer
        return GoodsReceiptSerializer

    def create(self, request, *args, **kwargs):
        serializer = ReceiveGoodsSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        receipt = serializer.save()
        return Response(GoodsReceiptSerializer(receipt).data, status=status.HTTP_201_CREATED)


class SupplierPayableViewSet(BusinessQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SupplierPayableSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "purchase.view"
    queryset = SupplierPayable.objects.all()
    filterset_fields = ("supplier", "status")

    def get_queryset(self):
        return super().get_queryset().select_related("supplier", "goods_receipt")


class SupplierPaymentViewSet(
    BusinessQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SupplierPaymentSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = SupplierPayment.objects.all()
    filterset_fields = ("supplier",)

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "supplier.view"
        return "supplier.manage"

    def get_queryset(self):
        return super().get_queryset().select_related("supplier", "branch")

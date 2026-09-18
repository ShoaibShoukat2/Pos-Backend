from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasPermission
from apps.inventory.models import StockLevel, StockMovement, StockOperation, StockTransfer
from apps.inventory.serializers import (
    StockLevelSerializer,
    StockMovementSerializer,
    StockOperationSerializer,
    StockTransferSerializer,
)


class StockLevelViewSet(BusinessQuerysetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = StockLevelSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "stock.view"
    queryset = StockLevel.objects.all()
    search_fields = ("variant__sku", "variant__barcode", "variant__name", "variant__product__name")
    filterset_fields = ("branch", "variant")

    def get_queryset(self):
        qs = super().get_queryset().select_related("variant__product", "branch")
        qs = qs.filter(variant__product__item_kind="product", variant__product__track_stock=True)
        if self.request.query_params.get("low_stock") in {"1", "true", "yes"}:
            qs = qs.filter(quantity__lt=F("variant__min_stock"))
        return qs


class StockMovementViewSet(BusinessQuerysetMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "stock.view"
    queryset = StockMovement.objects.all()
    search_fields = ("variant__sku", "variant__product__name", "reason")
    filterset_fields = ("branch", "variant", "movement_type")


class StockOperationViewSet(
    BusinessQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = StockOperationSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = StockOperation.objects.all()
    filterset_fields = ("kind", "branch", "status")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "stock.view"
        if self.request.data.get("kind") == StockOperation.Kind.COUNT:
            return "stock.count"
        return "stock.adjust"

    def get_queryset(self):
        return super().get_queryset().select_related("branch").prefetch_related("lines__variant")


class StockTransferViewSet(
    BusinessQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = StockTransferSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = StockTransfer.objects.all()
    filterset_fields = ("from_branch", "to_branch", "status")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "stock.view"
        return "stock.transfer"

    def get_queryset(self):
        return super().get_queryset().select_related("from_branch", "to_branch").prefetch_related("lines__variant")


class InventorySummaryView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "stock.view"

    def get(self, request):
        from apps.core.branch import apply_branch_scope

        business = request.user.business
        levels = apply_branch_scope(StockLevel.objects.filter(business=business), request)
        money = DecimalField(max_digits=18, decimal_places=2)
        stats = levels.aggregate(
            on_hand=Sum("quantity"),
            stock_value=Sum(
                ExpressionWrapper(F("quantity") * F("variant__cost_price"), output_field=money)
            ),
            low_stock=Count("id", filter=Q(quantity__lt=F("variant__min_stock"))),
            sku_locations=Count("id"),
        )
        return Response(
            {
                "on_hand_qty": str(stats["on_hand"] or 0),
                "stock_value": str(stats["stock_value"] or 0),
                "low_stock": stats["low_stock"] or 0,
                "sku_locations": stats["sku_locations"] or 0,
            }
        )

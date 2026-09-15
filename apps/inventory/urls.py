from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.inventory.views import (
    InventorySummaryView,
    StockLevelViewSet,
    StockMovementViewSet,
    StockOperationViewSet,
    StockTransferViewSet,
)

router = DefaultRouter()
router.register("stock", StockLevelViewSet, basename="stock-level")
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
router.register("stock-operations", StockOperationViewSet, basename="stock-operation")
router.register("stock-transfers", StockTransferViewSet, basename="stock-transfer")

urlpatterns = [
    path("inventory/summary/", InventorySummaryView.as_view(), name="inventory-summary"),
    path("", include(router.urls)),
]

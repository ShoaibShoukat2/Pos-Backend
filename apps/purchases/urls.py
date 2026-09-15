from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.purchases.views import (
    GoodsReceiptViewSet,
    PurchaseOrderViewSet,
    SupplierPayableViewSet,
    SupplierPaymentViewSet,
    SupplierViewSet,
)

router = DefaultRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("goods-receipts", GoodsReceiptViewSet, basename="goods-receipt")
router.register("payables", SupplierPayableViewSet, basename="payable")
router.register("supplier-payments", SupplierPaymentViewSet, basename="supplier-payment")

urlpatterns = [path("", include(router.urls))]

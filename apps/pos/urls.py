from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.pos.scanner import ScannerOpenView, ScannerPullView, ScannerPushView, ScannerStatusView
from apps.pos.views import CatalogSearchView, CheckoutView, SaleViewSet, SnapshotView, SyncView

router = DefaultRouter()
router.register("pos/sales", SaleViewSet, basename="pos-sale")

urlpatterns = [
    path("pos/checkout/", CheckoutView.as_view(), name="pos-checkout"),
    path("pos/sync/", SyncView.as_view(), name="pos-sync"),
    path("pos/snapshot/", SnapshotView.as_view(), name="pos-snapshot"),
    path("pos/catalog/", CatalogSearchView.as_view(), name="pos-catalog"),
    path("scanner/sessions/", ScannerOpenView.as_view(), name="scanner-open"),
    path("scanner/sessions/<str:token>/pull/", ScannerPullView.as_view(), name="scanner-pull"),
    path("scanner/sessions/<str:token>/", ScannerStatusView.as_view(), name="scanner-status"),
    path("scanner/sessions/<str:token>/push/", ScannerPushView.as_view(), name="scanner-push"),
    path("", include(router.urls)),
]

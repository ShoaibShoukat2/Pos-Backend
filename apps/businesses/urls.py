from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.businesses.views import (
    BranchViewSet,
    BusinessProfileView,
    CurrencyViewSet,
    InvoiceSettingsView,
    PublicPriceCheckerInfoView,
    PublicPriceCheckerSearchView,
    TaxRateViewSet,
)

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("currencies", CurrencyViewSet, basename="currency")
router.register("tax-rates", TaxRateViewSet, basename="tax-rate")

urlpatterns = [
    path("business/", BusinessProfileView.as_view(), name="business-profile"),
    path("invoice-settings/", InvoiceSettingsView.as_view(), name="invoice-settings"),
    # ── Public price checker (no auth) ───────────────────────────────────────
    path("public/price-check/<slug:slug>/", PublicPriceCheckerInfoView.as_view(), name="public-price-check-info"),
    path("public/price-check/<slug:slug>/search/", PublicPriceCheckerSearchView.as_view(), name="public-price-check-search"),
    path("", include(router.urls)),
]

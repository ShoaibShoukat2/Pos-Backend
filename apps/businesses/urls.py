from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.businesses.views import (
    BranchViewSet,
    BusinessProfileView,
    CurrencyViewSet,
    InvoiceSettingsView,
    TaxRateViewSet,
)

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("currencies", CurrencyViewSet, basename="currency")
router.register("tax-rates", TaxRateViewSet, basename="tax-rate")

urlpatterns = [
    path("business/", BusinessProfileView.as_view(), name="business-profile"),
    path("invoice-settings/", InvoiceSettingsView.as_view(), name="invoice-settings"),
    path("", include(router.urls)),
]

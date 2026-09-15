from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.customers.views import CustomerPaymentViewSet, CustomerSaleViewSet, CustomerViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("customer-sales", CustomerSaleViewSet, basename="customer-sale")
router.register("customer-payments", CustomerPaymentViewSet, basename="customer-payment")

urlpatterns = [path("", include(router.urls))]

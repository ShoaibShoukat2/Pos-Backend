from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.showroom.views import (
    CarBrandViewSet, CarPurchaseViewSet, CarSellerViewSet,
    CarSaleViewSet, CarViewSet, ExpenseCategoryViewSet,
    FuelTypeViewSet, ShowroomCustomerViewSet,
    ShowroomDashboardView, ShowroomExpenseViewSet,
    TransmissionViewSet,
)

router = DefaultRouter()
router.register("cars",           CarViewSet,              basename="car")
router.register("car-purchases",  CarPurchaseViewSet,      basename="car-purchase")
router.register("car-sales",      CarSaleViewSet,          basename="car-sale")
router.register("showroom-customers", ShowroomCustomerViewSet, basename="showroom-customer")
router.register("car-sellers",    CarSellerViewSet,        basename="car-seller")
router.register("showroom-expenses", ShowroomExpenseViewSet, basename="showroom-expense")
router.register("car-brands",     CarBrandViewSet,         basename="car-brand")
router.register("fuel-types",     FuelTypeViewSet,         basename="fuel-type")
router.register("transmissions",  TransmissionViewSet,     basename="transmission")
router.register("showroom-expense-categories", ExpenseCategoryViewSet, basename="showroom-expense-category")

urlpatterns = [
    path("showroom/dashboard/", ShowroomDashboardView.as_view(), name="showroom-dashboard"),
    path("showroom/", include(router.urls)),
]

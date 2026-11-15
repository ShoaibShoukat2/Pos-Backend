from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.rental.views import CarRentalViewSet, RentalCarViewSet, RentalCustomerViewSet, RentalDashboardView

router = DefaultRouter()
router.register("rental-cars", RentalCarViewSet, basename="rental-car")
router.register("rental-customers", RentalCustomerViewSet, basename="rental-customer")
router.register("rentals", CarRentalViewSet, basename="car-rental")

urlpatterns = [
    path("rental/dashboard/", RentalDashboardView.as_view(), name="rental-dashboard"),
    path("rental/", include(router.urls)),
]

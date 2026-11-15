from decimal import Decimal

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import BusinessQuerysetMixin
from apps.rental.models import CarRental, RentalCar, RentalCustomer
from apps.rental.serializers import (
    CarRentalListSerializer,
    CarRentalSerializer,
    RentalCarSerializer,
    RentalCustomerSerializer,
    rental_row,
)

ZERO = Decimal("0")


class RentalCarViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = RentalCarSerializer
    queryset = RentalCar.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = None
    filterset_fields = ("status",)
    search_fields = ("brand", "model", "registration_number", "color")


class RentalCustomerViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = RentalCustomerSerializer
    queryset = RentalCustomer.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = None
    search_fields = ("name", "phone", "cnic")


class CarRentalViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CarRentalSerializer
    queryset = CarRental.objects.all()
    permission_classes = [IsAuthenticated]
    search_fields = ("invoice_number", "customer__name", "car__registration_number", "car__model")

    def get_serializer_class(self):
        if self.action == "list":
            return CarRentalListSerializer
        return CarRentalSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("car", "customer")

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        rental = self.get_object()
        if rental.status != CarRental.Status.ACTIVE:
            raise ValidationError({"detail": "This rental is already closed."})
        rental.status = CarRental.Status.COMPLETED
        rental.save(update_fields=["status", "updated_at"])
        rental.car.status = RentalCar.Status.AVAILABLE
        rental.car.save(update_fields=["status"])
        return Response(CarRentalSerializer(rental).data)


class RentalDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        biz = request.user.business
        today = timezone.localdate()
        cars = RentalCar.objects.filter(business=biz)
        rentals = list(
            CarRental.objects.filter(business=biz).select_related("car", "customer").order_by("-start_date", "-created_at")
        )
        active = [row for row in rentals if row.status == CarRental.Status.ACTIVE]
        month = [row for row in rentals if row.start_date.year == today.year and row.start_date.month == today.month]
        month_revenue = sum((row.total_amount for row in month), ZERO)
        deposits = sum((row.deposit for row in active), ZERO)
        outstanding = sum((row.balance for row in active), ZERO)
        due_today = sum(1 for row in active if row.end_date == today)
        overdue = sum(1 for row in active if row.end_date < today)
        return Response({
            "cars_total": cars.count(),
            "available": cars.filter(status=RentalCar.Status.AVAILABLE).count(),
            "rented": cars.filter(status=RentalCar.Status.RENTED).count(),
            "maintenance": cars.filter(status=RentalCar.Status.MAINTENANCE).count(),
            "active_count": len(active),
            "due_today": due_today,
            "overdue": overdue,
            "month_revenue": str(month_revenue),
            "deposits_held": str(deposits),
            "outstanding": str(outstanding),
            "rentals": [rental_row(row, today) for row in rentals[:40]],
            "fleet": [
                {
                    "id": str(car.id),
                    "name": car.display_name,
                    "registration_number": car.registration_number,
                    "color": car.color,
                    "daily_rate": str(car.daily_rate),
                    "status": car.status,
                }
                for car in cars.order_by("status", "brand", "model")[:40]
            ],
        })

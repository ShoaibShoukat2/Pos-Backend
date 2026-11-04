from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import BusinessQuerysetMixin
from apps.showroom.models import (
    Car, CarBrand, CarPurchase, CarSale,
    CarSeller, FuelType, ShowroomCustomer,
    ShowroomExpense, ShowroomExpenseCategory, TransmissionType,
)
from apps.showroom.serializers import (
    CarBrandSerializer, CarPurchaseSerializer, CarSaleSerializer,
    CarSellerSerializer, CarSerializer, FuelTypeSerializer,
    ShowroomCustomerSerializer, ShowroomExpenseCategorySerializer,
    ShowroomExpenseSerializer, TransmissionTypeSerializer,
)

ZERO = Decimal("0")


class CarBrandViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CarBrandSerializer
    queryset = CarBrand.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = None


class FuelTypeViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = FuelTypeSerializer
    queryset = FuelType.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = None


class TransmissionViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = TransmissionTypeSerializer
    queryset = TransmissionType.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = None


class ExpenseCategoryViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ShowroomExpenseCategorySerializer
    queryset = ShowroomExpenseCategory.objects.all()
    permission_classes = [IsAuthenticated]
    pagination_class = None


class ShowroomCustomerViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ShowroomCustomerSerializer
    queryset = ShowroomCustomer.objects.all()
    permission_classes = [IsAuthenticated]
    search_fields = ("name", "phone", "cnic")


class CarSellerViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CarSellerSerializer
    queryset = CarSeller.objects.all()
    permission_classes = [IsAuthenticated]
    search_fields = ("name", "phone", "cnic")


class CarViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CarSerializer
    queryset = Car.objects.all()
    permission_classes = [IsAuthenticated]
    filterset_fields = ("status",)
    search_fields = ("model", "variant", "registration_number", "chassis_number", "color", "brand__name")

    def get_queryset(self):
        return super().get_queryset().select_related(
            "brand", "fuel_type", "transmission"
        ).prefetch_related("images")

    def perform_create(self, serializer):
        serializer.save(business=self.request.user.business)


class CarPurchaseViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CarPurchaseSerializer
    queryset = CarPurchase.objects.all()
    permission_classes = [IsAuthenticated]
    search_fields = ("car__model", "seller__name")

    def get_queryset(self):
        return super().get_queryset().select_related("car__brand", "seller")

    def perform_create(self, serializer):
        serializer.save(business=self.request.user.business, created_by=self.request.user)


class CarSaleViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CarSaleSerializer
    queryset = CarSale.objects.all()
    permission_classes = [IsAuthenticated]
    search_fields = ("car__model", "customer__name")

    def get_queryset(self):
        return super().get_queryset().select_related("car__brand", "customer", "car__purchase")


class ShowroomExpenseViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ShowroomExpenseSerializer
    queryset = ShowroomExpense.objects.all()
    permission_classes = [IsAuthenticated]
    filterset_fields = ("category",)
    search_fields = ("title",)

    def get_queryset(self):
        return super().get_queryset().select_related("category", "car__brand")

    def perform_create(self, serializer):
        serializer.save(business=self.request.user.business, created_by=self.request.user)


class ShowroomDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        biz = request.user.business

        cars        = Car.objects.filter(business=biz)
        total_cars  = cars.count()
        available   = cars.filter(status="available").count()
        reserved    = cars.filter(status="reserved").count()
        sold        = cars.filter(status="sold").count()

        purchases   = CarPurchase.objects.filter(business=biz)
        sales       = CarSale.objects.filter(business=biz)
        expenses    = ShowroomExpense.objects.filter(business=biz)

        total_investment = (
            purchases.aggregate(
                v=Coalesce(Sum(F("purchase_price") + F("additional_expenses")), Value(0), output_field=DecimalField())
            )["v"]
        )
        total_sales_revenue = (
            sales.aggregate(
                v=Coalesce(Sum(ExpressionWrapper(F("selling_price") - F("discount"), output_field=DecimalField())), Value(0), output_field=DecimalField())
            )["v"]
        )
        total_expenses = (
            expenses.aggregate(v=Coalesce(Sum("amount"), Value(0), output_field=DecimalField()))["v"]
        )
        total_profit = total_sales_revenue - total_investment - total_expenses

        # Customer dues (remaining amounts on sales)
        customer_dues = sum(
            max(0, float(s.final_amount) - float(s.received_amount))
            for s in sales.select_related("car__purchase")
        )
        # Seller dues (remaining on purchases)
        seller_dues = sum(
            max(0, float(p.total_cost) - float(p.advance_paid))
            for p in purchases
        )

        # Recent 5 sales
        recent_sales = [
            {
                "id": str(s.id),
                "car": s.car.display_name,
                "customer": s.customer.name,
                "amount": str(s.final_amount),
                "date": str(s.sale_date),
                "profit": str(s.profit),
            }
            for s in sales.select_related("car__brand", "customer", "car__purchase").order_by("-sale_date")[:5]
        ]

        # Available cars list
        available_cars = [
            {
                "id": str(c.id),
                "name": c.display_name,
                "color": c.color,
                "year": c.model_year,
                "price": str(c.selling_price),
                "mileage": c.mileage_km,
            }
            for c in cars.filter(status="available").select_related("brand").order_by("-created_at")[:6]
        ]

        return Response({
            "total_cars": total_cars,
            "available": available,
            "reserved": reserved,
            "sold": sold,
            "total_investment": str(total_investment),
            "total_sales_revenue": str(total_sales_revenue),
            "total_expenses": str(total_expenses),
            "total_profit": str(total_profit),
            "customer_dues": str(round(customer_dues, 2)),
            "seller_dues": str(round(seller_dues, 2)),
            "recent_sales": recent_sales,
            "available_cars": available_cars,
        })

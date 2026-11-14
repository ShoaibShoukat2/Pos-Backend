from datetime import date
from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import BusinessQuerysetMixin
from apps.showroom.models import (
    Car, CarBrand, CarPurchase, CarSale, CarSalePayment,
    CarSeller, FuelType, ShowroomCustomer,
    ShowroomExpense, ShowroomExpenseCategory, TransmissionType,
)
from apps.showroom.serializers import (
    CarBrandSerializer, CarPurchaseSerializer, CarSaleListSerializer, CarSaleSerializer,
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
    search_fields = ("car__model", "customer__name", "invoice_number")

    def get_serializer_class(self):
        if self.action == "list":
            return CarSaleListSerializer
        return CarSaleSerializer

    def get_queryset(self):
        return super().get_queryset().select_related(
            "car__brand", "car__fuel_type", "car__transmission", "customer", "car__purchase"
        ).prefetch_related("payments")

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        sale = self.get_object()
        try:
            amount = Decimal(str(request.data.get("amount") or "0"))
        except Exception:
            raise ValidationError({"amount": "Enter a valid amount."})
        if amount <= ZERO:
            raise ValidationError({"amount": "Enter an amount greater than zero."})
        if amount > sale.remaining_amount:
            raise ValidationError({"amount": f"Balance is only Rs {sale.remaining_amount}."})
        method = request.data.get("payment_method") or sale.payment_method
        if method not in dict(CarSale.PaymentMethod.choices):
            raise ValidationError({"payment_method": "Unknown payment method."})
        raw_date = request.data.get("payment_date") or timezone.localdate().isoformat()
        try:
            paid_on = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            raise ValidationError({"payment_date": "Use a date like 2026-11-14."})
        CarSalePayment.objects.create(
            business=sale.business,
            sale=sale,
            amount=amount,
            payment_date=paid_on,
            payment_method=method,
            notes=(request.data.get("notes") or "")[:200],
            created_by=request.user,
        )
        sale.received_amount = sale.received_amount + amount
        sale.save(update_fields=["received_amount"])
        sale = self.get_queryset().get(pk=sale.pk)
        return Response(CarSaleSerializer(sale, context={"request": request}).data)


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
        sale_rows = list(
            sales.select_related("car__brand", "customer", "car__purchase").order_by("-sale_date", "-created_at")
        )
        realized = sum((s.profit for s in sale_rows), ZERO)
        total_profit = realized - total_expenses

        customer_dues = sum((max(ZERO, s.final_amount - s.received_amount) for s in sale_rows), ZERO)
        seller_dues = sum((max(ZERO, p.total_cost - p.advance_paid) for p in purchases), ZERO)
        cash_received = sum((s.received_amount for s in sale_rows), ZERO)
        dues_count = sum(1 for s in sale_rows if s.remaining_amount > ZERO)
        unsigned_invoices = sum(1 for s in sale_rows if not s.is_signed)

        today = timezone.localdate()
        month_rows = [s for s in sale_rows if s.sale_date.year == today.year and s.sale_date.month == today.month]
        today_rows = [s for s in sale_rows if s.sale_date == today]
        month_sales = sum((s.final_amount for s in month_rows), ZERO)
        month_profit = sum((s.profit for s in month_rows), ZERO)
        today_sales = sum((s.final_amount for s in today_rows), ZERO)

        unsold_ids = list(cars.exclude(status="sold").values_list("id", flat=True))
        stock_cost = purchases.filter(car_id__in=unsold_ids).aggregate(
            v=Coalesce(Sum(F("purchase_price") + F("additional_expenses")), Value(0), output_field=DecimalField())
        )["v"]
        stock_value = cars.exclude(status="sold").aggregate(
            v=Coalesce(Sum("selling_price"), Value(0), output_field=DecimalField())
        )["v"]

        monthly = []
        for offset in range(5, -1, -1):
            index = (today.year * 12 + (today.month - 1)) - offset
            year, month = divmod(index, 12)
            month += 1
            bucket = [s for s in sale_rows if s.sale_date.year == year and s.sale_date.month == month]
            monthly.append({
                "label": date(year, month, 1).strftime("%b"),
                "sales": str(sum((s.final_amount for s in bucket), ZERO)),
                "count": len(bucket),
            })

        recent_sales = [
            {
                "id": str(s.id),
                "invoice_number": s.invoice_number or "",
                "car": s.car.display_name,
                "customer": s.customer.name,
                "amount": str(s.final_amount),
                "remaining": str(s.remaining_amount),
                "date": str(s.sale_date),
                "profit": str(s.profit),
                "signed": s.is_signed,
            }
            for s in sale_rows[:6]
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
            "customer_dues": str(customer_dues),
            "seller_dues": str(seller_dues),
            "cash_received": str(cash_received),
            "dues_count": dues_count,
            "unsigned_invoices": unsigned_invoices,
            "today_sales": str(today_sales),
            "today_count": len(today_rows),
            "month_sales": str(month_sales),
            "month_profit": str(month_profit),
            "month_count": len(month_rows),
            "stock_value": str(stock_value),
            "stock_cost": str(stock_cost),
            "monthly": monthly,
            "recent_sales": recent_sales,
            "available_cars": available_cars,
        })

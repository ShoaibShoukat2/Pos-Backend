from datetime import date
from decimal import Decimal

from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import BusinessQuerysetMixin
from apps.rental.models import CarRental, RentalCar, RentalCustomer, RentalTerms
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

    def perform_destroy(self, instance):
        if instance.rentals.filter(status=CarRental.Status.ACTIVE).exists():
            raise ValidationError({"detail": "This car is on rent. Check it in before deleting it."})
        if instance.rentals.exists():
            raise ValidationError({"detail": "This car has rental history. Move it to workshop instead of deleting it."})
        instance.delete()


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

    def perform_destroy(self, instance):
        car = instance.car
        was_active = instance.status == CarRental.Status.ACTIVE
        instance.delete()
        if was_active and not car.rentals.filter(status=CarRental.Status.ACTIVE).exists():
            car.status = RentalCar.Status.AVAILABLE
            car.save(update_fields=["status"])

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

    @action(detail=True, methods=["post"])
    def extend(self, request, pk=None):
        rental = self.get_object()
        if rental.status != CarRental.Status.ACTIVE:
            raise ValidationError({"detail": "This rental is already closed."})
        try:
            end = date.fromisoformat(str(request.data.get("end_date") or "")[:10])
        except ValueError:
            raise ValidationError({"end_date": "Choose the new return date."})
        if end < rental.start_date:
            raise ValidationError({"end_date": "Return date cannot be before the start date."})
        days = max(1, (end - rental.start_date).days or 1)
        rental.end_date = end
        rental.total_amount = rental.daily_rate * days
        rental.save(update_fields=["end_date", "total_amount", "updated_at"])
        return Response(CarRentalSerializer(rental).data)

    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        rental = self.get_object()
        try:
            amount = Decimal(str(request.data.get("amount") or "0"))
        except Exception:
            raise ValidationError({"amount": "Enter a valid amount."})
        if amount <= ZERO:
            raise ValidationError({"amount": "Enter an amount greater than zero."})
        rental.received_amount = rental.received_amount + amount
        rental.save(update_fields=["received_amount", "updated_at"])
        return Response(CarRentalSerializer(rental).data)


DEFAULT_CLAUSES = [
    "میں جو گاڑی کرائے پر لے رہا ہوں میں نے اچھی طرح چیک کر لی ہے۔ اپنے استعمال کے دوران ہر قسم کے نقصان کا ذمہ دار ہوں اور تمام نقصان کی پوری رقم ادا کروں گا۔",
    "خدا نخواستہ ایکسیڈنٹ یا کسی کے نقصان کی صورت میں گاڑی کا تمام کام خود کرواؤں گا اور روزانہ کا کرایہ پابندی و باقاعدگی سے ادا کروں گا۔ میں اس کا ذمہ دار ہوں، اور گاڑی جب تک کام کے لیے کھڑی رہے گی تب تک گاڑی کا کرایہ پورا ادا کروں گا۔",
    "گاڑی چوری ہونے کی صورت میں جب تک دوسری گاڑی نہیں آ جاتی، میں اس کا روزانہ کرایہ ادا کرنے اور پوری گاڑی خریدنے (یا اس کی مکمل قیمت ادا کرنے) کا پابند ہوں گا۔",
    "میں یہ وعدہ کرتا ہوں کہ گاڑی کے کسی پرزے کو نہیں بدلوں گا اور نہ ہی کسی دوسرے استعمال میں دوں گا۔",
    "میں یہ وعدہ کرتا ہوں کہ گاڑی کے ذریعے کوئی غیر قانونی کام نہیں کروں گا، ایکسیڈنٹ یا کسی اور صورت میں پولیس کیس سے نمٹنے کی پوری ذمہ داری میری ہوگی۔",
    "اگر گاڑی مقررہ وقت پر واپس نہ کی تو جب تک واپس کروں گا 500 روپے فی گھنٹہ ادا کروں گا۔",
    "بغیر اجازت گاڑی کراچی سے باہر نہیں لے جاؤں گا، ورنہ کرایہ دگنا ادا کروں گا۔",
    "گاڑی کی واپسی دن میں کی جائے گی۔ رات کے وقت سے لیٹ واپسی صبح 11:00 بجے تک ہوگی۔",
    "گاڑی کی خوبصورتی بگڑنے، یا کراچی سے باہر جانے کی صورت میں چارجز دگنے کیے جائیں گے۔",
    "گاڑی کرائے پر لیتے وقت بطور سیکورٹی گاڑی کی پوری مالیت کا چیک جمع کرواؤں گا، جو گاڑی کی بحفاظت واپسی پر واپس لے لوں گا۔",
    "میں نے تمام شرائط پڑھ لی ہیں، مجھے منظور ہیں۔",
]


def clean_clauses(value):
    if not isinstance(value, list):
        raise ValidationError({"clauses": "Write each line on its own."})
    rows = []
    for item in value:
        text = str(item or "").strip()
        if not text:
            continue
        if len(text) > 800:
            raise ValidationError({"clauses": "One line is too long."})
        rows.append(text)
    if not rows:
        raise ValidationError({"clauses": "Keep at least one line on the sheet."})
    if len(rows) > 40:
        raise ValidationError({"clauses": "Keep the sheet to 40 lines."})
    return rows


class RentalTermsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        business = request.user.business
        sheet = RentalTerms.objects.filter(business=business).first()
        if sheet is None or not sheet.clauses:
            return Response({
                "title": (sheet.title if sheet and sheet.title else "") or business.name,
                "clauses": DEFAULT_CLAUSES,
                "footer": (sheet.footer if sheet and sheet.footer else "") or "دستخط / انگوٹھا",
            })
        return Response({
            "title": sheet.title or business.name,
            "clauses": sheet.clauses,
            "footer": sheet.footer or "دستخط / انگوٹھا",
        })

    def put(self, request):
        business = request.user.business
        title = str(request.data.get("title") or "").strip()[:160]
        footer = str(request.data.get("footer") or "").strip()[:120] or "دستخط / انگوٹھا"
        clauses = clean_clauses(request.data.get("clauses"))
        sheet, _created = RentalTerms.objects.get_or_create(business=business)
        sheet.title = title
        sheet.footer = footer
        sheet.clauses = clauses
        sheet.save()
        return Response({
            "title": sheet.title or business.name,
            "clauses": sheet.clauses,
            "footer": sheet.footer,
        })


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

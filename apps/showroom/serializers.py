from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.core.numbering import allocate_number
from apps.showroom.models import (
    Car, CarBrand, CarImage, CarPurchase, CarSale, CarSalePayment,
    CarSeller, FuelType, ShowroomCustomer,
    ShowroomExpense, ShowroomExpenseCategory, TransmissionType,
)


def clean_signature(value):
    if not value:
        return ""
    if not isinstance(value, str) or not value.startswith("data:image/png;base64,"):
        raise serializers.ValidationError("Signature must be a saved PNG drawing.")
    if len(value) > 500_000:
        raise serializers.ValidationError("Signature image is too large.")
    return value


class CarBrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarBrand
        fields = ("id", "name", "is_active")
        read_only_fields = ("id",)


class FuelTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelType
        fields = ("id", "name")
        read_only_fields = ("id",)


class TransmissionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransmissionType
        fields = ("id", "name")
        read_only_fields = ("id",)


class ShowroomExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ShowroomExpenseCategory
        fields = ("id", "name")
        read_only_fields = ("id",)


class ShowroomCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShowroomCustomer
        fields = ("id", "name", "phone", "cnic", "address", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class CarSellerSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarSeller
        fields = ("id", "name", "phone", "cnic", "address", "is_active", "created_at")
        read_only_fields = ("id", "created_at")


class CarImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarImage
        fields = ("id", "image", "order")
        read_only_fields = ("id",)


class CarSerializer(serializers.ModelSerializer):
    brand_name       = serializers.CharField(source="brand.name", read_only=True)
    fuel_type_name   = serializers.CharField(source="fuel_type.name", read_only=True)
    transmission_name= serializers.CharField(source="transmission.name", read_only=True)
    display_name     = serializers.CharField(read_only=True)
    images           = CarImageSerializer(many=True, read_only=True)

    class Meta:
        model = Car
        fields = (
            "id", "brand", "brand_name", "model", "variant", "model_year",
            "registration_number", "chassis_number", "engine_number",
            "color", "engine_cc", "fuel_type", "fuel_type_name",
            "transmission", "transmission_name", "mileage_km",
            "purchase_price", "selling_price", "status",
            "notes", "display_name", "images", "created_at",
        )
        read_only_fields = ("id", "created_at")


class CarPurchaseSerializer(serializers.ModelSerializer):
    car_display  = serializers.CharField(source="car.display_name", read_only=True)
    seller_name  = serializers.CharField(source="seller.name", read_only=True)
    total_cost       = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    remaining_payment= serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = CarPurchase
        fields = (
            "id", "car", "car_display", "seller", "seller_name",
            "purchase_date", "purchase_price", "additional_expenses",
            "advance_paid", "payment_method", "notes",
            "total_cost", "remaining_payment", "created_at",
        )
        read_only_fields = ("id", "created_at")


class CarSalePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarSalePayment
        fields = ("id", "amount", "payment_date", "payment_method", "notes", "created_at")
        read_only_fields = fields


def _car_info(car):
    if not car:
        return None
    return {
        "id": str(car.id),
        "display_name": car.display_name,
        "brand_name": car.brand.name if car.brand_id else "",
        "model": car.model,
        "variant": car.variant,
        "model_year": car.model_year,
        "color": car.color,
        "registration_number": car.registration_number,
        "chassis_number": car.chassis_number,
        "engine_number": car.engine_number,
        "engine_cc": car.engine_cc,
        "fuel_type_name": car.fuel_type.name if car.fuel_type_id else "",
        "transmission_name": car.transmission.name if car.transmission_id else "",
        "mileage_km": car.mileage_km,
        "purchase_price": str(car.purchase_price),
    }


def _customer_info(customer):
    if not customer:
        return None
    return {
        "id": str(customer.id),
        "name": customer.name,
        "phone": customer.phone,
        "cnic": customer.cnic,
        "address": customer.address,
    }


class CarSaleSerializer(serializers.ModelSerializer):
    car_display      = serializers.CharField(source="car.display_name", read_only=True)
    customer_name    = serializers.CharField(source="customer.name", read_only=True)
    final_amount     = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    profit           = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    signed           = serializers.BooleanField(source="is_signed", read_only=True)
    car_info         = serializers.SerializerMethodField()
    customer_info    = serializers.SerializerMethodField()
    payments         = CarSalePaymentSerializer(many=True, read_only=True)

    class Meta:
        model = CarSale
        fields = (
            "id", "car", "car_display", "customer", "customer_name",
            "sale_date", "selling_price", "discount", "final_amount",
            "received_amount", "remaining_amount", "payment_method",
            "profit", "notes", "invoice_number", "signed", "signed_at",
            "customer_signature", "dealer_signature",
            "car_info", "customer_info", "payments", "created_at",
        )
        read_only_fields = ("id", "created_at", "invoice_number", "signed_at")

    def get_car_info(self, obj):
        return _car_info(obj.car)

    def get_customer_info(self, obj):
        return _customer_info(obj.customer)

    def validate_customer_signature(self, value):
        return clean_signature(value)

    def validate_dealer_signature(self, value):
        return clean_signature(value)

    def validate_car(self, car):
        if self.instance is None and car.status == "sold":
            raise serializers.ValidationError("This car is already sold.")
        return car

    @transaction.atomic
    def create(self, validated):
        request = self.context["request"]
        validated["created_by"] = request.user
        validated["business"] = request.user.business
        validated["invoice_number"] = allocate_number(request.user.business, "car_sale", "SR", 5)
        received = validated.get("received_amount") or 0
        sale = super().create(validated)
        sale.car.status = "sold"
        sale.car.save(update_fields=["status"])
        if received and received > 0:
            CarSalePayment.objects.create(
                business=sale.business,
                sale=sale,
                amount=received,
                payment_date=sale.sale_date,
                payment_method=sale.payment_method,
                notes="Received at sale",
                created_by=request.user,
            )
        return sale

    def update(self, instance, validated):
        touched_sig = "customer_signature" in validated or "dealer_signature" in validated
        sale = super().update(instance, validated)
        if touched_sig and sale.is_signed:
            sale.signed_at = timezone.now()
            sale.save(update_fields=["signed_at"])
        return sale


class CarSaleListSerializer(CarSaleSerializer):
    class Meta(CarSaleSerializer.Meta):
        fields = tuple(
            field for field in CarSaleSerializer.Meta.fields
            if field not in ("customer_signature", "dealer_signature", "car_info", "customer_info", "payments")
        )


class ShowroomExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    car_display   = serializers.CharField(source="car.display_name", read_only=True)
    is_car_specific = serializers.BooleanField(read_only=True)

    class Meta:
        model = ShowroomExpense
        fields = (
            "id", "category", "category_name", "car", "car_display",
            "title", "amount", "expense_date", "payment_method",
            "description", "is_car_specific", "created_at",
        )
        read_only_fields = ("id", "created_at")

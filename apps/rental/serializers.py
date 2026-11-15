from datetime import date

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.core.numbering import allocate_number
from apps.rental.models import CarRental, RentalCar, RentalCustomer


def clean_signature(value):
    if not value:
        return ""
    if not isinstance(value, str) or not value.startswith("data:image/png;base64,"):
        raise serializers.ValidationError("Signature must be a saved PNG drawing.")
    if len(value) > 500_000:
        raise serializers.ValidationError("Signature image is too large.")
    return value


def clean_capture(value, label):
    if not value:
        return ""
    if not isinstance(value, str) or not (
        value.startswith("data:image/jpeg;base64,") or value.startswith("data:image/png;base64,")
    ):
        raise serializers.ValidationError(f"{label} must be a saved photo.")
    if len(value) > 900_000:
        raise serializers.ValidationError(f"{label} is too large. Capture it again.")
    return value


class RentalCarSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = RentalCar
        fields = (
            "id", "brand", "model", "model_year", "registration_number", "color",
            "daily_rate", "status", "notes", "display_name", "created_at",
        )
        read_only_fields = ("id", "created_at")


class RentalCustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalCustomer
        fields = ("id", "name", "phone", "cnic", "address", "created_at")
        read_only_fields = ("id", "created_at")


class CarRentalSerializer(serializers.ModelSerializer):
    car_name = serializers.CharField(source="car.display_name", read_only=True)
    registration_number = serializers.CharField(source="car.registration_number", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    customer_cnic = serializers.CharField(source="customer.cnic", read_only=True)
    customer_address = serializers.CharField(source="customer.address", read_only=True)
    days = serializers.IntegerField(read_only=True)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    signed = serializers.BooleanField(source="is_signed", read_only=True)

    class Meta:
        model = CarRental
        fields = (
            "id", "car", "car_name", "registration_number",
            "customer", "customer_name", "customer_phone", "customer_cnic", "customer_address",
            "start_date", "end_date", "days", "daily_rate", "total_amount", "deposit",
            "received_amount", "balance", "payment_method", "notes", "invoice_number",
            "status", "signed", "signed_at",
            "customer_photo", "customer_signature", "dealer_signature",
            "created_at",
        )
        read_only_fields = ("id", "created_at", "invoice_number", "total_amount", "signed_at", "status")

    def validate_customer_signature(self, value):
        return clean_signature(value)

    def validate_dealer_signature(self, value):
        return clean_signature(value)

    def validate_customer_photo(self, value):
        return clean_capture(value, "Customer photo")

    def validate(self, attrs):
        start = attrs.get("start_date") or getattr(self.instance, "start_date", None)
        end = attrs.get("end_date") or getattr(self.instance, "end_date", None)
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "Return date cannot be before the start date."})
        car = attrs.get("car")
        if self.instance is None and car and car.status != RentalCar.Status.AVAILABLE:
            raise serializers.ValidationError({"car": "This car is not available to rent."})
        return attrs

    @transaction.atomic
    def create(self, validated):
        request = self.context["request"]
        car = validated["car"]
        start = validated["start_date"]
        end = validated["end_date"]
        days = max(1, (end - start).days or 1)
        rate = validated["daily_rate"]
        validated["total_amount"] = rate * days
        validated["created_by"] = request.user
        validated["business"] = request.user.business
        validated["invoice_number"] = allocate_number(request.user.business, "car_rental", "RC", 5)
        rental = super().create(validated)
        car.status = RentalCar.Status.RENTED
        car.save(update_fields=["status"])
        return rental

    def update(self, instance, validated):
        touched = any(field in validated for field in ("customer_signature", "dealer_signature", "customer_photo"))
        rental = super().update(instance, validated)
        if touched and rental.is_signed and not rental.signed_at:
            rental.signed_at = timezone.now()
            rental.save(update_fields=["signed_at"])
        return rental


class CarRentalListSerializer(CarRentalSerializer):
    class Meta(CarRentalSerializer.Meta):
        fields = tuple(
            field for field in CarRentalSerializer.Meta.fields
            if field not in ("customer_photo", "customer_signature", "dealer_signature")
        )


def rental_row(rental, today: date):
    overdue = rental.status == "active" and rental.end_date < today
    due_today = rental.status == "active" and rental.end_date == today
    return {
        "id": str(rental.id),
        "invoice_number": rental.invoice_number or "",
        "car": rental.car.display_name,
        "registration_number": rental.car.registration_number,
        "customer": rental.customer.name,
        "phone": rental.customer.phone,
        "cnic": rental.customer.cnic,
        "start_date": rental.start_date.isoformat(),
        "end_date": rental.end_date.isoformat(),
        "days": rental.days,
        "daily_rate": str(rental.daily_rate),
        "total_amount": str(rental.total_amount),
        "deposit": str(rental.deposit),
        "received_amount": str(rental.received_amount),
        "balance": str(rental.balance),
        "payment_method": rental.payment_method,
        "status": "overdue" if overdue else ("due_today" if due_today else rental.status),
        "signed": rental.is_signed,
    }

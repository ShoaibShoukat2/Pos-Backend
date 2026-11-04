from rest_framework import serializers
from apps.showroom.models import (
    Car, CarBrand, CarImage, CarPurchase, CarSale,
    CarSeller, FuelType, ShowroomCustomer,
    ShowroomExpense, ShowroomExpenseCategory, TransmissionType,
)


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


class CarSaleSerializer(serializers.ModelSerializer):
    car_display      = serializers.CharField(source="car.display_name", read_only=True)
    customer_name    = serializers.CharField(source="customer.name", read_only=True)
    final_amount     = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    remaining_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    profit           = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = CarSale
        fields = (
            "id", "car", "car_display", "customer", "customer_name",
            "sale_date", "selling_price", "discount", "final_amount",
            "received_amount", "remaining_amount", "payment_method",
            "profit", "notes", "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate_car(self, car):
        if car.status == "sold":
            raise serializers.ValidationError("This car is already sold.")
        return car

    def create(self, validated):
        request = self.context["request"]
        validated["created_by"] = request.user
        sale = super().create(validated)
        # Mark car as sold
        sale.car.status = "sold"
        sale.car.save(update_fields=["status"])
        return sale


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

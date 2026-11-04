from django.conf import settings
from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel


# ── Reference / Settings models ───────────────────────────────────────────────

class CarBrand(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="car_brands")
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    objects = BusinessScopedManager()
    class Meta:
        unique_together = ("business", "name")
        ordering = ["name"]
    def __str__(self): return self.name


class FuelType(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="fuel_types")
    name = models.CharField(max_length=60)
    objects = BusinessScopedManager()
    class Meta:
        unique_together = ("business", "name")
        ordering = ["name"]
    def __str__(self): return self.name


class TransmissionType(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="transmission_types")
    name = models.CharField(max_length=60)
    objects = BusinessScopedManager()
    class Meta:
        unique_together = ("business", "name")
        ordering = ["name"]
    def __str__(self): return self.name


class ShowroomExpenseCategory(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="showroom_expense_categories")
    name = models.CharField(max_length=100)
    objects = BusinessScopedManager()
    class Meta:
        unique_together = ("business", "name")
        ordering = ["name"]
    def __str__(self): return self.name


# ── People ────────────────────────────────────────────────────────────────────

class ShowroomCustomer(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="showroom_customers")
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=30, blank=True)
    cnic = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    objects = BusinessScopedManager()
    class Meta:
        ordering = ["name"]
    def __str__(self): return self.name


class CarSeller(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="car_sellers")
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=30, blank=True)
    cnic = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    objects = BusinessScopedManager()
    class Meta:
        ordering = ["name"]
    def __str__(self): return self.name


# ── Car Inventory ─────────────────────────────────────────────────────────────

class Car(TimeStampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED  = "reserved",  "Reserved"
        SOLD      = "sold",      "Sold"

    business            = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="cars")
    brand               = models.ForeignKey(CarBrand, on_delete=models.PROTECT, related_name="cars")
    model               = models.CharField(max_length=120)
    variant             = models.CharField(max_length=120, blank=True)
    model_year          = models.PositiveSmallIntegerField()
    registration_number = models.CharField(max_length=30, blank=True)
    chassis_number      = models.CharField(max_length=60, blank=True)
    engine_number       = models.CharField(max_length=60, blank=True)
    color               = models.CharField(max_length=60, blank=True)
    engine_cc           = models.PositiveIntegerField(default=0)
    fuel_type           = models.ForeignKey(FuelType, on_delete=models.SET_NULL, null=True, blank=True)
    transmission        = models.ForeignKey(TransmissionType, on_delete=models.SET_NULL, null=True, blank=True)
    mileage_km          = models.PositiveIntegerField(default=0)
    purchase_price      = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    selling_price       = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    status              = models.CharField(max_length=12, choices=Status.choices, default=Status.AVAILABLE)
    notes               = models.TextField(blank=True)
    objects             = BusinessScopedManager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "status"], name="car_biz_status_idx"),
        ]

    def __str__(self):
        return f"{self.brand.name} {self.model} {self.model_year}"

    @property
    def display_name(self):
        parts = [self.brand.name, self.model]
        if self.variant: parts.append(self.variant)
        parts.append(str(self.model_year))
        return " ".join(parts)


class CarImage(TimeStampedModel):
    car   = models.ForeignKey(Car, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="showroom/cars/")
    order = models.PositiveSmallIntegerField(default=0)
    class Meta:
        ordering = ["order", "created_at"]


# ── Car Purchase ──────────────────────────────────────────────────────────────

class CarPurchase(TimeStampedModel):
    class PaymentMethod(models.TextChoices):
        CASH         = "cash",         "Cash"
        BANK         = "bank",         "Bank Transfer"
        CARD         = "card",         "Card"
        JAZZCASH     = "jazzcash",     "JazzCash"
        EASYPAISA    = "easypaisa",    "Easypaisa"

    business            = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="car_purchases")
    car                 = models.OneToOneField(Car, on_delete=models.PROTECT, related_name="purchase")
    seller              = models.ForeignKey(CarSeller, on_delete=models.PROTECT, related_name="purchases")
    purchase_date       = models.DateField()
    purchase_price      = models.DecimalField(max_digits=16, decimal_places=2)
    additional_expenses = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    advance_paid        = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_method      = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    notes               = models.TextField(blank=True)
    created_by          = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    objects             = BusinessScopedManager()

    class Meta:
        ordering = ["-purchase_date", "-created_at"]

    @property
    def total_cost(self):
        return self.purchase_price + self.additional_expenses

    @property
    def remaining_payment(self):
        return max(0, self.total_cost - self.advance_paid)


# ── Car Sale ──────────────────────────────────────────────────────────────────

class CarSale(TimeStampedModel):
    class PaymentMethod(models.TextChoices):
        CASH      = "cash",      "Cash"
        BANK      = "bank",      "Bank Transfer"
        CARD      = "card",      "Card"
        JAZZCASH  = "jazzcash",  "JazzCash"
        EASYPAISA = "easypaisa", "Easypaisa"

    business         = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="car_sales")
    car              = models.OneToOneField(Car, on_delete=models.PROTECT, related_name="sale")
    customer         = models.ForeignKey(ShowroomCustomer, on_delete=models.PROTECT, related_name="purchases")
    sale_date        = models.DateField()
    selling_price    = models.DecimalField(max_digits=16, decimal_places=2)
    discount         = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    received_amount  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_method   = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    notes            = models.TextField(blank=True)
    created_by       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    objects          = BusinessScopedManager()

    class Meta:
        ordering = ["-sale_date", "-created_at"]

    @property
    def final_amount(self):
        return self.selling_price - self.discount

    @property
    def remaining_amount(self):
        return max(0, self.final_amount - self.received_amount)

    @property
    def profit(self):
        purchase = getattr(self.car, "purchase", None)
        if not purchase:
            return self.final_amount
        return self.final_amount - purchase.total_cost


# ── Expenses ──────────────────────────────────────────────────────────────────

class ShowroomExpense(TimeStampedModel):
    class PaymentMethod(models.TextChoices):
        CASH      = "cash",      "Cash"
        BANK      = "bank",      "Bank Transfer"
        CARD      = "card",      "Card"
        JAZZCASH  = "jazzcash",  "JazzCash"
        EASYPAISA = "easypaisa", "Easypaisa"

    business       = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="showroom_expenses")
    category       = models.ForeignKey(ShowroomExpenseCategory, on_delete=models.PROTECT, related_name="expenses")
    car            = models.ForeignKey(Car, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses",
                                       help_text="Leave blank for general expense")
    title          = models.CharField(max_length=200)
    amount         = models.DecimalField(max_digits=14, decimal_places=2)
    expense_date   = models.DateField()
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    description    = models.TextField(blank=True)
    created_by     = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    objects        = BusinessScopedManager()

    class Meta:
        ordering = ["-expense_date", "-created_at"]

    @property
    def is_car_specific(self):
        return self.car_id is not None

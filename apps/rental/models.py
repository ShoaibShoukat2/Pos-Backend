from django.conf import settings
from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel


class RentalCar(TimeStampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RENTED = "rented", "On rent"
        MAINTENANCE = "maintenance", "Maintenance"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="rental_cars")
    brand = models.CharField(max_length=80)
    model = models.CharField(max_length=80)
    model_year = models.PositiveSmallIntegerField(default=0)
    registration_number = models.CharField(max_length=30, blank=True)
    color = models.CharField(max_length=40, blank=True)
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.AVAILABLE)
    notes = models.TextField(blank=True)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["brand", "model"]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        parts = [self.brand, self.model]
        if self.model_year:
            parts.append(str(self.model_year))
        return " ".join(parts)


class RentalTerms(TimeStampedModel):
    business = models.OneToOneField("businesses.Business", on_delete=models.CASCADE, related_name="rental_terms")
    title = models.CharField(max_length=160, blank=True)
    clauses = models.JSONField(default=list, blank=True)
    footer = models.CharField(max_length=120, blank=True, default="دستخط / انگوٹھا")

    class Meta:
        verbose_name = "rental terms"

    def __str__(self):
        return self.title or "شرائط"


class RentalCustomer(TimeStampedModel):
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="rental_customers")
    name = models.CharField(max_length=160)
    phone = models.CharField(max_length=30, blank=True)
    cnic = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CarRental(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "On rent"
        COMPLETED = "completed", "Returned"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        BANK = "bank", "Bank Transfer"
        CARD = "card", "Card"
        JAZZCASH = "jazzcash", "JazzCash"
        EASYPAISA = "easypaisa", "Easypaisa"

    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="car_rentals")
    car = models.ForeignKey(RentalCar, on_delete=models.PROTECT, related_name="rentals")
    customer = models.ForeignKey(RentalCustomer, on_delete=models.PROTECT, related_name="rentals")
    start_date = models.DateField()
    end_date = models.DateField()
    daily_rate = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    deposit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    received_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    notes = models.TextField(blank=True)
    invoice_number = models.CharField(max_length=20, null=True, blank=True)
    customer_photo = models.TextField(blank=True)
    customer_signature = models.TextField(blank=True)
    dealer_signature = models.TextField(blank=True)
    guarantor_signature = models.TextField(blank=True)
    customer_thumbprint = models.TextField(blank=True)
    guarantor_thumbprint = models.TextField(blank=True)
    cnic_front = models.TextField(blank=True)
    cnic_back = models.TextField(blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    objects = BusinessScopedManager()

    class Meta:
        ordering = ["-start_date", "-created_at"]
        unique_together = ("business", "invoice_number")

    @property
    def days(self):
        if not self.start_date or not self.end_date:
            return 1
        return max(1, (self.end_date - self.start_date).days or 1)

    @property
    def balance(self):
        return max(0, self.total_amount - self.received_amount)

    @property
    def is_signed(self):
        return bool(self.customer_signature or self.dealer_signature or self.guarantor_signature)

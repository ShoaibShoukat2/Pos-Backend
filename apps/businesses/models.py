from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel


class BusinessType(models.TextChoices):
    GROCERY = "grocery", "Grocery"
    CLOTHING = "clothing", "Clothing"
    RESTAURANT = "restaurant", "Restaurant"
    PHARMACY = "pharmacy", "Pharmacy"
    ELECTRONICS = "electronics", "Electronics"
    GENERAL = "general", "General Retail"


class Business(TimeStampedModel):
    name = models.CharField(max_length=160)
    legal_name = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    website = models.URLField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=80, blank=True)
    country = models.CharField(max_length=80, default="Pakistan")
    postal_code = models.CharField(max_length=20, blank=True)
    tax_number = models.CharField(max_length=60, blank=True, help_text="NTN / GST / VAT")
    logo = models.ImageField(upload_to="logos/", blank=True, null=True)
    timezone = models.CharField(max_length=60, default="Asia/Karachi")
    date_format = models.CharField(max_length=20, default="DD/MM/YYYY")
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=7)
    business_type = models.CharField(
        max_length=30,
        choices=BusinessType.choices,
        default=BusinessType.GENERAL,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "businesses"

    def __str__(self):
        return self.name


class Branch(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=80, blank=True)
    is_head_office = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "code")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class Currency(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="currencies")
    code = models.CharField(max_length=8)
    name = models.CharField(max_length=60)
    symbol = models.CharField(max_length=8)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    exchange_rate = models.DecimalField(max_digits=14, decimal_places=6, default=1)
    is_base = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "code")
        verbose_name_plural = "currencies"
        ordering = ["-is_base", "code"]

    def __str__(self):
        return f"{self.code} {self.symbol}"


class TaxRate(TimeStampedModel):
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="tax_rates")
    name = models.CharField(max_length=80)
    code = models.CharField(max_length=20)
    rate = models.DecimalField(max_digits=6, decimal_places=3)
    is_inclusive = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "code")
        ordering = ["-is_default", "name"]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class InvoiceSettings(TimeStampedModel):
    class PaperSize(models.TextChoices):
        MM80 = "80mm", "80mm thermal"
        MM58 = "58mm", "58mm thermal"
        A4 = "A4", "A4"

    business = models.OneToOneField(
        Business,
        on_delete=models.CASCADE,
        related_name="invoice_settings",
    )
    prefix = models.CharField(max_length=12, default="INV")
    next_number = models.PositiveIntegerField(default=1)
    number_padding = models.PositiveSmallIntegerField(default=6)
    footer_note = models.CharField(max_length=255, blank=True, default="Thank you for your purchase")
    terms = models.TextField(blank=True)
    show_logo = models.BooleanField(default=True)
    show_tax_breakdown = models.BooleanField(default=True)
    show_cashier_name = models.BooleanField(default=True)
    paper_size = models.CharField(
        max_length=8,
        choices=PaperSize.choices,
        default=PaperSize.MM80,
    )

    def __str__(self):
        return f"Invoice settings · {self.business.name}"

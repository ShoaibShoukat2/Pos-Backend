from django.db import models

from apps.core.models import BusinessScopedManager, TimeStampedModel


class Category(TimeStampedModel):
    class Kind(models.TextChoices):
        PRODUCT = "product", "Product"
        SERVICE = "service", "Service"

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PRODUCT)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "name")
        verbose_name_plural = "categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Brand(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="brands",
    )
    name = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Unit(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="units",
    )
    name = models.CharField(max_length=60)
    short_code = models.CharField(max_length=12)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "short_code")
        ordering = ["name"]

    def __str__(self):
        return self.short_code


class Product(TimeStampedModel):
    class ItemKind(models.TextChoices):
        PRODUCT = "product", "Product"
        SERVICE = "service", "Service"

    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="products",
    )
    name = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    item_kind = models.CharField(max_length=20, choices=ItemKind.choices, default=ItemKind.PRODUCT)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    brand = models.ForeignKey(
        Brand,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name="products",
    )
    tax_rate = models.ForeignKey(
        "businesses.TaxRate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    sku = models.CharField(max_length=60)
    barcode = models.CharField(max_length=80, blank=True)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    min_stock = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    has_variants = models.BooleanField(default=False)
    track_stock = models.BooleanField(default=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    warranty_days = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "sku")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["business", "is_active"], name="prd_biz_active_idx"),
            models.Index(fields=["business", "name"], name="prd_biz_name_idx"),
            models.Index(fields=["business", "item_kind"], name="prd_biz_kind_idx"),
            models.Index(fields=["barcode"], name="prd_barcode_idx"),
        ]

    def __str__(self):
        return self.name


class ProductVariant(TimeStampedModel):
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="variants",
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    name = models.CharField(max_length=180, blank=True)
    sku = models.CharField(max_length=80)
    barcode = models.CharField(max_length=80, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    cost_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    min_stock = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    objects = BusinessScopedManager()

    class Meta:
        unique_together = ("business", "sku")
        ordering = ["product__name", "name", "sku"]
        indexes = [
            models.Index(fields=["business", "is_active"], name="var_biz_active_idx"),
            models.Index(fields=["barcode"], name="var_barcode_idx"),
            models.Index(fields=["product", "is_active"], name="var_prd_active_idx"),
        ]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.name:
            return self.name
        if self.attributes:
            return " / ".join(str(v) for v in self.attributes.values())
        return self.product.name

    def save(self, *args, **kwargs):
        if self.product_id and not self.business_id:
            self.business_id = self.product.business_id
        if not self.name and self.attributes:
            self.name = " / ".join(str(v) for v in self.attributes.values())
        if not self.name:
            self.name = self.product.name
        super().save(*args, **kwargs)

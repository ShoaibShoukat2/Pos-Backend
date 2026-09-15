from rest_framework import serializers

from apps.businesses.models import Branch, Business, BusinessType, Currency, InvoiceSettings, TaxRate
from apps.core.services import seed_electronics_catalog


class BusinessSerializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = (
            "id",
            "name",
            "legal_name",
            "email",
            "phone",
            "website",
            "address",
            "city",
            "state",
            "country",
            "postal_code",
            "tax_number",
            "logo",
            "timezone",
            "date_format",
            "fiscal_year_start_month",
            "business_type",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "is_active", "created_at", "updated_at")

    def update(self, instance, validated):
        previous_type = instance.business_type
        business = super().update(instance, validated)
        if business.business_type == BusinessType.ELECTRONICS and previous_type != BusinessType.ELECTRONICS:
            seed_electronics_catalog(business)
        return business


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = (
            "id",
            "name",
            "code",
            "phone",
            "email",
            "address",
            "city",
            "is_head_office",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_code(self, value):
        business = self.context["request"].user.business
        qs = Branch.objects.filter(business=business, code__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A branch with this code already exists.")
        return value.upper()


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = (
            "id",
            "code",
            "name",
            "symbol",
            "decimal_places",
            "exchange_rate",
            "is_base",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_code(self, value):
        return value.upper()


class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = (
            "id",
            "name",
            "code",
            "rate",
            "is_inclusive",
            "is_default",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_code(self, value):
        return value.upper()


class InvoiceSettingsSerializer(serializers.ModelSerializer):
    preview_number = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceSettings
        fields = (
            "id",
            "prefix",
            "next_number",
            "number_padding",
            "footer_note",
            "terms",
            "show_logo",
            "show_tax_breakdown",
            "show_cashier_name",
            "paper_size",
            "preview_number",
            "updated_at",
        )
        read_only_fields = ("id", "updated_at")

    def get_preview_number(self, obj):
        return f"{obj.prefix}-{str(obj.next_number).zfill(obj.number_padding)}"

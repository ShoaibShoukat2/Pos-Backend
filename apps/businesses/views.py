from django.db import transaction
from rest_framework import generics, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.businesses.models import Branch, Currency, InvoiceSettings, TaxRate
from apps.businesses.serializers import (
    BranchSerializer,
    BusinessSerializer,
    CurrencySerializer,
    InvoiceSettingsSerializer,
    TaxRateSerializer,
)
from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasPermission


class BusinessProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, HasPermission]
    serializer_class = BusinessSerializer

    @property
    def required_permission(self):
        if self.request.method in ("GET", "HEAD"):
            return "business.view"
        return "business.edit"

    def get_object(self):
        business = self.request.user.business
        if not business:
            raise ValidationError("User is not attached to a business.")
        return business


class BranchViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = BranchSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Branch.objects.all()
    search_fields = ("name", "code", "city")
    filterset_fields = ("is_active", "is_head_office")
    pagination_class = None

    @property
    def required_permission(self):
        return {
            "list": "branch.view",
            "retrieve": "branch.view",
            "create": "branch.create",
            "update": "branch.edit",
            "partial_update": "branch.edit",
            "destroy": "branch.delete",
        }.get(self.action, "branch.view")

    def perform_create(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_head_office"):
                Branch.objects.filter(business=self.request.user.business).update(is_head_office=False)
            super().perform_create(serializer)

    def perform_update(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_head_office"):
                Branch.objects.filter(business=self.request.user.business).exclude(
                    pk=serializer.instance.pk
                ).update(is_head_office=False)
            serializer.save()

    def perform_destroy(self, instance):
        if instance.is_head_office:
            raise ValidationError("Head office cannot be deleted. Assign another head office first.")
        if instance.assigned_users.exists():
            instance.is_active = False
            instance.save(update_fields=["is_active"])
            return
        instance.delete()


class CurrencyViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CurrencySerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "currency.manage"
    queryset = Currency.objects.all()
    pagination_class = None

    def perform_create(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_base"):
                Currency.objects.filter(business=self.request.user.business).update(is_base=False)
            super().perform_create(serializer)

    def perform_update(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_base"):
                Currency.objects.filter(business=self.request.user.business).exclude(
                    pk=serializer.instance.pk
                ).update(is_base=False)
            serializer.save()

    def perform_destroy(self, instance):
        if instance.is_base:
            raise ValidationError("Base currency cannot be deleted.")
        instance.delete()


class TaxRateViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = TaxRateSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "tax.manage"
    queryset = TaxRate.objects.all()
    pagination_class = None

    def perform_create(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_default"):
                TaxRate.objects.filter(business=self.request.user.business).update(is_default=False)
            super().perform_create(serializer)

    def perform_update(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_default"):
                TaxRate.objects.filter(business=self.request.user.business).exclude(
                    pk=serializer.instance.pk
                ).update(is_default=False)
            serializer.save()


class InvoiceSettingsView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "invoice_settings.manage"
    serializer_class = InvoiceSettingsSerializer

    def get_object(self):
        settings, _ = InvoiceSettings.objects.get_or_create(business=self.request.user.business)
        return settings

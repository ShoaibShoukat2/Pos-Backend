from django.db import transaction
from rest_framework import generics, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.businesses.models import Branch, Business, Currency, InvoiceSettings, TaxRate
from apps.businesses.serializers import (
    BranchSerializer,
    BusinessSerializer,
    CurrencySerializer,
    InvoiceSettingsSerializer,
    TaxRateSerializer,
)
from apps.catalog.models import ProductVariant
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


# ── Public Price Checker ──────────────────────────────────────────────────────

class PublicPriceCheckerInfoView(APIView):
    """Returns shop branding for a given slug — no auth required."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        try:
            business = Business.objects.get(price_checker_slug=slug, is_active=True)
        except Business.DoesNotExist:
            raise NotFound("Price checker not found.")
        if not business.price_checker_enabled:
            raise NotFound("Price checker is disabled for this shop.")

        logo_url = ""
        if business.logo:
            try:
                logo_url = request.build_absolute_uri(business.logo.url)
            except ValueError:
                logo_url = ""

        return Response({
            "name": business.name,
            "legal_name": business.legal_name,
            "city": business.city,
            "logo": logo_url,
            "primary_color": business.primary_color or "#1e293b",
            "accent_color": business.accent_color or "#6366f1",
        })


class PublicPriceCheckerSearchView(APIView):
    """Search products by barcode/SKU/name — no auth required."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, slug):
        try:
            business = Business.objects.get(price_checker_slug=slug, is_active=True)
        except Business.DoesNotExist:
            raise NotFound("Price checker not found.")
        if not business.price_checker_enabled:
            raise NotFound("Price checker is disabled for this shop.")

        q = (request.query_params.get("q") or "").strip()
        if not q:
            return Response({"results": []})

        from django.db.models import Q
        qs = ProductVariant.objects.filter(
            business=business,
            is_active=True,
            product__is_active=True,
        ).select_related("product__category").order_by("product__name", "name")[:1]

        # Exact barcode or SKU first
        exact = ProductVariant.objects.filter(
            business=business,
            is_active=True,
            product__is_active=True,
        ).filter(
            Q(barcode__iexact=q) | Q(sku__iexact=q) | Q(product__barcode__iexact=q)
        ).select_related("product__category").first()

        if exact:
            items = [exact]
        else:
            items = list(
                ProductVariant.objects.filter(
                    business=business,
                    is_active=True,
                    product__is_active=True,
                ).filter(
                    Q(sku__icontains=q)
                    | Q(barcode__icontains=q)
                    | Q(name__icontains=q)
                    | Q(product__name__icontains=q)
                ).select_related("product__category").order_by("product__name")[:8]
            )

        results = []
        for v in items:
            results.append({
                "id": str(v.id),
                "product": v.product.name,
                "variant": v.display_name,
                "sku": v.sku,
                "barcode": v.barcode or v.product.barcode,
                "category": v.product.category.name if v.product.category_id else "",
                "selling_price": f"{v.selling_price:.2f}",
                "item_kind": v.product.item_kind,
            })

        return Response({"results": results})

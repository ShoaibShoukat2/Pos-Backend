from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, F, Prefetch, Q, Sum, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.catalog.models import Brand, Category, Product, ProductVariant, Unit
from apps.catalog.serializers import (
    BrandSerializer,
    CategorySerializer,
    ProductListSerializer,
    ProductSerializer,
    ProductVariantSerializer,
    UnitSerializer,
    VariantListSerializer,
)
from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasPermission
ZERO_QTY = Value(Decimal("0"), output_field=DecimalField(max_digits=14, decimal_places=3))


class CategoryViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Category.objects.all()
    search_fields = ("name",)
    filterset_fields = ("is_active", "kind")
    pagination_class = None

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "product.view"
        return "category.manage"

    def get_queryset(self):
        return super().get_queryset().annotate(
            product_count=Count("products", filter=Q(products__item_kind=F("kind"))),
        )


class BrandViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = BrandSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Brand.objects.all()
    search_fields = ("name",)
    pagination_class = None

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "product.view"
        return "brand.manage"

    def get_queryset(self):
        return super().get_queryset().annotate(
            product_count=Count("products", filter=Q(products__item_kind=Product.ItemKind.PRODUCT)),
        )


class UnitViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = UnitSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Unit.objects.all()
    pagination_class = None

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "product.view"
        return "product.manage"


class ProductViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Product.objects.all()
    search_fields = ("name", "sku", "barcode", "variants__sku", "variants__barcode")
    filterset_fields = ("is_active", "category", "brand", "has_variants", "item_kind")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "product.view"
        return "product.manage"

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        return ProductSerializer

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("category", "brand", "unit", "tax_rate")
            .annotate(
                variant_count=Count("variants", distinct=True),
                total_stock=Coalesce(Sum("variants__stock_levels__quantity"), ZERO_QTY),
            )
            .order_by("name")
        )
        if self.action == "retrieve":
            return qs.prefetch_related(
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.annotate(
                        total_stock=Coalesce(Sum("stock_levels__quantity"), ZERO_QTY)
                    ).prefetch_related("stock_levels__branch"),
                )
            )
        if self.action == "list" and "item_kind" not in self.request.query_params:
            qs = qs.filter(item_kind=Product.ItemKind.PRODUCT)
        return qs

    def perform_destroy(self, instance):
        try:
            with transaction.atomic():
                instance.variants.all().delete()
                instance.delete()
        except ProtectedError:
            instance.is_active = False
            instance.save(update_fields=["is_active", "updated_at"])
            instance.variants.update(is_active=False)

    @action(detail=False, methods=["post"], url_path="seed-templates")
    def seed_templates(self, request):
        from apps.core.services import seed_electronics_catalog

        created = seed_electronics_catalog(request.user.business)
        return Response({"created": created})


class VariantViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = ProductVariantSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = ProductVariant.objects.all()
    search_fields = ("sku", "barcode", "name", "product__name")
    filterset_fields = ("product", "is_active")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve", "lookup"):
            return "product.view"
        return "product.manage"

    def get_serializer_class(self):
        if self.action == "list":
            return VariantListSerializer
        return ProductVariantSerializer

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("product")
            .annotate(total_stock=Coalesce(Sum("stock_levels__quantity"), ZERO_QTY))
        )
        if self.action == "retrieve":
            return qs.prefetch_related("stock_levels__branch")
        if self.action == "list" and "item_kind" not in self.request.query_params:
            qs = qs.filter(product__item_kind=Product.ItemKind.PRODUCT)
        return qs

    @action(detail=False, methods=["get"])
    def lookup(self, request):
        code = (request.query_params.get("barcode") or request.query_params.get("sku") or "").strip()
        if not code:
            return Response({"detail": "Provide barcode or sku."}, status=400)
        variant = self.get_queryset().filter(barcode__iexact=code).first()
        if not variant:
            variant = self.get_queryset().filter(sku__iexact=code).first()
        if not variant:
            return Response({"detail": "Variant not found."}, status=404)
        return Response(self.get_serializer(variant).data)

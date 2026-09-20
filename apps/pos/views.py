from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.businesses.serializers import BranchSerializer
from apps.catalog.models import ProductVariant
from apps.accounts.helpers import is_cashier_user
from apps.core.branch import accessible_branches, apply_branch_scope, resolve_branch
from apps.core.mixins import BusinessQuerysetMixin
from apps.core.pagination import StandardPagination
from apps.core.permissions import HasAnyPermission, HasPermission
from apps.customers.models import Customer
from apps.customers.serializers import CustomerSerializer
from apps.finance.models import CashSession
from apps.finance.serializers import CashSessionSerializer
from apps.inventory.models import StockLevel
from apps.pos.models import Sale, SaleReturn
from apps.pos.serializers import CheckoutSerializer, ReturnSerializer, SaleReturnSerializer, SaleSerializer, SyncSerializer
from apps.promotions.engine import active_promotions, loyalty_settings, tier_for
from apps.promotions.models import Coupon, MembershipTier
from apps.promotions.serializers import CouponSerializer, LoyaltySettingsSerializer, MembershipTierSerializer, PromotionSerializer

CATALOG_PRELOAD = 200
CUSTOMER_PRELOAD = 80


def _catalog_rows(variants, levels):
    catalog = []
    for variant in variants:
        product = variant.product
        catalog.append(
            {
                "id": str(variant.id),
                "product_id": str(product.id),
                "product": product.name,
                "variant": variant.display_name,
                "sku": variant.sku,
                "barcode": variant.barcode or product.barcode,
                "category": product.category.name if product.category_id else "",
                "category_id": str(product.category_id) if product.category_id else None,
                "selling_price": f"{variant.selling_price:.2f}",
                "cost_price": f"{variant.cost_price:.2f}",
                "track_stock": product.track_stock,
                "item_kind": product.item_kind,
                "duration_minutes": product.duration_minutes,
                "warranty_days": product.warranty_days,
                "qty": f"{levels.get(str(variant.id), 0):.3f}",
            }
        )
    return catalog


def _stock_map(business, branch=None):
    totals = {}
    qs = StockLevel.objects.filter(business=business).only("variant_id", "quantity")
    if branch:
        qs = qs.filter(branch=branch)
    for row in qs:
        key = str(row.variant_id)
        totals[key] = totals.get(key, Decimal("0")) + row.quantity
    return totals


class SaleViewSet(BusinessQuerysetMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SaleSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Sale.objects.all()
    filterset_fields = ("branch", "customer", "status")
    search_fields = ("number", "coupon_code", "customer__name")

    @property
    def required_permission(self):
        return "sale.view"

    def get_queryset(self):
        qs = (
            super()
            .get_queryset()
            .select_related("customer", "branch", "created_by")
            .prefetch_related("lines__variant__product", "payments")
        )
        user = self.request.user
        if is_cashier_user(user) and not user.is_owner:
            qs = qs.filter(created_by=user)
        return qs


class ReturnLookupView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("return.sale", "sale.create")

    def get(self, request):
        q = (request.query_params.get("q") or request.query_params.get("search") or request.query_params.get("number") or "").strip()
        if not q:
            return Response({"detail": "Enter a ticket number."}, status=400)
        qs = apply_branch_scope(
            Sale.objects.filter(business=request.user.business)
            .select_related("customer", "branch", "created_by")
            .prefetch_related("lines__variant__product", "payments"),
            request,
        )
        sale = qs.filter(number__iexact=q).first()
        if not sale:
            sale = qs.filter(number__icontains=q).order_by("-created_at").first()
        if not sale:
            return Response({"detail": "Ticket not found."}, status=404)
        return Response(SaleSerializer(sale).data)


class ReturnView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("return.sale", "sale.create")

    def get(self, request):
        qs = apply_branch_scope(
            SaleReturn.objects.filter(business=request.user.business)
            .select_related("sale", "sale__customer", "branch", "created_by")
            .prefetch_related("lines__variant__product", "sale__lines__variant__product", "sale__payments")
            .order_by("-created_at"),
            request,
        )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(SaleReturnSerializer(page, many=True).data)

    def post(self, request):
        ser = ReturnSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        row = ser.save()
        return Response(SaleReturnSerializer(row).data, status=201)


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "sale.create"

    def post(self, request):
        ser = CheckoutSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        sale = ser.save()
        return Response(SaleSerializer(sale).data, status=201)


class SyncView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("sale.create", "sync.manage")

    def post(self, request):
        ser = SyncSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        results = ser.save()
        return Response({"results": results})


class SnapshotView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("pos.access", "sale.create", "product.view")

    def get(self, request):
        business = request.user.business
        branch = resolve_branch(request, required=True)
        variant_qs = (
            ProductVariant.objects.filter(business=business, is_active=True, product__is_active=True)
            .select_related("product__category")
            .order_by("product__name", "name", "sku")
        )
        catalog_counts = variant_qs.aggregate(
            total=Count("id"),
            products=Count("id", filter=Q(product__item_kind="product")),
            services=Count("id", filter=Q(product__item_kind="service")),
        )
        catalog_total = catalog_counts["total"] or 0
        variants = list(variant_qs[:CATALOG_PRELOAD])
        levels = _stock_map(business)
        customers = Customer.objects.filter(business=business, is_active=True).order_by("name")
        customer_total = customers.count()
        customer_rows = []
        for c in customers[:CUSTOMER_PRELOAD]:
            tier = tier_for(c)
            customer_rows.append(
                {
                    **CustomerSerializer(c).data,
                    "membership_name": tier.name if tier else "",
                    "membership_discount": f"{tier.discount_percent:.2f}" if tier else "0.00",
                }
            )
        coupons = Coupon.objects.filter(business=business, is_active=True)
        money = DecimalField(max_digits=18, decimal_places=2)
        stock_value = (
            StockLevel.objects.filter(
                business=business,
                variant__product__item_kind="product",
                variant__product__track_stock=True,
            ).aggregate(
                total=Sum(ExpressionWrapper(F("quantity") * F("variant__cost_price"), output_field=money))
            )["total"]
            or 0
        )
        open_shift = CashSession.objects.filter(branch=branch, status=CashSession.Status.OPEN).first()
        return Response(
            {
                "branch": BranchSerializer(branch).data,
                "branches": BranchSerializer(accessible_branches(request.user), many=True).data,
                "catalog": _catalog_rows(variants, levels),
                "catalog_truncated": catalog_total > CATALOG_PRELOAD,
                "catalog_total": catalog_total,
                "catalog_products": catalog_counts["products"] or 0,
                "catalog_services": catalog_counts["services"] or 0,
                "customers": customer_rows,
                "customer_truncated": customer_total > CUSTOMER_PRELOAD,
                "coupons": CouponSerializer(coupons, many=True).data,
                "promotions": PromotionSerializer(active_promotions(business), many=True).data,
                "tiers": MembershipTierSerializer(
                    MembershipTier.objects.filter(business=business, is_active=True), many=True
                ).data,
                "loyalty": LoyaltySettingsSerializer(loyalty_settings(business)).data,
                "open_shift": CashSessionSerializer(open_shift).data if open_shift else None,
                "stock_value": str(stock_value),
            }
        )


class CatalogSearchView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("pos.access", "sale.create", "product.view")

    def get(self, request):
        business = request.user.business
        branch = resolve_branch(request, required=True)
        q = (request.query_params.get("search") or request.query_params.get("q") or "").strip()
        qs = (
            ProductVariant.objects.filter(business=business, is_active=True, product__is_active=True)
            .select_related("product__category")
            .order_by("product__name", "name", "sku")
        )
        if q:
            exact = qs.filter(Q(barcode__iexact=q) | Q(sku__iexact=q) | Q(product__barcode__iexact=q))
            qs = exact if exact.exists() else qs.filter(
                Q(sku__icontains=q)
                | Q(barcode__icontains=q)
                | Q(name__icontains=q)
                | Q(product__name__icontains=q)
                | Q(product__barcode__icontains=q)
            )
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        levels = _stock_map(business)
        return paginator.get_paginated_response(_catalog_rows(page, levels))

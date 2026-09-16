from django.contrib.auth import get_user_model
from django.db.models import Count
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.models import Permission, Role
from apps.accounts.helpers import is_cashier_user
from apps.accounts.serializers import (
    CashierLoginSerializer,
    ChangePasswordSerializer,
    CreateCashierSerializer,
    LoginSerializer,
    MeSerializer,
    OwnerLoginSerializer,
    PermissionSerializer,
    PlatformLoginSerializer,
    RegisterSerializer,
    RoleSerializer,
    UserSerializer,
)
from apps.businesses.serializers import BranchSerializer
from apps.core.branch import accessible_branches
from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasPermission

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    permission_classes = [AllowAny]
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        user.refresh_from_db()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": MeSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = LoginSerializer


class OwnerLoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = OwnerLoginSerializer


class PlatformLoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = PlatformLoginSerializer


class CashierLoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = CashierLoginSerializer


class CashierCreateView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "user.create"
    serializer_class = CreateCashierSerializer

    def create(self, request, *args, **kwargs):
        if not request.user.is_owner and not request.user.has_module_permission("user.create"):
            return Response({"detail": "Only a business owner can add cashiers."}, status=status.HTTP_403_FORBIDDEN)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        user.refresh_from_db()
        return Response(MeSerializer(user).data, status=status.HTTP_201_CREATED)


class CashierListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "user.view"
    serializer_class = UserSerializer

    def get_queryset(self):
        return User.objects.filter(
            business=self.request.user.business,
            is_owner=False,
            role__name="Cashier",
        ).select_related("role", "default_branch")


class CashierOverviewView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from django.db.models import Count, F, Sum
        from django.utils import timezone

        from apps.finance.models import CashSession
        from apps.pos.models import OPEN_SALE_STATUSES, Sale, SaleLine
        from apps.reports.services import money

        user = request.user
        if not is_cashier_user(user) and not user.is_owner:
            return Response({"detail": "Cashier access only."}, status=status.HTTP_403_FORBIDDEN)
        start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        sales = Sale.objects.filter(
            business=user.business,
            created_by=user,
            status__in=OPEN_SALE_STATUSES,
            created_at__gte=start,
        )
        if user.default_branch_id:
            shift = (
                CashSession.objects.filter(
                    business=user.business,
                    branch_id=user.default_branch_id,
                    status=CashSession.Status.OPEN,
                )
                .select_related("branch")
                .first()
            )
        else:
            shift = (
                CashSession.objects.filter(business=user.business, status=CashSession.Status.OPEN, opened_by=user)
                .select_related("branch")
                .first()
            )
        recent = list(
            sales.select_related("customer", "branch")
            .prefetch_related("lines__variant__product")
            .order_by("-created_at")[:12]
        )
        sold = list(
            SaleLine.objects.filter(sale__in=sales)
            .values("variant__product__name", "variant__sku")
            .annotate(qty=Sum(F("quantity") - F("returned_qty")), revenue=Sum(F("line_total") - F("returned_amount")), tickets=Count("sale", distinct=True))
            .order_by("-qty")[:10]
        )
        totals = sales.aggregate(total=Sum("net_total"), orders=Count("id"))
        return Response(
            {
                "cashier_name": user.full_name,
                "business_name": user.business.name if user.business_id else "",
                "branch_name": user.default_branch.name if user.default_branch_id else "",
                "today_sales": money(totals["total"]),
                "orders": totals["orders"] or 0,
                "open_shift": (
                    {
                        "id": str(shift.id),
                        "number": shift.number,
                        "branch_name": shift.branch.name,
                        "expected_cash": money(shift.expected_cash),
                        "sales_cash": money(shift.sales_cash),
                    }
                    if shift
                    else None
                ),
                "sold_products": [
                    {
                        "product": row["variant__product__name"],
                        "sku": row["variant__sku"] or "",
                        "qty": f"{row['qty']:.3f}",
                        "revenue": money(row["revenue"]),
                        "tickets": row["tickets"],
                    }
                    for row in sold
                ],
                "recent_sales": [
                    {
                        "id": str(sale.id),
                        "number": sale.number,
                        "total": money(sale.net_total),
                        "status": sale.status,
                        "customer_name": sale.customer.name if sale.customer_id else "Walk-in",
                        "branch_name": sale.branch.name,
                        "payment_method": sale.payment_method,
                        "created_at": sale.created_at.isoformat(),
                        "lines": [
                            {
                                "product": line.variant.product.name,
                                "sku": line.variant.sku,
                                "qty": f"{line.quantity:.3f}",
                                "total": money(line.line_total),
                            }
                            for line in sale.lines.all()
                        ],
                    }
                    for sale in recent
                ],
            }
        )


class MeView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user


class MyBranchesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BranchSerializer
    pagination_class = None

    def get_queryset(self):
        return accessible_branches(self.request.user)


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response({"detail": "Password updated."})


class PermissionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "role.view"
    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()
    pagination_class = None


class RoleViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Role.objects.all()
    search_fields = ("name",)
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().annotate(user_count=Count("users")).prefetch_related("permissions")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "role.view"
        return "role.manage"

    def perform_destroy(self, instance):
        if instance.is_system:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("System roles cannot be deleted.")
        instance.delete()


class UserViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = User.objects.select_related("role", "default_branch").prefetch_related("branches")
    search_fields = ("email", "first_name", "last_name", "phone")
    filterset_fields = ("is_active", "role")

    @property
    def required_permission(self):
        mapping = {
            "list": "user.view",
            "retrieve": "user.view",
            "create": "user.create",
            "update": "user.edit",
            "partial_update": "user.edit",
            "destroy": "user.delete",
            "activate": "user.edit",
        }
        return mapping.get(self.action, "user.view")

    def perform_destroy(self, instance):
        from rest_framework.exceptions import ValidationError

        if instance.is_owner:
            raise ValidationError("The business owner cannot be deleted.")
        if instance.pk == self.request.user.pk:
            raise ValidationError("You cannot delete your own account.")
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response(self.get_serializer(user).data)

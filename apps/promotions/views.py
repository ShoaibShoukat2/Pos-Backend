from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasPermission
from apps.promotions.engine import loyalty_settings
from apps.promotions.models import Coupon, MembershipTier, Promotion
from apps.promotions.serializers import (
    CouponSerializer,
    LoyaltySettingsSerializer,
    MembershipTierSerializer,
    PromotionSerializer,
)


class CouponViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CouponSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Coupon.objects.all()
    pagination_class = None
    search_fields = ("code",)

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "discount.manage"
        return "discount.manage"


class PromotionViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = PromotionSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Promotion.objects.all()
    pagination_class = None

    @property
    def required_permission(self):
        return "discount.manage"

    def get_queryset(self):
        return super().get_queryset().select_related("product", "category", "variant")


class MembershipTierViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = MembershipTierSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = MembershipTier.objects.all()
    pagination_class = None

    @property
    def required_permission(self):
        return "loyalty.manage"


class LoyaltySettingsView(APIView):
    permission_classes = [IsAuthenticated, HasPermission]
    required_permission = "loyalty.manage"

    def get(self, request):
        return Response(LoyaltySettingsSerializer(loyalty_settings(request.user.business)).data)

    def put(self, request):
        settings = loyalty_settings(request.user.business)
        ser = LoyaltySettingsSerializer(settings, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    def patch(self, request):
        return self.put(request)

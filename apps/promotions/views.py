from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasPermission
from apps.promotions.models import Promotion
from apps.promotions.serializers import PromotionSerializer


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

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.businesses.subscription import force_delete_business, renew_subscription, shift_subscription, stop_subscription
from apps.core.permissions import IsPlatformAdmin
from apps.platform.serializers import PlatformBusinessSerializer, PlatformUserSerializer
from apps.platform.services import annotated_businesses, platform_overview


class PlatformOverviewView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    def get(self, request):
        period = request.query_params.get("period") or "month"
        if period not in {"today", "week", "month"}:
            period = "month"
        return Response(platform_overview(period))


class PlatformBusinessViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PlatformBusinessSerializer
    queryset = annotated_businesses()
    search_fields = ("name", "legal_name", "email", "phone", "city")
    filterset_fields = ("is_active", "business_type")
    ordering_fields = ("created_at", "name")

    def get_queryset(self):
        return annotated_businesses()

    def create(self, request, *args, **kwargs):
        return self.http_method_not_allowed(request)

    def perform_destroy(self, instance):
        force_delete_business(instance)

    @action(detail=True, methods=["post"])
    def subscription(self, request, pk=None):
        business = self.get_object()
        kind = str(request.data.get("action") or "").strip()
        if kind == "stop":
            stop_subscription(business)
        elif kind == "activate":
            renew_subscription(business)
        elif kind == "shift":
            try:
                days = int(request.data.get("days"))
            except (TypeError, ValueError):
                raise ValidationError({"days": "Enter a whole number of days."}) from None
            if days == 0 or days < -3650 or days > 3650:
                raise ValidationError({"days": "Use between -3650 and 3650 days, and not zero."})
            shift_subscription(business, days)
        else:
            raise ValidationError({"action": "Use stop, activate, or shift."})
        fresh = self.get_queryset().get(pk=business.pk)
        return Response(self.get_serializer(fresh).data, status=status.HTTP_200_OK)


class PlatformUserViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "patch", "head", "options"]
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PlatformUserSerializer
    search_fields = ("email", "first_name", "last_name", "phone")
    filterset_fields = ("is_active", "is_owner", "business")
    ordering_fields = ("date_joined", "email", "last_login")

    def get_queryset(self):
        return User.objects.filter(is_platform_admin=False).select_related("business", "role")

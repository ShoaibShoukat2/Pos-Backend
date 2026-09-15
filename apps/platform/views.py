from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
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
    http_method_names = ["get", "patch", "head", "options"]
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PlatformBusinessSerializer
    queryset = annotated_businesses()
    search_fields = ("name", "legal_name", "email", "phone", "city")
    filterset_fields = ("is_active", "business_type")
    ordering_fields = ("created_at", "name")

    def get_queryset(self):
        return annotated_businesses()


class PlatformUserViewSet(viewsets.ModelViewSet):
    http_method_names = ["get", "patch", "head", "options"]
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PlatformUserSerializer
    search_fields = ("email", "first_name", "last_name", "phone")
    filterset_fields = ("is_active", "is_owner", "business")
    ordering_fields = ("date_joined", "email", "last_login")

    def get_queryset(self):
        return User.objects.filter(is_platform_admin=False).select_related("business", "role")

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.mixins import BusinessQuerysetMixin
from apps.core.permissions import HasPermission
from apps.customers.models import Customer, CustomerLedgerEntry, CustomerPayment, CustomerSale
from apps.customers.serializers import (
    CustomerLedgerSerializer,
    CustomerPaymentSerializer,
    CustomerSaleSerializer,
    CustomerSerializer,
)


class CustomerViewSet(BusinessQuerysetMixin, viewsets.ModelViewSet):
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = Customer.objects.all()
    search_fields = ("name", "phone", "email", "city")
    filterset_fields = ("is_active",)

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve", "ledger"):
            return "customer.view"
        return "customer.manage"

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])

    @action(detail=True, methods=["get"])
    def ledger(self, request, pk=None):
        entries = CustomerLedgerEntry.objects.filter(
            business=request.user.business, customer=self.get_object()
        )
        page = self.paginate_queryset(entries)
        if page is not None:
            return self.get_paginated_response(CustomerLedgerSerializer(page, many=True).data)
        return Response(CustomerLedgerSerializer(entries, many=True).data)


class CustomerSaleViewSet(
    BusinessQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CustomerSaleSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = CustomerSale.objects.all()
    filterset_fields = ("customer", "branch")

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "customer.view"
        return "customer.credit"

    def get_queryset(self):
        return super().get_queryset().select_related("customer", "branch")


class CustomerPaymentViewSet(
    BusinessQuerysetMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = CustomerPaymentSerializer
    permission_classes = [IsAuthenticated, HasPermission]
    queryset = CustomerPayment.objects.all()
    filterset_fields = ("customer",)

    @property
    def required_permission(self):
        if self.action in ("list", "retrieve"):
            return "customer.view"
        return "customer.credit"

    def get_queryset(self):
        return super().get_queryset().select_related("customer", "branch")

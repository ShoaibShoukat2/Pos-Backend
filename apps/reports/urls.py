from django.urls import path

from apps.reports.views import (
    DashboardReportView,
    FinancialReportView,
    InventoryReportView,
    OwnerOverviewView,
    SalesReportView,
)

urlpatterns = [
    path("reports/dashboard/", DashboardReportView.as_view(), name="report-dashboard"),
    path("reports/owner/", OwnerOverviewView.as_view(), name="report-owner"),
    path("reports/sales/", SalesReportView.as_view(), name="report-sales"),
    path("reports/inventory/", InventoryReportView.as_view(), name="report-inventory"),
    path("reports/financial/", FinancialReportView.as_view(), name="report-financial"),
]

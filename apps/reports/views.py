from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import HasAnyPermission
from apps.reports.period import period_bounds
from apps.reports.services import dashboard, financial_report, inventory_report, owner_overview, sales_report


def report_scope(request):
    start, end, period = period_bounds(request, default="today")
    # Parse optional branch filter: ?branch=uuid or ?branch=uuid1,uuid2
    branch_param = (request.query_params.get("branch") or "").strip()
    branch_ids = [b.strip() for b in branch_param.split(",") if b.strip()] if branch_param else None
    return start, end, period, branch_ids


class DashboardReportView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = (
        "report.sales",
        "report.profit",
        "report.inventory",
        "report.cashier",
        "sale.view",
    )

    def get(self, request):
        start, end, period, branch_ids = report_scope(request)
        return Response(dashboard(request.user.business, start, end, period, branch_ids))


class OwnerOverviewView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = (
        "report.sales",
        "report.profit",
        "report.inventory",
        "sale.view",
        "user.view",
    )

    def get(self, request):
        start, end, period, branch_ids = report_scope(request)
        return Response(owner_overview(request.user.business, start, end, period, branch_ids))


class SalesReportView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("report.sales", "report.cashier")

    def get(self, request):
        start, end, period = period_bounds(request, default="month")
        _, _, _, branch_ids = report_scope(request)
        return Response(sales_report(request.user.business, start, end, period, branch_ids))


class InventoryReportView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("report.inventory", "stock.view")

    def get(self, request):
        start, end, period = period_bounds(request, default="month")
        _, _, _, branch_ids = report_scope(request)
        return Response(inventory_report(request.user.business, start, end, branch_ids))


class FinancialReportView(APIView):
    permission_classes = [IsAuthenticated, HasAnyPermission]
    required_any_permissions = ("report.profit", "ledger.view")

    def get(self, request):
        start, end, period = period_bounds(request, default="month")
        _, _, _, branch_ids = report_scope(request)
        return Response(financial_report(request.user.business, start, end, period, branch_ids))

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.hostel.views import (
    AuditViewSet,
    BedViewSet,
    BillingGenerateView,
    BillingLateFeeView,
    BranchViewSet,
    CustomerViewSet,
    DocumentViewSet,
    EmployeeViewSet,
    ExpenseViewSet,
    HostelDashboardView,
    HostelMeView,
    HostelReportView,
    HostelSearchView,
    HostelSettingsView,
    InviteAcceptView,
    MaintenanceViewSet,
    MonthlyViewSet,
    NotificationViewSet,
    PaymentViewSet,
    ReservationViewSet,
    RoomViewSet,
)

router = DefaultRouter()
router.register("branches", BranchViewSet, basename="hostel-branch")
router.register("rooms", RoomViewSet, basename="hostel-room")
router.register("beds", BedViewSet, basename="hostel-bed")
router.register("customers", CustomerViewSet, basename="hostel-customer")
router.register("reservations", ReservationViewSet, basename="hostel-reservation")
router.register("payments", PaymentViewSet, basename="hostel-payment")
router.register("monthly", MonthlyViewSet, basename="hostel-monthly")
router.register("expenses", ExpenseViewSet, basename="hostel-expense")
router.register("maintenance", MaintenanceViewSet, basename="hostel-maintenance")
router.register("employees", EmployeeViewSet, basename="hostel-employee")
router.register("documents", DocumentViewSet, basename="hostel-document")
router.register("notifications", NotificationViewSet, basename="hostel-notification")
router.register("audit", AuditViewSet, basename="hostel-audit")

urlpatterns = [
    path("hostel/me/", HostelMeView.as_view(), name="hostel-me"),
    path("hostel/dashboard/", HostelDashboardView.as_view(), name="hostel-dashboard"),
    path("hostel/search/", HostelSearchView.as_view(), name="hostel-search"),
    path("hostel/reports/", HostelReportView.as_view(), name="hostel-report"),
    path("hostel/settings/", HostelSettingsView.as_view(), name="hostel-settings"),
    path("hostel/billing/generate/", BillingGenerateView.as_view(), name="hostel-billing"),
    path("hostel/billing/late-fees/", BillingLateFeeView.as_view(), name="hostel-late-fees"),
    path("hostel/invite/", InviteAcceptView.as_view(), name="hostel-invite"),
    path("hostel/", include(router.urls)),
]

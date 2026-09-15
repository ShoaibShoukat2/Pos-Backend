from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.finance.views import (
    CashSessionViewSet,
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    FinanceSummaryView,
)

router = DefaultRouter()
router.register("expense-categories", ExpenseCategoryViewSet, basename="expense-category")
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("cash-sessions", CashSessionViewSet, basename="cash-session")

urlpatterns = [
    path("finance/summary/", FinanceSummaryView.as_view(), name="finance-summary"),
    path("", include(router.urls)),
]

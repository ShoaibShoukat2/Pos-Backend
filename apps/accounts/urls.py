from django.urls import path

from apps.accounts.views import CashierOverviewView, ChangePasswordView, MeView, MyBranchesView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("me/", MeView.as_view(), name="me"),
    path("branches/", MyBranchesView.as_view(), name="my-branches"),
    path("change-password/", ChangePasswordView.as_view(), name="change-password"),
    path("cashier/overview/", CashierOverviewView.as_view(), name="cashier-overview"),
]

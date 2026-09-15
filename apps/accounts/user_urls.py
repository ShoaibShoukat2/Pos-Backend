from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.accounts.views import CashierCreateView, CashierListView, PermissionListView, RoleViewSet, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("roles", RoleViewSet, basename="role")

urlpatterns = [
    path("permissions/", PermissionListView.as_view(), name="permissions"),
    path("cashiers/", CashierListView.as_view(), name="cashiers"),
    path("cashiers/create/", CashierCreateView.as_view(), name="cashier-create"),
    path("", include(router.urls)),
]

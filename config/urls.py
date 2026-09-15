from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import CashierLoginView, LoginView, OwnerLoginView, PlatformLoginView
from apps.core.views import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/auth/login/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/auth/owner/login/", OwnerLoginView.as_view(), name="owner_token_obtain_pair"),
    path("api/auth/platform/login/", PlatformLoginView.as_view(), name="platform_token_obtain_pair"),
    path("api/auth/cashier/login/", CashierLoginView.as_view(), name="cashier_token_obtain_pair"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/auth/", include("apps.accounts.urls")),
    path("api/", include("apps.businesses.urls")),
    path("api/", include("apps.accounts.user_urls")),
    path("api/", include("apps.catalog.urls")),
    path("api/", include("apps.inventory.urls")),
    path("api/", include("apps.purchases.urls")),
    path("api/", include("apps.finance.urls")),
    path("api/", include("apps.customers.urls")),
    path("api/", include("apps.reports.urls")),
    path("api/", include("apps.promotions.urls")),
    path("api/", include("apps.pos.urls")),
    path("api/platform/", include("apps.platform.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

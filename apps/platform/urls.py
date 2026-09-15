from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.platform.views import PlatformBusinessViewSet, PlatformOverviewView, PlatformUserViewSet

router = DefaultRouter()
router.register("businesses", PlatformBusinessViewSet, basename="platform-business")
router.register("users", PlatformUserViewSet, basename="platform-user")

urlpatterns = [
    path("overview/", PlatformOverviewView.as_view(), name="platform-overview"),
    path("", include(router.urls)),
]

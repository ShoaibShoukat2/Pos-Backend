from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.promotions.views import PromotionViewSet

router = DefaultRouter()
router.register("promotions", PromotionViewSet, basename="promotion")

urlpatterns = [
    path("", include(router.urls)),
]

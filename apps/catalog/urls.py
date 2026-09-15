from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.catalog.views import BrandViewSet, CategoryViewSet, ProductViewSet, UnitViewSet, VariantViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("units", UnitViewSet, basename="unit")
router.register("products", ProductViewSet, basename="product")
router.register("variants", VariantViewSet, basename="variant")

urlpatterns = [path("", include(router.urls))]

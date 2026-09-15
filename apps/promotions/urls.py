from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.promotions.views import CouponViewSet, LoyaltySettingsView, MembershipTierViewSet, PromotionViewSet

router = DefaultRouter()
router.register("coupons", CouponViewSet, basename="coupon")
router.register("promotions", PromotionViewSet, basename="promotion")
router.register("membership-tiers", MembershipTierViewSet, basename="membership-tier")

urlpatterns = [
    path("loyalty-settings/", LoyaltySettingsView.as_view(), name="loyalty-settings"),
    path("", include(router.urls)),
]

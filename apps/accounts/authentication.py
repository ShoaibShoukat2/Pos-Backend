from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.businesses.subscription import EXPIRED_MESSAGE, subscription_expired


class SubscriptionJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if getattr(user, "is_platform_admin", False) or not getattr(user, "business_id", None):
            return user
        if subscription_expired(user.business):
            raise AuthenticationFailed(EXPIRED_MESSAGE, code="subscription_expired")
        return user

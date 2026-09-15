from rest_framework.permissions import BasePermission


class HasPermission(BasePermission):
    """
    DRF permission that checks a single catalog codename.

    Usage:
        permission_classes = [IsAuthenticated, HasPermission]
        required_permission = "branch.create"
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        required = getattr(view, "required_permission", None)
        if not required:
            return True
        return user.has_module_permission(required)


class IsPlatformAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, "is_platform_admin", False)
        )


class HasAnyPermission(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        required = getattr(view, "required_any_permissions", None)
        if not required:
            return True
        return any(user.has_module_permission(code) for code in required)

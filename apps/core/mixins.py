from rest_framework.exceptions import PermissionDenied

from apps.core.branch import apply_branch_scope


class BusinessQuerysetMixin:
    """Scopes queryset and create() to the authenticated user's business (and branch)."""

    def get_queryset(self):
        qs = super().get_queryset()
        business = getattr(self.request.user, "business", None)
        if not business:
            raise PermissionDenied("User is not attached to a business.")
        qs = qs.filter(business=business)
        return apply_branch_scope(qs, self.request)

    def perform_create(self, serializer):
        business = self.request.user.business
        if not business:
            raise PermissionDenied("User is not attached to a business.")
        serializer.save(business=business)

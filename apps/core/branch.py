from rest_framework.exceptions import ValidationError

from apps.businesses.models import Branch


def shop_branch(business):
    """Single shop location used for stock, sales and cash. Branch UI is not exposed."""
    if not business:
        return None
    return (
        Branch.objects.filter(business=business, is_head_office=True, is_active=True).first()
        or Branch.objects.filter(business=business, is_active=True).first()
        or Branch.objects.filter(business=business).first()
    )


def can_see_all_branches(user) -> bool:
    return bool(user and user.is_authenticated)


def accessible_branches(user):
    if not user or not getattr(user, "business_id", None):
        return Branch.objects.none()
    return Branch.objects.filter(business=user.business)


def accessible_branch_ids(user):
    return list(accessible_branches(user).values_list("id", flat=True))


def peek_branch_id(request):
    return None


def resolve_branch(request, required=False):
    branch = shop_branch(getattr(request.user, "business", None))
    if required and not branch:
        raise ValidationError({"branch": "Shop is not set up."})
    return branch


def apply_branch_scope(qs, request):
    return qs

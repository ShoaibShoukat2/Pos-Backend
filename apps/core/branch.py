from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.businesses.models import Branch


def can_see_all_branches(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if user.is_owner or user.is_superuser:
        return True
    return user.has_module_permission("branch.view") or user.has_module_permission("branch.reports")


def accessible_branches(user):
    qs = Branch.objects.filter(business=user.business)
    if can_see_all_branches(user):
        return qs
    ids = set(user.branches.values_list("id", flat=True))
    if user.default_branch_id:
        ids.add(user.default_branch_id)
    return qs.filter(id__in=ids)


def accessible_branch_ids(user):
    return list(accessible_branches(user).values_list("id", flat=True))


def peek_branch_id(request):
    return request.headers.get("X-Branch-Id") or request.query_params.get("branch") or None


def resolve_branch(request, required=False):
    raw = peek_branch_id(request)
    allowed = accessible_branches(request.user)
    if raw:
        branch = allowed.filter(pk=raw).first()
        if not branch:
            raise PermissionDenied("You cannot access this branch.")
        return branch
    if not can_see_all_branches(request.user):
        branch = allowed.first()
        if branch:
            return branch
    if required:
        raise ValidationError({"branch": "Branch is required."})
    return None


def apply_branch_scope(qs, request):
    """Limit rows to the selected branch, or to the user's assigned branches."""
    model = qs.model
    selected = peek_branch_id(request)
    ids = None if can_see_all_branches(request.user) else accessible_branch_ids(request.user)

    if model._meta.label == "accounts.User":
        from django.db.models import Q

        if selected:
            return qs.filter(Q(branches__id=selected) | Q(default_branch_id=selected)).distinct()
        if ids is not None:
            return qs.filter(Q(branches__id__in=ids) | Q(default_branch_id__in=ids) | Q(is_owner=True)).distinct()
        return qs

    if any(f.name == "branch" for f in model._meta.fields):
        if selected:
            return qs.filter(branch_id=selected)
        if ids is not None:
            return qs.filter(branch_id__in=ids)
        return qs

    if model._meta.label == "inventory.StockTransfer":
        from django.db.models import Q

        if selected:
            return qs.filter(Q(from_branch_id=selected) | Q(to_branch_id=selected))
        if ids is not None:
            return qs.filter(Q(from_branch_id__in=ids) | Q(to_branch_id__in=ids))
    return qs

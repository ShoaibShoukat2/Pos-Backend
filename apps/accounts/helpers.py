def is_cashier_user(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_owner", False) or getattr(user, "is_platform_admin", False):
        return False
    role_name = getattr(getattr(user, "role", None), "name", "") or ""
    if role_name.lower() == "cashier":
        return True
    if user.has_module_permission("pos.access") and not user.has_module_permission("report.sales"):
        return True
    return False


def cashier_role_for(business):
    from apps.accounts.models import Role
    from apps.core.services import ensure_permission_rows
    from apps.core.catalog import ROLE_TEMPLATES

    permissions = ensure_permission_rows()
    role, _ = Role.objects.get_or_create(
        business=business,
        name="Cashier",
        defaults={"is_system": True, "description": "Default Cashier role"},
    )
    codes = ROLE_TEMPLATES.get("Cashier", [])
    role.permissions.set([permissions[c] for c in codes if c in permissions])
    return role

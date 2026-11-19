from rest_framework.exceptions import PermissionDenied

from apps.hostel.models import HostelEmployee


OWNER_ONLY = {
    "branches.manage",
    "payments.void",
    "reports.owner",
    "settings.manage",
    "staff.permissions",
}

MANAGER_DEFAULT = [
    "rooms.manage",
    "seats.manage",
    "customers.manage",
    "reservations.manage",
    "stays.manage",
    "payments.collect",
    "expenses.submit",
    "expenses.approve",
    "maintenance.submit",
    "maintenance.manage",
    "reports.branch",
    "documents.manage",
]

EMPLOYEE_DEFAULT = [
    "customers.manage",
    "reservations.manage",
    "stays.manage",
    "payments.collect",
    "expenses.submit",
    "maintenance.submit",
    "documents.manage",
]


def is_active_hostel_staff(user) -> bool:
    if not getattr(user, "business_id", None) or getattr(user, "is_owner", False):
        return False
    if getattr(user.business, "business_type", "") != "hostel":
        return False
    return HostelEmployee.objects.filter(
        user=user,
        business_id=user.business_id,
        status=HostelEmployee.Status.ACTIVE,
        is_deleted=False,
    ).exists()


def actor_context(user):
    if not user or not user.is_authenticated or not getattr(user, "business_id", None):
        raise PermissionDenied("Sign in to the hostel workspace.")
    if user.business.business_type != "hostel":
        raise PermissionDenied("Hostel workspace is not enabled for this business.")
    if user.is_owner:
        return {"role": "owner", "branch_id": None, "employee": None, "user": user, "business": user.business}
    employee = (
        HostelEmployee.objects.select_related("branch")
        .filter(user=user, business_id=user.business_id, is_deleted=False)
        .first()
    )
    if employee is None or employee.status != HostelEmployee.Status.ACTIVE:
        raise PermissionDenied("This staff account is not active.")
    return {
        "role": employee.role,
        "branch_id": employee.branch_id,
        "employee": employee,
        "user": user,
        "business": user.business,
    }


def permission_codes(actor) -> set[str]:
    if actor["role"] == "owner":
        return {
            *OWNER_ONLY,
            *MANAGER_DEFAULT,
            *EMPLOYEE_DEFAULT,
            "staff.manage",
        }
    employee = actor["employee"]
    if employee.role == HostelEmployee.Role.MANAGER:
        return set(codes_for_employee(employee))
    return set(employee.permissions.values_list("codename", flat=True))


def has_perm(actor, code: str) -> bool:
    if actor["role"] == "owner":
        return True
    return code in permission_codes(actor)


def ensure_perm(actor, code: str):
    if not has_perm(actor, code):
        raise PermissionDenied("You do not have permission for this action.")


def codes_for_employee(employee) -> list[str]:
    if employee.role == HostelEmployee.Role.MANAGER:
        codes = list(MANAGER_DEFAULT)
        codes.append("staff.manage")
        return codes
    codes = list(EMPLOYEE_DEFAULT)
    if employee.can_view_reports:
        codes.append("reports.branch")
    return [code for code in codes if code not in OWNER_ONLY]

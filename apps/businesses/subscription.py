from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

EXPIRED_MESSAGE = "Your subscription has expired. Ask the administrator to activate it again."
MONTH_DAYS = 30


def subscription_expired(business) -> bool:
    if business is None:
        return False
    if not business.is_active:
        return True
    end = business.subscription_ends_on
    return bool(end and end < timezone.localdate())


def stop_subscription(business):
    business.is_active = False
    business.save(update_fields=["is_active", "updated_at"])


def renew_subscription(business, days=MONTH_DAYS):
    business.is_active = True
    business.subscription_ends_on = timezone.localdate() + timedelta(days=days)
    business.save(update_fields=["is_active", "subscription_ends_on", "updated_at"])


def shift_subscription(business, days: int):
    base = business.subscription_ends_on or timezone.localdate()
    business.subscription_ends_on = base + timedelta(days=days)
    if business.subscription_ends_on >= timezone.localdate():
        business.is_active = True
    business.save(update_fields=["is_active", "subscription_ends_on", "updated_at"])


def force_delete_business(business):
    """Remove a business even when related records protect each other."""
    with transaction.atomic():
        pending = [business]
        seen = 0
        while pending:
            seen += 1
            if seen > 20000:
                raise RuntimeError("Could not delete this business. Too many linked records.")
            obj = pending.pop()
            try:
                obj.delete()
            except ObjectDoesNotExist:
                continue
            except ProtectedError as exc:
                pending.append(obj)
                pending.extend(exc.protected_objects)

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone

from apps.accounts.models import User
from apps.businesses.models import Branch, Business
from apps.catalog.models import Product
from apps.customers.models import Customer
from apps.pos.models import OPEN_SALE_STATUSES, Sale

MONEY = DecimalField(max_digits=18, decimal_places=2)


def money(value) -> str:
    if value is None:
        return "0.00"
    return f"{Decimal(value):.2f}"


def period_start(period: str):
    now = timezone.now()
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "week":
        return now - timedelta(days=7)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def platform_overview(period: str = "month"):
    start = period_start(period)
    trend_start = timezone.now() - timedelta(days=13)
    businesses = Business.objects.all()
    today = timezone.localdate()
    live = Q(is_active=True) & (Q(subscription_ends_on__isnull=True) | Q(subscription_ends_on__gte=today))
    users = User.objects.filter(is_platform_admin=False)
    sales = Sale.objects.filter(status__in=OPEN_SALE_STATUSES)
    period_sales = sales.filter(created_at__gte=start)

    trend = (
        sales.filter(created_at__gte=trend_start)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            orders=Count("id"),
            revenue=Coalesce(Sum("total"), Decimal("0"), output_field=MONEY),
        )
        .order_by("day")
    )

    recent = businesses.order_by("-created_at")[:8]
    soon = today + timedelta(days=14)
    ending_qs = businesses.filter(
        live,
        subscription_ends_on__isnull=False,
        subscription_ends_on__gte=today,
        subscription_ends_on__lte=soon,
    )
    by_type = (
        businesses.values("business_type")
        .annotate(total=Count("id"), active=Count("id", filter=live))
        .order_by("-total", "business_type")
    )
    return {
        "period": period,
        "businesses": {
            "total": businesses.count(),
            "active": businesses.filter(live).count(),
            "inactive": businesses.exclude(live).count(),
            "new": businesses.filter(created_at__gte=start).count(),
        },
        "users": {
            "total": users.count(),
            "owners": users.filter(is_owner=True).count(),
            "staff": users.filter(is_owner=False).count(),
            "active": users.filter(is_active=True).count(),
            "new": users.filter(date_joined__gte=start).count(),
        },
        "branches": {"total": Branch.objects.count()},
        "products": {"total": Product.objects.count()},
        "customers": {"total": Customer.objects.count()},
        "expiring_soon": ending_qs.count(),
        "by_type": [
            {"business_type": row["business_type"], "total": row["total"], "active": row["active"]}
            for row in by_type
        ],
        "ending_soon": [
            {
                "id": str(row.id),
                "name": row.name,
                "business_type": row.business_type,
                "city": row.city,
                "subscription_ends_on": row.subscription_ends_on.isoformat(),
                "days_left": (row.subscription_ends_on - today).days,
            }
            for row in ending_qs.order_by("subscription_ends_on")[:6]
        ],
        "sales": {
            "count": sales.count(),
            "revenue": money(sales.aggregate(t=Coalesce(Sum("total"), Decimal("0"), output_field=MONEY))["t"]),
            "period_count": period_sales.count(),
            "period_revenue": money(
                period_sales.aggregate(t=Coalesce(Sum("total"), Decimal("0"), output_field=MONEY))["t"]
            ),
        },
        "sales_trend": [
            {
                "date": row["day"].isoformat() if row["day"] else "",
                "orders": row["orders"],
                "revenue": money(row["revenue"]),
            }
            for row in trend
        ],
        "recent_businesses": [
            {
                "id": str(row.id),
                "name": row.name,
                "business_type": row.business_type,
                "city": row.city,
                "is_active": row.is_active and (row.subscription_ends_on is None or row.subscription_ends_on >= timezone.localdate()),
                "subscription_ends_on": row.subscription_ends_on.isoformat() if row.subscription_ends_on else None,
                "created_at": row.created_at.isoformat(),
            }
            for row in recent
        ],
    }


def annotated_businesses():
    return Business.objects.annotate(
        user_count=Count("users", distinct=True),
        branch_count=Count("branches", distinct=True),
        product_count=Count("products", distinct=True),
        customer_count=Count("customers", distinct=True),
        sale_count=Count(
            "pos_sales",
            filter=Q(pos_sales__status__in=OPEN_SALE_STATUSES),
            distinct=True,
        ),
        owner_email=MaxOwnerEmail(),
    ).order_by("-created_at")


def MaxOwnerEmail():
    from django.db.models import CharField, OuterRef, Subquery

    owner = User.objects.filter(business_id=OuterRef("pk"), is_owner=True).order_by("date_joined")
    return Subquery(owner.values("email")[:1], output_field=CharField())

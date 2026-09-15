from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date


def period_bounds(request, default="month"):
    """
    Returns (start, end, label) in the active timezone.
    period: today | week | month | custom
    custom uses from=YYYY-MM-DD and to=YYYY-MM-DD inclusive.
    """
    tz = timezone.get_current_timezone()
    now = timezone.localtime()
    period = (request.query_params.get("period") or default).lower()
    today = now.date()

    if period == "custom":
        start_date = parse_date(request.query_params.get("from") or "") or today
        end_date = parse_date(request.query_params.get("to") or "") or today
        if end_date < start_date:
            start_date, end_date = end_date, start_date
    elif period == "today":
        start_date = end_date = today
    elif period == "week":
        start_date = today - timedelta(days=6)
        end_date = today
    else:
        period = "month"
        start_date = today.replace(day=1)
        end_date = today

    start = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    end = timezone.make_aware(datetime.combine(end_date, time.max), tz)
    return start, end, period


def in_range(qs, field="created_at", start=None, end=None):
    return qs.filter(**{f"{field}__gte": start, f"{field}__lte": end})

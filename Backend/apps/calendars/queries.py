from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Optional
from django.db.models import Q, QuerySet
from django.utils import timezone
from apps.tasks.models import Task

def _base(user) -> QuerySet:
    return (
        Task.objects
        .filter(user=user, deleted_at__isnull=True)
        .select_related('category')
        .prefetch_related('tags')
    )

def _now() -> datetime:
    return timezone.now()

def fetch_daily(user, target_date: date, now: Optional[datetime] = None) -> QuerySet:
    tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(
        datetime.combine(target_date, datetime.min.time()), tz
    )
    day_end = day_start + timedelta(days=1)

    return (
        _base(user)
        .filter(
            Q(deadline__gte=day_start, deadline__lt=day_end)
            | Q(deadline__isnull=True, created_at__date=target_date)
        )
        .order_by('deadline', 'priority', 'created_at')
    )

def fetch_weekly(user, week_start: date, now: Optional[datetime] = None) -> QuerySet:
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(week_start, datetime.min.time()), tz)
    end = start + timedelta(days=7)

    return (
        _base(user)
        .filter(deadline__gte=start, deadline__lt=end)
        .order_by('deadline', 'priority')
    )

def fetch_monthly(user, year: int, month: int, now: Optional[datetime] = None) -> QuerySet:
    import calendar as cal
    timezone = timezone.get_current_timezone()
    first_day = date(year, month, 1)
    last_day = date(year, month, cal.monthrange(year, month)[1])
    # Buffer for the view's leading/trailing week cells
    buffer_start = first_day - timedelta(days=7)
    buffer_end = last_day  + timedelta(days=7)

    start = timezone.make_aware(datetime.combine(buffer_start, datetime.min.time()), tz)
    end = timezone.make_aware(
        datetime.combine(buffer_end + timedelta(days=1), datetime.min.time()), tz
    )
    return (
        _base(user)
        .filter(deadline__gte=start, deadline__lt=end)
        .order_by('deadline', 'priority')
    )

def fetch_range(
    user,
    range_start: datetime,
    range_end: datetime,
    status_filter: Optional[list[str]] = None,
    priority_filter: Optional[list[str]] = None,
    category_id: Optional[int] = None,
    include_no_deadline: bool = False,
) -> QuerySet:
    qs = _base(user).filter(deadline__gte=range_start, deadline__lt=range_end)

    if include_no_deadline:
        qs = _base(user).filter(
            Q(deadline__gte=range_start, deadline__lt=range_end)
            | Q(deadline__isnull=True)
        )

    if status_filter:
        qs = qs.filter(status__in=status_filter)
    if priority_filter:
        qs = qs.filter(priority__in=priority_filter)
    if category_id:
        qs = qs.filter(category_id=category_id)
    return qs.order_by('deadline', 'priority')

def fetch_overdue(user, now: Optional[datetime] = None) -> QuerySet:
    cutoff = now or _now()
    return (
        _base(user)
        .filter(
            deadline__lt=cutoff,
            status__in=('todo', 'in_progress'),
        )
        .order_by('deadline')
    )

def fetch_upcoming(user, days: int = 7, now: Optional[datetime] = None) -> QuerySet:
    cutoff = now or _now()
    end = cutoff + timedelta(days=days)
    return (
        _base(user)
        .filter(
            deadline__gte=cutoff,
            deadline__lt=end,
            status__in=('todo', 'in_progress'),
        )
        .order_by('deadline')
    )

def fetch_no_deadline(user) -> QuerySet:
    return (
        _base(user)
        .filter(deadline__isnull=True, status__in=('todo', 'in_progress'))
        .order_by('priority', 'created_at')
    )

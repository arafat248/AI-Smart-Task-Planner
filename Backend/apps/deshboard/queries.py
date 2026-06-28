from __future__ import annotations
from datetime import date, timedelta
from django.db.models import (
    Avg, Case, Count, DurationField, ExpressionWrapper, F, FloatField,
    IntegerField, Max, Min, Q, Sum, Value, When,
)
from django.db.models.functions import (
    Cast, ExtractIsoWeekDay, ExtractWeek, ExtractYear, TruncDate,
    TruncMonth, TruncWeek,
)
from django.utils import timezone
from apps.tasks.models import Task

def _live_tasks(user):
    """Base queryset: active (non-deleted) tasks for this user."""
    return Task.objects.filter(user=user, deleted_at__isnull=True)

def _now():
    return timezone.now()

def fetch_summary(user) -> dict:
    """
    Returns total, completed, in_progress, todo, cancelled, overdue
    and productivity_pct in a single aggregation query.

    Uses conditional COUNT (CASE WHEN … THEN 1 END) which compiles
    to a single SQL SELECT with no subqueries or extra round-trips.
    """
    now = _now()
    qs  = _live_tasks(user)

    result = qs.aggregate(
        total=Count('id'),

        completed=Count('id', filter=Q(status='completed')),
        in_progress=Count('id', filter=Q(status='in_progress')),
        todo=Count('id', filter=Q(status='todo')),
        cancelled=Count('id', filter=Q(status='cancelled')),

        overdue=Count(
            'id',
            filter=Q(
                deadline__lt=now,
                status__in=('todo', 'in_progress'),
            ),
        ),

        # Deadlines within next 24 hours (not yet overdue)
        due_soon=Count(
            'id',
            filter=Q(
                deadline__gte=now,
                deadline__lt=now + timedelta(hours=24),
                status__in=('todo', 'in_progress'),
            ),
        ),

        ai_generated=Count('id', filter=Q(ai_generated=True)),

        # Sum estimated_time (DurationField) for active tasks
        total_estimated_time=Sum(
            'estimated_time',
            filter=Q(status__in=('todo', 'in_progress')),
        ),
        completed_estimated_time=Sum(
            'estimated_time',
            filter=Q(status='completed'),
        ),
    )

    total      = result['total'] or 0
    completed  = result['completed'] or 0
    cancelled  = result['cancelled'] or 0
    active     = total - cancelled   # denominator excludes cancelled

    # Productivity % = completed / (total - cancelled) × 100
    productivity_pct = round((completed / active * 100), 1) if active > 0 else 0.0

    # Convert DurationField totals to hours
    def _dur_to_h(dur) -> float:
        return round(dur.total_seconds() / 3600, 1) if dur else 0.0

    return {
        'total':                    total,
        'completed':                completed,
        'in_progress':              result['in_progress'] or 0,
        'todo':                     result['todo'] or 0,
        'cancelled':                cancelled,
        'overdue':                  result['overdue'] or 0,
        'due_soon':                 result['due_soon'] or 0,
        'ai_generated':             result['ai_generated'] or 0,
        'productivity_pct':         productivity_pct,
        'pending':                  (result['todo'] or 0) + (result['in_progress'] or 0),
        'total_estimated_hours':    _dur_to_h(result['total_estimated_time']),
        'completed_estimated_hours': _dur_to_h(result['completed_estimated_time']),
    }

def fetch_priority_breakdown(user) -> list[dict]:
    """
    Returns count per priority for active (non-cancelled, non-deleted) tasks.
    Single GROUP BY query.
    """
    rows = (
        _live_tasks(user)
        .exclude(status='cancelled')
        .values('priority')
        .annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status__in=('todo', 'in_progress'))),
        )
        .order_by('priority')
    )

    # Build a complete dict (every priority present, even if count=0)
    data = {p: {'priority': p, 'total': 0, 'completed': 0, 'pending': 0}
            for p in ('low', 'medium', 'high', 'urgent')}
    for row in rows:
        data[row['priority']] = {
            'priority':  row['priority'],
            'total':     row['total'],
            'completed': row['completed'],
            'pending':   row['pending'],
        }
    return list(data.values())

def fetch_category_breakdown(user, limit: int = 10) -> list[dict]:
    """
    Per-category count of total / completed / pending tasks.
    Single JOIN + GROUP BY — no N+1.
    """
    rows = (
        _live_tasks(user)
        .filter(category__isnull=False)
        .values('category__id', 'category__name', 'category__color', 'category__icon')
        .annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed')),
            pending=Count('id', filter=Q(status__in=('todo', 'in_progress'))),
            overdue=Count(
                'id',
                filter=Q(deadline__lt=_now(), status__in=('todo', 'in_progress'))
            ),
        )
        .order_by('-total')[:limit]
    )

    return [
        {
            'id':        row['category__id'],
            'name':      row['category__name'],
            'color':     row['category__color'],
            'icon':      row['category__icon'],
            'total':     row['total'],
            'completed': row['completed'],
            'pending':   row['pending'],
            'overdue':   row['overdue'],
        }
        for row in rows
    ]

def fetch_tag_breakdown(user, limit: int = 10) -> list[dict]:
    """Per-tag task counts via M2M join. Single query."""
    rows = (
        _live_tasks(user)
        .filter(tags__isnull=False)
        .values('tags__id', 'tags__name', 'tags__color')
        .annotate(
            total=Count('id', distinct=True),
            completed=Count('id', filter=Q(status='completed'), distinct=True),
        )
        .order_by('-total')[:limit]
    )
    return [
        {
            'id':        row['tags__id'],
            'name':      row['tags__name'],
            'color':     row['tags__color'],
            'total':     row['total'],
            'completed': row['completed'],
        }
        for row in rows
    ]

def fetch_daily_series(user, days: int = 7) -> list[dict]:
    """
    Returns one record per day for the last `days` days.
    Uses TruncDate + GROUP BY for a single query regardless of `days`.
    Python fills in zeroes for days with no activity.
    """
    today      = _now().date()
    start_date = today - timedelta(days=days - 1)

    # Single aggregation query grouped by completion date
    rows = (
        _live_tasks(user)
        .filter(completed_at__date__gte=start_date)
        .annotate(day=TruncDate('completed_at'))
        .values('day')
        .annotate(completed=Count('id'))
        .order_by('day')
    )
    completed_map = {str(row['day']): row['completed'] for row in rows}

    # Single query for created counts
    created_rows = (
        _live_tasks(user)
        .filter(created_at__date__gte=start_date)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(created=Count('id'))
        .order_by('day')
    )
    created_map = {str(row['day']): row['created'] for row in created_rows}

    # Build full series (zeroes for missing days)
    series = []
    for i in range(days):
        d = str(start_date + timedelta(days=i))
        series.append({
            'date':      d,
            'completed': completed_map.get(d, 0),
            'created':   created_map.get(d, 0),
        })
    return series

def fetch_weekly_series(user, weeks: int = 8) -> list[dict]:
    """
    Returns one record per ISO week for the last `weeks` weeks.
    Two queries (completed + created) — both single GROUP BY.
    """
    today      = _now().date()
    start_date = today - timedelta(weeks=weeks - 1)

    def _week_series(date_field: str, count_alias: str):
        return (
            _live_tasks(user)
            .filter(**{f'{date_field}__date__gte': start_date})
            .annotate(week_start=TruncWeek(date_field))
            .values('week_start')
            .annotate(**{count_alias: Count('id')})
            .order_by('week_start')
        )

    completed_map = {
        str(r['week_start'].date()): r['completed']
        for r in _week_series('completed_at', 'completed')
    }
    created_map = {
        str(r['week_start'].date()): r['created']
        for r in _week_series('created_at', 'created')
    }

    # Build Monday-anchored series
    current_monday = today - timedelta(days=today.weekday())
    series = []
    for i in range(weeks - 1, -1, -1):
        monday = str(current_monday - timedelta(weeks=i))
        series.append({
            'week_start': monday,
            'completed':  completed_map.get(monday, 0),
            'created':    created_map.get(monday, 0),
        })
    return series

def fetch_monthly_series(user, months: int = 6) -> list[dict]:
    """
    Returns one record per calendar month.
    Two queries grouped by TruncMonth — no per-month Python queries.
    """
    today      = _now().date()
    # Start of the first month in range
    start_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    for _ in range(months - 2):
        start_month = (start_month - timedelta(days=1)).replace(day=1)

    def _month_series(date_field: str, count_alias: str):
        return (
            _live_tasks(user)
            .filter(**{f'{date_field}__date__gte': start_month})
            .annotate(month=TruncMonth(date_field))
            .values('month')
            .annotate(**{count_alias: Count('id')})
            .order_by('month')
        )

    completed_map = {
        r['month'].strftime('%Y-%m'): r['completed']
        for r in _month_series('completed_at', 'completed')
    }
    created_map = {
        r['month'].strftime('%Y-%m'): r['created']
        for r in _month_series('created_at', 'created')
    }

    series = []
    month = start_month
    for _ in range(months):
        key = month.strftime('%Y-%m')
        series.append({
            'month':     key,
            'label':     month.strftime('%b %Y'),
            'completed': completed_map.get(key, 0),
            'created':   created_map.get(key, 0),
        })
        # Advance to next month
        month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
    return series

def fetch_completion_streak(user) -> dict:
    """
    Calculates current and longest completion streaks.
    ONE query: fetch all distinct completion dates, sort in Python.
    Avoids SQL window functions for portability across DB backends.
    """
    dates = sorted(
        _live_tasks(user)
        .filter(completed_at__isnull=False)
        .annotate(day=TruncDate('completed_at'))
        .values_list('day', flat=True)
        .distinct()
        .order_by('day')
    )

    if not dates:
        return {'current_streak': 0, 'longest_streak': 0, 'last_active_date': None}

    today     = _now().date()
    yesterday = today - timedelta(days=1)

    current_streak = 0
    longest_streak = 0
    run = 1

    for i in range(1, len(dates)):
        if (dates[i] - dates[i - 1]).days == 1:
            run += 1
        else:
            longest_streak = max(longest_streak, run)
            run = 1
    longest_streak = max(longest_streak, run)

    last = dates[-1]
    if last >= yesterday:
        current_streak = 1
        for i in range(len(dates) - 2, -1, -1):
            if (dates[i + 1] - dates[i]).days == 1:
                current_streak += 1
            else:
                break

    return {
        'current_streak':  current_streak,
        'longest_streak':  longest_streak,
        'last_active_date': str(last),
    }

def fetch_recent_completions(user, limit: int = 5) -> list[dict]:
    """
    Returns lightweight recent-completion records.
    select_related('category') for zero N+1 on category name.
    """
    tasks = (
        _live_tasks(user)
        .filter(status='completed', completed_at__isnull=False)
        .select_related('category')
        .only('id', 'title', 'priority', 'completed_at', 'category__name', 'category__color')
        .order_by('-completed_at')[:limit]
    )
    return [
        {
            'id':           t.id,
            'title':        t.title,
            'priority':     t.priority,
            'completed_at': t.completed_at.isoformat(),
            'category':     {'name': t.category.name, 'color': t.category.color}
                            if t.category else None,
        }
        for t in tasks
    ]

def fetch_upcoming_deadlines(user, limit: int = 5) -> list[dict]:
    """
    Returns upcoming tasks ordered by deadline ASC.
    select_related avoids category N+1.
    """
    now = _now()
    tasks = (
        _live_tasks(user)
        .filter(
            deadline__gte=now,
            status__in=('todo', 'in_progress'),
        )
        .select_related('category')
        .only('id', 'title', 'priority', 'status', 'deadline',
              'category__name', 'category__color')
        .order_by('deadline')[:limit]
    )
    return [
        {
            'id':       t.id,
            'title':    t.title,
            'priority': t.priority,
            'status':   t.status,
            'deadline': t.deadline.isoformat(),
            'hours_remaining': round(
                (t.deadline - now).total_seconds() / 3600, 1
            ),
            'category': {'name': t.category.name, 'color': t.category.color}
                        if t.category else None,
        }
        for t in tasks
    ]

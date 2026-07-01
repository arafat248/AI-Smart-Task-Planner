from __future__ import annotations
from datetime import datetime, timedelta, timezone as dt_tz
from typing import Any
from django.utils import timezone

PRIORITY_COLOR: dict[str, str] = {
    'urgent': '#EF4444',
    'high':   '#F97316',
    'medium': '#3B82F6',
    'low':    '#22C55E',
}

PRIORITY_BORDER: dict[str, str] = {
    'urgent': '#DC2626',
    'high':   '#EA580C',
    'medium': '#2563EB',
    'low':    '#16A34A',
}

PRIORITY_TEXT: dict[str, str] = {
    'urgent': '#ffffff',
    'high':   '#ffffff',
    'medium': '#ffffff',
    'low':    '#ffffff',
}

STATUS_CLASS: dict[str, str] = {
    'todo': 'fc-event-todo',
    'in_progress': 'fc-event-in-progress',
    'completed': 'fc-event-completed',
    'cancelled': 'fc-event-cancelled',
}

RECURRENCE_RRULE: dict[str, str] = {
    'daily': 'FREQ=DAILY',
    'weekly': 'FREQ=WEEKLY',
    'monthly': 'FREQ=MONTHLY',
}

def _is_all_day(dt: datetime) -> bool:
    """True when deadline carries no meaningful time (midnight UTC)."""
    utc = dt.astimezone(dt_tz.utc)
    return utc.hour == 0 and utc.minute == 0 and utc.second == 0

def _end_dt(deadline: datetime, estimated_time) -> datetime:
    if estimated_time is not None:
        return deadline + estimated_time
    return deadline + timedelta(minutes=30)

def _class_names(task_status: str, is_overdue: bool) -> list[str]:
    names = [STATUS_CLASS.get(task_status, '')]
    if is_overdue:
        names.append('fc-event-overdue')
    return [n for n in names if n]

def task_to_event(task) -> dict:
    now = timezone.now()
    deadline = task.deadline
    is_over = (
        deadline is not None
        and task.status not in ('completed', 'cancelled')
        and now > deadline
    )
    bg_color = PRIORITY_COLOR.get(task.priority, '#3B82F6')
    border_color = PRIORITY_BORDER.get(task.priority, '#2563EB')
    text_color = PRIORITY_TEXT.get(task.priority, '#ffffff')

    if is_over:
        bg_color = '#7F1D1D'
        border_color = '#991B1B'
        text_color = '#FCA5A5'

    # Completed tasks fade out
    if task.status == 'completed':
        bg_color  = '#6B7280'
        border_color = '#4B5563'

    event: dict[str, Any] = {
        'id': str(task.id),
        'title': task.title,

        'start': deadline.isoformat() if deadline else None,
        'end':  _end_dt(deadline, task.estimated_time).isoformat() if deadline else None,
        'allDay': _is_all_day(deadline) if deadline else False,

        'backgroundColor': bg_color,
        'borderColor': border_color,
        'textColor': text_color,
        'classNames': _class_names(task.status, is_over),

        'rrule': RECURRENCE_RRULE.get(task.recurrence) if task.recurrence != 'none' else None,
        'duration': _duration_str(task.estimated_time),

        'extendedProps': {
            'taskId': task.id,
            'description': task.description or '',
            'status': task.status,
            'priority': task.priority,
            'isOverdue': is_over,
            'aiGenerated': task.ai_generated,
            'recurrence': task.recurrence,
            'estimatedTime': str(task.estimated_time) if task.estimated_time else None,
            'estimatedMinutes': task.estimated_minutes,
            'reminderAt': task.reminder_at.isoformat() if task.reminder_at else None,
            'completedAt': task.completed_at.isoformat() if task.completed_at else None,
            'createdAt': task.created_at.isoformat(),
            'category': (
                {
                    'id': task.category.id,
                    'name': task.category.name,
                    'color': task.category.color,
                    'icon': task.category.icon,
                }
                if task.category else None
            ),
            'tags': [
                {'id': t.id, 'name': t.name, 'color': t.color}
                for t in task.tags.all()
            ],
        },
    }
    if event['rrule'] is None:
        del event['rrule']
    if event['duration'] is None:
        del event['duration']
    return event

def _duration_str(estimated_time) -> str | None:
    """Convert Python timedelta to FullCalendar duration string HH:MM:SS."""
    if estimated_time is None:
        return None
    total = int(estimated_time.total_seconds())
    h, rem = divmod(total, 3600)
    m, s   = divmod(rem, 60)
    return f'{h:02d}:{m:02d}:{s:02d}'

def tasks_to_events(tasks) -> list[dict]:
    """Batch-convert an iterable of Task objects to FullCalendar events."""
    return [task_to_event(t) for t in tasks]

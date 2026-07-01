import pytest
from datetime import datetime, timedelta, timezone as dt_tz
from unittest.mock import MagicMock, PropertyMock

from apps.calendar.formatters import (
    _duration_str, _end_dt, _is_all_day, task_to_event, tasks_to_events,
    PRIORITY_COLOR, PRIORITY_BORDER,
)
def _mock_task(**kwargs):
    t = MagicMock()
    t.id = kwargs.get('id', 1)
    t.title = kwargs.get('title', 'Test task')
    t.description = kwargs.get('description', 'desc')
    t.status = kwargs.get('status', 'todo')
    t.priority = kwargs.get('priority', 'medium')
    t.deadline = kwargs.get('deadline', None)
    t.estimated_time = kwargs.get('estimated_time', None)
    t.estimated_minutes = kwargs.get('estimated_minutes', None)
    t.recurrence = kwargs.get('recurrence', 'none')
    t.ai_generated = kwargs.get('ai_generated', False)
    t.reminder_at = kwargs.get('reminder_at', None)
    t.completed_at = kwargs.get('completed_at', None)
    t.created_at = kwargs.get('created_at', datetime.now(dt_tz.utc))
    t.category = kwargs.get('category', None)
    t.tags.all.return_value = kwargs.get('tags', [])

    type(t).is_overdue = PropertyMock(return_value=kwargs.get('is_overdue', False))
    return t

class TestIsAllDay:
    def test_midnight_utc_is_all_day(self):
        dt = datetime(2026, 6, 25, 0, 0, 0, tzinfo=dt_tz.utc)
        assert _is_all_day(dt) is True

    def test_specific_time_is_not_all_day(self):
        dt = datetime(2026, 6, 25, 9, 30, 0, tzinfo=dt_tz.utc)
        assert _is_all_day(dt) is False

class TestEndDt:
    def test_uses_estimated_time_when_present(self):
        deadline = datetime(2026, 6, 25, 9, 0, tzinfo=dt_tz.utc)
        end = _end_dt(deadline, timedelta(hours=2))
        assert end == datetime(2026, 6, 25, 11, 0, tzinfo=dt_tz.utc)

    def test_defaults_to_30_min_when_no_estimate(self):
        deadline = datetime(2026, 6, 25, 9, 0, tzinfo=dt_tz.utc)
        end = _end_dt(deadline, None)
        assert end == datetime(2026, 6, 25, 9, 30, tzinfo=dt_tz.utc)

class TestDurationStr:
    def test_2h30m(self):
        assert _duration_str(timedelta(hours=2, minutes=30)) == '02:30:00'

    def test_45min(self):
        assert _duration_str(timedelta(minutes=45)) == '00:45:00'

    def test_none_returns_none(self):
        assert _duration_str(None) is None

class TestTaskToEvent:
    def test_required_fullcalendar_fields_present(self):
        task  = _mock_task(deadline=datetime(2026, 6, 25, 9, 0, tzinfo=dt_tz.utc))
        event = task_to_event(task)
        for field in ('id', 'title', 'start', 'end', 'allDay',
                      'backgroundColor', 'borderColor', 'textColor',
                      'classNames', 'extendedProps'):
            assert field in event, f'Missing FullCalendar field: {field}'

    def test_id_is_string(self):
        task  = _mock_task(id=42)
        event = task_to_event(task)
        assert event['id'] == '42'
        assert isinstance(event['id'], str)

    def test_priority_color_mapping(self):
        for priority, color in PRIORITY_COLOR.items():
            task  = _mock_task(priority=priority,
                               deadline=datetime(2026, 6, 25, 9, 0, tzinfo=dt_tz.utc))
            event = task_to_event(task)
            assert event['backgroundColor'] == color

    def test_overdue_gets_distinct_color(self):
        task = _mock_task(
            deadline=datetime(2020, 1, 1, 9, 0, tzinfo=dt_tz.utc),
            is_overdue=True,
            status='todo',
        )
        event = task_to_event(task)
        assert event['backgroundColor'] == '#7F1D1D'
        assert 'fc-event-overdue' in event['classNames']

    def test_completed_gets_grey(self):
        task  = _mock_task(
            status='completed',
            deadline=datetime(2026, 6, 25, 9, 0, tzinfo=dt_tz.utc),
        )
        event = task_to_event(task)
        assert event['backgroundColor'] == '#6B7280'

    def test_null_deadline_produces_null_start_end(self):
        task  = _mock_task(deadline=None)
        event = task_to_event(task)
        assert event['start'] is None
        assert event['end'] is None
        assert event['allDay'] is False

    def test_recurring_task_includes_rrule(self):
        task = _mock_task(
            recurrence='daily',
            deadline=datetime(2026, 6, 25, 9, 0, tzinfo=dt_tz.utc),
            estimated_time=timedelta(minutes=30),
        )
        event = task_to_event(task)
        assert event['rrule'] == 'FREQ=DAILY'
        assert event['duration'] == '00:30:00'

    def test_non_recurring_has_no_rrule_key(self):
        task  = _mock_task(recurrence='none',
                           deadline=datetime(2026, 6, 25, 9, 0, tzinfo=dt_tz.utc))
        event = task_to_event(task)
        assert 'rrule' not in event

    def test_extended_props_shape(self):
        cat = MagicMock(id=5, name='Work', color='#3B82F6', icon='briefcase')
        tag = MagicMock(id=3, name='focus', color='#EF4444')
        task = _mock_task(
            deadline=datetime(2026, 6, 25, 9, 0, tzinfo=dt_tz.utc),
            category=cat, tags=[tag],
        )
        task.tags.all.return_value = [tag]
        event = task_to_event(task)
        ep = event['extendedProps']
        assert ep['taskId'] == task.id
        assert ep['category']['name'] == 'Work'
        assert ep['tags'][0]['name'] == 'focus'
        assert isinstance(ep['isOverdue'], bool)

    def test_tasks_to_events_batch(self):
        tasks = [_mock_task(id=i) for i in range(5)]
        events = tasks_to_events(tasks)
        assert len(events) == 5
        assert [e['id'] for e in events] == ['0', '1', '2', '3', '4']

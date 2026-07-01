import pytest
from datetime import date, timedelta
from django.utils import timezone
from apps.tasks.models import Task

BASE = '/api/calendar/events/'
NOW  = timezone.now()
TODAY = NOW.date()

def get_ids(response) -> set:
    return {e['id'] for e in response.data['data']['events']}

@pytest.mark.django_db
class TestAuthRequired:
    def test_daily_401(self):
        from rest_framework.test import APIClient
        assert APIClient().get(f'{BASE}daily/').status_code == 401

    def test_weekly_401(self):
        from rest_framework.test import APIClient
        assert APIClient().get(f'{BASE}weekly/').status_code == 401

    def test_monthly_401(self):
        from rest_framework.test import APIClient
        assert APIClient().get(f'{BASE}monthly/').status_code == 401

    def test_range_401(self):
        from rest_framework.test import APIClient
        assert APIClient().get(f'{BASE}range/').status_code == 401

    def test_overdue_401(self):
        from rest_framework.test import APIClient
        assert APIClient().get(f'{BASE}overdue/').status_code == 401

@pytest.mark.django_db
class TestDailyEndpoint:
    URL = f'{BASE}daily/'
    def test_returns_200(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        assert r.status_code == 200

    def test_response_shape(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        d = r.data['data']
        assert 'events' in d
        assert 'total' in d
        assert 'view' in d
        assert d['view'] == 'daily'

    def test_events_are_fullcalendar_objects(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        for event in r.data['data']['events']:
            assert 'id' in event
            assert 'title' in event
            assert 'start' in event
            assert 'backgroundColor' in event
            assert 'extendedProps' in event

    def test_includes_todays_tasks(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        ids = get_ids(r)
        assert str(task_set['today_todo'].id) in ids
        assert str(task_set['today_inprogress'].id) in ids
        assert str(task_set['today_completed'].id) in ids

    def test_excludes_other_dates(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        ids = get_ids(r)
        assert str(task_set['tomorrow'].id) not in ids
        assert str(task_set['next_week'].id) not in ids

    def test_excludes_soft_deleted(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        ids = get_ids(r)
        assert str(task_set['deleted'].id) not in ids

    def test_excludes_other_users_tasks(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        ids = get_ids(r)
        assert str(task_set['other_user_task'].id) not in ids

    def test_defaults_to_today(self, auth_client, task_set):
        client, _ = auth_client
        r_with_date    = client.get(self.URL, {'date': str(TODAY)})
        r_without_date = client.get(self.URL)
        assert r_with_date.data['data']['total'] == r_without_date.data['data']['total']

    def test_total_matches_events_length(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        d = r.data['data']
        assert d['total'] == len(d['events'])

    def test_overdue_events_have_overdue_class(self, auth_client, task_set):
        client, _ = auth_client
        # Check overdue endpoint to see styling
        r = client.get(f'{BASE}overdue/')
        for event in r.data['data']['events']:
            if event['extendedProps']['isOverdue']:
                assert 'fc-event-overdue' in event['classNames']
                assert event['backgroundColor'] == '#7F1D1D'

    def test_extended_props_contains_task_metadata(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'date': str(TODAY)})
        event = next(
            e for e in r.data['data']['events']
            if e['id'] == str(task_set['today_todo'].id)
        )
        ep = event['extendedProps']
        assert ep['status'] == 'todo'
        assert ep['priority'] == 'high'
        assert ep['category'] is not None
        assert ep['category']['name'] == 'Work'
        assert len(ep['tags']) == 1

@pytest.mark.django_db
class TestWeeklyEndpoint:
    URL = f'{BASE}weekly/'
    def test_returns_200(self, auth_client, task_set):
        client, _ = auth_client
        monday = TODAY - timedelta(days=TODAY.weekday())
        r = client.get(self.URL, {'week_start': str(monday)})
        assert r.status_code == 200

    def test_view_is_weekly(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.data['data']['view'] == 'weekly'

    def test_includes_7_day_window(self, auth_client, task_set):
        client, _ = auth_client
        monday = TODAY - timedelta(days=TODAY.weekday())
        r = client.get(self.URL, {'week_start': str(monday)})
        ids = get_ids(r)
        # today_todo (today) and tomorrow both fall in current week
        assert str(task_set['today_todo'].id) in ids

    def test_excludes_next_week(self, auth_client, task_set):
        client, _ = auth_client
        monday = TODAY - timedelta(days=TODAY.weekday())
        r = client.get(self.URL, {'week_start': str(monday)})
        ids = get_ids(r)
        assert str(task_set['next_week'].id) not in ids

    def test_snaps_non_monday_to_monday(self, auth_client, task_set):
        client, _ = auth_client
        wednesday = TODAY - timedelta(days=TODAY.weekday()) + timedelta(days=2)
        r = client.get(self.URL, {'week_start': str(wednesday)})
        assert r.status_code == 200
        # Same result as if we'd passed Monday
        monday = TODAY - timedelta(days=TODAY.weekday())
        r2 = client.get(self.URL, {'week_start': str(monday)})
        assert r.data['data']['total'] == r2.data['data']['total']

    def test_recurring_task_includes_rrule(self, auth_client, task_set):
        client, _ = auth_client
        monday = TODAY - timedelta(days=TODAY.weekday())
        r = client.get(self.URL, {'week_start': str(monday)})
        recurring_events = [
            e for e in r.data['data']['events']
            if e['id'] == str(task_set['recurring'].id)
        ]
        if recurring_events:
            assert recurring_events[0].get('rrule') == 'FREQ=DAILY'

    def test_range_start_end_present(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        d = r.data['data']
        assert d['range_start'] is not None
        assert d['range_end'] is not None

@pytest.mark.django_db
class TestMonthlyEndpoint:
    URL = f'{BASE}monthly/'

    def test_returns_200(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'year': TODAY.year, 'month': TODAY.month})
        assert r.status_code == 200

    def test_view_is_monthly(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.data['data']['view'] == 'monthly'

    def test_includes_current_month_tasks(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'year': TODAY.year, 'month': TODAY.month})
        ids = get_ids(r)
        assert str(task_set['today_todo'].id) in ids

    def test_invalid_month_returns_400(self, auth_client):
        client, _ = auth_client
        r = client.get(self.URL, {'month': 13})
        assert r.status_code == 400

    def test_includes_buffer_days(self, auth_client, user):
        from django.utils import timezone
        first_of_month = TODAY.replace(day=1)
        if first_of_month > TODAY:
            return  # can't test this if we're already at start of month
        task = Task.objects.create(
            user=user, title='Buffer task', status='todo', priority='low',
            deadline=timezone.make_aware(
                __import__('datetime').datetime.combine(first_of_month, __import__('datetime').time(9))
            ),
        )
        client, _ = auth_client
        prev_month = (first_of_month - timedelta(days=1))
        r = client.get(self.URL, {'year': prev_month.year, 'month': prev_month.month})
        ids = get_ids(r)
        assert str(task.id) in ids

    def test_defaults_to_current_month(self, auth_client, task_set):
        client, _ = auth_client
        r_explicit = client.get(self.URL, {'year': TODAY.year, 'month': TODAY.month})
        r_default  = client.get(self.URL)
        assert r_explicit.data['data']['total'] == r_default.data['data']['total']

@pytest.mark.django_db
class TestRangeEndpoint:
    URL = f'{BASE}range/'
    def test_returns_200(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {
            'start': NOW.isoformat(),
            'end':   (NOW + timedelta(days=7)).isoformat(),
        })
        assert r.status_code == 200

    def test_view_is_range(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {
            'start': NOW.isoformat(),
            'end': (NOW + timedelta(days=7)).isoformat(),
        })
        assert r.data['data']['view'] == 'range'

    def test_missing_start_returns_400(self, auth_client):
        client, _ = auth_client
        r = client.get(self.URL, {'end': NOW.isoformat()})
        assert r.status_code == 400

    def test_end_before_start_returns_400(self, auth_client):
        client, _ = auth_client
        r = client.get(self.URL, {
            'start': (NOW + timedelta(days=7)).isoformat(),
            'end':   NOW.isoformat(),
        })
        assert r.status_code == 400

    def test_status_filter(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {
            'start': (NOW - timedelta(days=30)).isoformat(),
            'end': (NOW + timedelta(days=30)).isoformat(),
            'status': ['completed'],
        })
        events = r.data['data']['events']
        assert all(e['extendedProps']['status'] == 'completed' for e in events)

    def test_priority_filter(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {
            'start': (NOW - timedelta(days=30)).isoformat(),
            'end': (NOW + timedelta(days=30)).isoformat(),
            'priority': ['urgent'],
        })
        events = r.data['data']['events']
        assert all(e['extendedProps']['priority'] == 'urgent' for e in events)

    def test_category_filter(self, auth_client, task_set, category):
        client, _ = auth_client
        r = client.get(self.URL, {
            'start': (NOW - timedelta(days=1)).isoformat(),
            'end': (NOW + timedelta(days=30)).isoformat(),
            'category': category.id,
        })
        events = r.data['data']['events']
        assert all(
            e['extendedProps']['category'] is not None and
            e['extendedProps']['category']['id'] == category.id
            for e in events
        )

    def test_range_excludes_soft_deleted(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {
            'start': (NOW - timedelta(days=1)).isoformat(),
            'end': (NOW + timedelta(days=30)).isoformat(),
        })
        ids = get_ids(r)
        assert str(task_set['deleted'].id) not in ids

@pytest.mark.django_db
class TestOverdueEndpoint:
    URL = f'{BASE}overdue/'

    def test_returns_200(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.status_code == 200

    def test_response_has_events_and_meta(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        d = r.data['data']
        assert 'events' in d
        assert 'meta' in d

    def test_meta_fields(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        meta = r.data['data']['meta']
        assert 'total' in meta
        assert 'critical' in meta
        assert 'by_priority' in meta
        assert 'oldest_deadline' in meta

    def test_includes_overdue_tasks(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        ids = get_ids(r)
        assert str(task_set['overdue_recent'].id) in ids
        assert str(task_set['overdue_old'].id) in ids

    def test_excludes_completed_overdue(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        ids = get_ids(r)
        assert str(task_set['overdue_but_done'].id) not in ids

    def test_total_matches_events(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        d = r.data['data']
        assert d['meta']['total'] == len(d['events'])

    def test_critical_counts_old_overdue(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.data['data']['meta']['critical'] >= 1

    def test_by_priority_has_all_keys(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        bp = r.data['data']['meta']['by_priority']
        for p in ('low', 'medium', 'high', 'urgent'):
            assert p in bp

    def test_priority_filter(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'priority': ['urgent']})
        events = r.data['data']['events']
        assert all(e['extendedProps']['priority'] == 'urgent' for e in events)

    def test_all_overdue_events_have_overdue_class(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        for event in r.data['data']['events']:
            assert 'fc-event-overdue' in event['classNames']

    def test_excludes_soft_deleted(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        ids = get_ids(r)
        assert str(task_set['deleted'].id) not in ids

    def test_excludes_other_users_tasks(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        ids = get_ids(r)
        assert str(task_set['other_user_task'].id) not in ids

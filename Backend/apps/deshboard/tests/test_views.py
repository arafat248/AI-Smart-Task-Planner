import pytest
from rest_framework import status

BASE = '/api/dashboard/'

@pytest.mark.django_db
class TestOverviewEndpoint:
    URL = f'{BASE}overview/'

    def test_requires_auth(self):
        from rest_framework.test import APIClient
        r = APIClient().get(self.URL)
        assert r.status_code == 401

    def test_returns_200_with_all_sections(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.status_code == 200
        d = r.data['data']
        for key in ('summary', 'priorities', 'categories', 'tags',
                    'streak', 'upcoming_deadlines', 'recent_completions'):
            assert key in d, f'Missing key: {key}'

    def test_summary_fields(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        s = r.data['data']['summary']
        for field in ('total', 'completed', 'in_progress', 'todo', 'cancelled',
                      'pending', 'overdue', 'due_soon', 'productivity_pct',
                      'total_estimated_hours'):
            assert field in s, f'Missing summary field: {field}'

    def test_productivity_pct_between_0_and_100(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        pct = r.data['data']['summary']['productivity_pct']
        assert 0.0 <= pct <= 100.0

    def test_overdue_correct(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.data['data']['summary']['overdue'] == 1

    def test_pending_equals_todo_plus_in_progress(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        s = r.data['data']['summary']
        assert s['pending'] == s['todo'] + s['in_progress']

    def test_deleted_task_not_counted(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        # 11 tasks created (including 1 deleted) → total should be 10
        assert r.data['data']['summary']['total'] == 10

    def test_priorities_has_all_four_levels(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        priorities = {p['priority'] for p in r.data['data']['priorities']}
        assert priorities == {'low', 'medium', 'high', 'urgent'}

    def test_upcoming_deadlines_are_in_future(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        for item in r.data['data']['upcoming_deadlines']:
            assert item['hours_remaining'] > 0

    def test_streak_has_required_fields(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        streak = r.data['data']['streak']
        assert 'current_streak' in streak
        assert 'longest_streak' in streak

    def test_isolates_to_own_user(self, auth_client, other_user, task_set):
        from apps.tasks.models import Task
        from django.utils import timezone
        Task.objects.create(
            user=other_user, title='Theirs',
            status='completed', priority='low',
            completed_at=timezone.now(),
        )
        client, _ = auth_client
        r = client.get(self.URL)
        # Other user's completed task must not inflate the count
        assert r.data['data']['summary']['completed'] == 4

@pytest.mark.django_db
class TestWeeklyEndpoint:
    URL = f'{BASE}weekly/'

    def test_returns_200(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.status_code == 200

    def test_response_shape(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        d = r.data['data']
        assert 'daily' in d
        assert 'weekly' in d

    def test_daily_has_7_entries(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert len(r.data['data']['daily']) == 7

    def test_weekly_respects_weeks_param(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'weeks': 4})
        assert len(r.data['data']['weekly']) == 4

    def test_weekly_default_8_weeks(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert len(r.data['data']['weekly']) == 8

    def test_daily_entries_have_required_fields(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        for entry in r.data['data']['daily']:
            assert 'date' in entry
            assert 'completed' in entry
            assert 'created' in entry

    def test_weekly_entries_are_mondays(self, auth_client, task_set):
        from datetime import date
        client, _ = auth_client
        r = client.get(self.URL, {'weeks': 4})
        for entry in r.data['data']['weekly']:
            d = date.fromisoformat(entry['week_start'])
            assert d.weekday() == 0

    def test_invalid_weeks_param_returns_400(self, auth_client):
        client, _ = auth_client
        r = client.get(self.URL, {'weeks': 0})
        assert r.status_code == 400

    def test_weeks_param_max_clamped(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'weeks': 100})
        assert r.status_code == 400

@pytest.mark.django_db
class TestMonthlyEndpoint:
    URL = f'{BASE}monthly/'

    def test_returns_200(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.status_code == 200

    def test_response_shape(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        d = r.data['data']
        assert 'monthly' in d
        assert 'month_on_month_delta' in d

    def test_monthly_default_6_entries(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert len(r.data['data']['monthly']) == 6

    def test_monthly_respects_months_param(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'months': 3})
        assert len(r.data['data']['monthly']) == 3

    def test_month_labels_present(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        for entry in r.data['data']['monthly']:
            assert 'label' in entry
            assert 'month' in entry

    def test_mom_delta_null_when_no_history(self, auth_client):
        client, _ = auth_client
        r = client.get(self.URL, {'months': 1})
        assert r.status_code == 200

    def test_invalid_months_param_returns_400(self, auth_client):
        client, _ = auth_client
        r = client.get(self.URL, {'months': 0})
        assert r.status_code == 400

@pytest.mark.django_db
class TestFullAnalyticsEndpoint:
    URL = f'{BASE}analytics/'

    def test_returns_200(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        assert r.status_code == 200

    def test_contains_all_top_level_keys(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        d = r.data['data']
        for key in ('summary', 'priorities', 'categories', 'tags',
                    'streak', 'upcoming_deadlines', 'recent_completions',
                    'daily_progress', 'weekly_progress', 'monthly_progress',
                    'month_on_month_delta'):
            assert key in d, f'Missing key: {key}'

    def test_accepts_weeks_and_months_params(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL, {'weeks': 4, 'months': 3})
        assert r.status_code == 200
        assert len(r.data['data']['weekly_progress']) == 4
        assert len(r.data['data']['monthly_progress']) == 3

    def test_returns_401_without_auth(self):
        from rest_framework.test import APIClient
        r = APIClient().get(self.URL)
        assert r.status_code == 401

    def test_summary_counts_are_correct(self, auth_client, task_set):
        client, _ = auth_client
        r = client.get(self.URL)
        s = r.data['data']['summary']
        assert s['total'] == 10
        assert s['overdue'] == 1
        assert s['cancelled'] == 1
        assert s['ai_generated'] == 1

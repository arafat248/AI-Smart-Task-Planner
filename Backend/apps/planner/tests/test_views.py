import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone
from rest_framework import status
from apps.planner.models import AIPlan, PlanStatus
from apps.planner.services import PlannerService

BASE = '/api/planner/plans/'
TODAY = timezone.now().date().isoformat()

@pytest.mark.django_db
class TestGeneratePlan:
    @patch('apps.planner.views.generate_plan_async')
    def test_returns_202_with_plan_id(self, mock_task, auth_client):
        mock_task.delay = MagicMock()
        client, _ = auth_client
        r = client.post(BASE, {
            'plan_type': 'daily',
            'plan_date': TODAY,
            'available_hours': '8.0',
            'work_start_time': '09:00',
            'work_end_time': '17:00',
        })
        assert r.status_code == 202
        assert 'id' in r.data['data']
        assert r.data['data']['status'] == PlanStatus.PENDING
        mock_task.delay.assert_called_once()

    @patch('apps.planner.views.generate_plan_async')
    def test_defaults_plan_date_to_today(self, mock_task, auth_client):
        mock_task.delay = MagicMock()
        client, _ = auth_client
        r = client.post(BASE, {'plan_type': 'daily', 'available_hours': '8.0'})
        assert r.status_code == 202
        assert r.data['data']['plan_date'] == TODAY

    def test_requires_authentication(self):
        from rest_framework.test import APIClient
        r = APIClient().post(BASE, {'plan_type': 'daily', 'plan_date': TODAY})
        assert r.status_code == 401

    def test_rejects_invalid_plan_type(self, auth_client):
        client, _ = auth_client
        r = client.post(BASE, {'plan_type': 'hourly', 'plan_date': TODAY})
        assert r.status_code == 400

    def test_rejects_invalid_work_window(self, auth_client):
        client, _ = auth_client
        r = client.post(BASE, {
            'plan_type': 'daily', 'plan_date': TODAY,
            'work_start_time': '17:00', 'work_end_time': '09:00',
        })
        assert r.status_code == 400

    def test_rejects_zero_available_hours(self, auth_client):
        client, _ = auth_client
        r = client.post(BASE, {
            'plan_type': 'daily', 'plan_date': TODAY, 'available_hours': '0',
        })
        assert r.status_code == 400

    @patch('apps.planner.views.generate_plan_async')
    def test_weekly_plan_accepted(self, mock_task, auth_client):
        mock_task.delay = MagicMock()
        client, _ = auth_client
        r = client.post(BASE, {
            'plan_type': 'weekly',
            'plan_date': TODAY,
            'available_hours': '40.0',
        })
        assert r.status_code == 202

@pytest.mark.django_db
class TestListPlans:
    def test_returns_only_own_plans(self, auth_client, other_client, completed_plan):
        client, _ = auth_client
        oclient, _ = other_client
        # other user has no plans — should see empty list
        r = oclient.get(BASE)
        assert r.status_code == 200
        assert r.data['meta']['count'] == 0

    def test_returns_completed_plan_in_history(self, auth_client, completed_plan):
        client, _ = auth_client
        r = client.get(BASE)
        assert r.status_code == 200
        ids = [p['id'] for p in r.data['data']]
        assert completed_plan.id in ids

    def test_filter_by_plan_type(self, auth_client, user, completed_plan):
        client, _ = auth_client
        AIPlan.objects.create(
            user=user, plan_date=TODAY, plan_type='weekly',
            status=PlanStatus.COMPLETED, available_hours=8.0,
        )
        r = client.get(BASE, {'plan_type': 'daily'})
        assert r.status_code == 200
        assert all(p['plan_type'] == 'daily' for p in r.data['data'])

    def test_pending_plans_not_in_history(self, auth_client, pending_plan):
        client, _ = auth_client
        r = client.get(BASE)
        ids = [p['id'] for p in r.data['data']]
        assert pending_plan.id not in ids

@pytest.mark.django_db
class TestRetrievePlan:
    def test_retrieve_completed_plan(self, auth_client, completed_plan):
        client, _ = auth_client
        r = client.get(f'{BASE}{completed_plan.id}/')
        assert r.status_code == 200
        d = r.data['data']
        assert d['id'] == completed_plan.id
        assert 'recommended_order' in d
        assert 'time_blocks' in d
        assert 'break_suggestions' in d
        assert 'overdue_risk' in d
        assert 'productivity_score' in d
        assert 'tips' in d

    def test_retrieve_contains_all_score_fields(self, auth_client, completed_plan):
        client, _ = auth_client
        r = client.get(f'{BASE}{completed_plan.id}/')
        score = r.data['data']['productivity_score']
        for key in ('overall', 'focus', 'feasibility', 'balance', 'urgency_load', 'advice'):
            assert key in score

    def test_retrieve_other_users_plan_returns_404(self, other_client, completed_plan):
        client, _ = other_client
        r = client.get(f'{BASE}{completed_plan.id}/')
        assert r.status_code == 404

    def test_retrieve_nonexistent_returns_404(self, auth_client):
        client, _ = auth_client
        r = client.get(f'{BASE}999999/')
        assert r.status_code == 404

@pytest.mark.django_db
class TestPlanStatus:
    def test_status_completed(self, auth_client, completed_plan):
        client, _ = auth_client
        r = client.get(f'{BASE}{completed_plan.id}/status/')
        assert r.status_code == 200
        d = r.data['data']
        assert d['status'] == PlanStatus.COMPLETED
        assert d['is_ready'] is True
        assert d['overall_score'] == 82

    def test_status_pending(self, auth_client, pending_plan):
        client, _ = auth_client
        r = client.get(f'{BASE}{pending_plan.id}/status/')
        assert r.status_code == 200
        assert r.data['data']['status'] == PlanStatus.PENDING
        assert r.data['data']['is_ready'] is False

    def test_status_failed_shows_error_message(self, auth_client, failed_plan):
        client, _ = auth_client
        r = client.get(f'{BASE}{failed_plan.id}/status/')
        assert r.status_code == 200
        assert r.data['data']['error_message'] == 'OpenAI API quota exceeded.'

@pytest.mark.django_db
class TestLatestPlan:
    def test_latest_returns_most_recent_completed(self, auth_client, completed_plan):
        client, _ = auth_client
        r = client.get(f'{BASE}latest/')
        assert r.status_code == 200
        assert r.data['data']['id'] == completed_plan.id

    def test_latest_returns_204_when_none(self, auth_client):
        client, _ = auth_client
        r = client.get(f'{BASE}latest/')
        assert r.status_code == 204

    def test_latest_respects_plan_type(self, auth_client, completed_plan):
        client, _ = auth_client
        r = client.get(f'{BASE}latest/', {'plan_type': 'weekly'})
        assert r.status_code == 204

@pytest.mark.django_db
class TestRegeneratePlan:
    @patch('apps.planner.views.generate_plan_async')
    def test_regenerate_failed_plan(self, mock_task, auth_client, failed_plan):
        mock_task.delay = MagicMock()
        client, _ = auth_client
        r = client.post(f'{BASE}{failed_plan.id}/regenerate/')
        assert r.status_code == 202
        failed_plan.refresh_from_db()
        assert failed_plan.status == PlanStatus.PENDING
        assert failed_plan.retry_count == 1
        mock_task.delay.assert_called_once()

    @patch('apps.planner.views.generate_plan_async')
    def test_regenerate_completed_plan(self, mock_task, auth_client, completed_plan):
        mock_task.delay = MagicMock()
        client, _ = auth_client
        r = client.post(f'{BASE}{completed_plan.id}/regenerate/')
        assert r.status_code == 202

    def test_regenerate_generating_plan_returns_400(self, auth_client, pending_plan):
        pending_plan.status = PlanStatus.GENERATING
        pending_plan.save()
        client, _ = auth_client
        r = client.post(f'{BASE}{pending_plan.id}/regenerate/')
        assert r.status_code == 400

@pytest.mark.django_db
class TestDeletePlan:
    def test_delete_own_plan(self, auth_client, completed_plan):
        client, _ = auth_client
        r = client.delete(f'{BASE}{completed_plan.id}/')
        assert r.status_code == 204
        assert not AIPlan.objects.filter(id=completed_plan.id).exists()

    def test_delete_other_users_plan_returns_404(self, other_client, completed_plan):
        client, _ = other_client
        r = client.delete(f'{BASE}{completed_plan.id}/')
        assert r.status_code == 404

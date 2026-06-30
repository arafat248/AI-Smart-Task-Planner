import pytest
from django.utils import timezone
from apps.planner.models import AIPlan, PlanStatus
from apps.planner.repositories import PlannerRepository
TODAY = timezone.now().date().isoformat()


@pytest.mark.django_db
class TestAIPlanModel:
    def test_str_representation(self, completed_plan):
        assert 'AIPlan<' in str(completed_plan)
        assert completed_plan.plan_type in str(completed_plan)

    def test_is_ready_true_for_completed(self, completed_plan):
        assert completed_plan.is_ready is True

    def test_is_ready_false_for_pending(self, pending_plan):
        assert pending_plan.is_ready is False

    def test_is_ready_false_for_failed(self, failed_plan):
        assert failed_plan.is_ready is False

    def test_overall_score_from_productivity_score(self, completed_plan):
        assert completed_plan.overall_score == 82

    def test_overall_score_none_when_empty(self, pending_plan):
        assert pending_plan.overall_score is None

    def test_defaults(self, user):
        plan = AIPlan.objects.create(
            user=user, plan_date=TODAY, plan_type='daily'
        )
        assert plan.status == PlanStatus.PENDING
        assert plan.recommended_order == []
        assert plan.time_blocks == []
        assert plan.break_suggestions == []
        assert plan.tips == []
        assert plan.retry_count == 0

@pytest.mark.django_db
class TestPlannerRepository:

    def test_create_pending(self, user):
        repo = PlannerRepository()
        plan = repo.create_pending(
            user=user,
            plan_date=TODAY,
            plan_type='daily',
            input_tasks=[{'id': 1, 'title': 'T'}],
            available_hours=8.0,
            work_start_time='09:00',
            work_end_time='17:00',
        )
        assert plan.id is not None
        assert plan.status == PlanStatus.PENDING
        assert plan.input_tasks == [{'id': 1, 'title': 'T'}]

    def test_mark_generating(self, pending_plan):
        repo = PlannerRepository()
        repo.mark_generating(pending_plan, 'test prompt')
        pending_plan.refresh_from_db()
        assert pending_plan.status == PlanStatus.GENERATING
        assert pending_plan.prompt_used == 'test prompt'

    def test_save_result(self, pending_plan):
        repo = PlannerRepository()
        parsed = {
            'summary': 'Great day!',
            'recommended_order': [{'task_id': 1, 'title': 'T', 'rank': 1, 'reason': 'r', 'suggested_slot': '', 'score': 80}],
            'time_blocks': [],
            'break_suggestions': [],
            'overdue_risk': {'risk_level': 'none', 'risk_score': 0, 'at_risk_tasks': [], 'overloaded_days': [], 'analysis': ''},
            'productivity_score': {'overall': 75, 'focus': 80, 'feasibility': 70, 'balance': 75, 'urgency_load': 20, 'advice': []},
            'tips': ['Tip 1'],
        }
        repo.save_result(pending_plan, parsed, parsed, 1200)
        pending_plan.refresh_from_db()
        assert pending_plan.status == PlanStatus.COMPLETED
        assert pending_plan.summary == 'Great day!'
        assert pending_plan.generation_ms == 1200

    def test_mark_failed(self, pending_plan):
        repo = PlannerRepository()
        repo.mark_failed(pending_plan, 'API error')
        pending_plan.refresh_from_db()
        assert pending_plan.status == PlanStatus.FAILED
        assert pending_plan.error_message == 'API error'
        assert pending_plan.retry_count == 1

    def test_latest_for_user_returns_most_recent_completed(self, user, completed_plan):
        repo = PlannerRepository()
        result = repo.latest_for_user(user, 'daily')
        assert result is not None
        assert result.status == PlanStatus.COMPLETED

    def test_latest_for_user_ignores_pending(self, user, pending_plan):
        repo = PlannerRepository()
        result = repo.latest_for_user(user, 'daily')
        assert result is None

    def test_get_by_id_raises_for_wrong_user(self, completed_plan, other_user):
        repo = PlannerRepository()
        with pytest.raises(AIPlan.DoesNotExist):
            repo.get_by_id(completed_plan.id, other_user)

    def test_history_for_user_filters_by_type(self, user, completed_plan):
        AIPlan.objects.create(
            user=user, plan_date=TODAY, plan_type='weekly',
            status=PlanStatus.COMPLETED, available_hours=8.0,
        )
        repo = PlannerRepository()
        daily = list(repo.history_for_user(user, 'daily'))
        weekly = list(repo.history_for_user(user, 'weekly'))
        assert all(p.plan_type == 'daily' for p in daily)
        assert all(p.plan_type == 'weekly' for p in weekly)

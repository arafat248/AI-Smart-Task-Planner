import pytest
from datetime import timedelta
from unittest.mock import MagicMock, patch
from django.utils import timezone
from rest_framework.exceptions import ServiceUnavailable, ValidationError
from apps.planner.models import AIPlan, PlanStatus
from apps.planner.services import PlannerService, _serialise_task
TODAY = timezone.now().date().isoformat()

MOCK_AI_RESPONSE = {
    'summary': 'A productive day ahead.',
    'recommended_order': [
        {'task_id': 1, 'title': 'Task A', 'rank': 1, 'reason': 'Urgent', 'suggested_slot': '9:00-10:00', 'score': 90},
    ],
    'time_blocks': [
        {'start': '09:00', 'end': '10:00', 'title': 'Task A', 'type': 'work', 'task_id': 1, 'notes': ''},
        {'start': '10:00', 'end': '10:15', 'title': 'Break', 'type': 'break', 'task_id': None, 'notes': ''},
    ],
    'break_suggestions': [
        {'after_block': 1, 'time': '10:00', 'duration_minutes': 15, 'type': 'short', 'reason': 'Rest'},
    ],
    'overdue_risk': {
        'risk_level': 'low', 'risk_score': 10,
        'at_risk_tasks': [], 'overloaded_days': [], 'analysis': 'Low risk.',
    },
    'productivity_score': {
        'overall': 85, 'focus': 90, 'feasibility': 80, 'balance': 85, 'urgency_load': 25,
        'advice': ['Batch tasks.', 'Hydrate regularly.', 'Plan tomorrow tonight.'],
    },
    'tips': ['Use Pomodoro.', 'Turn off Slack.', 'Walk at noon.'],
}

@pytest.mark.django_db
class TestPlannerServiceCreatePending:
    def test_creates_pending_plan_with_task_snapshot(self, user, tasks):
        plan = PlannerService().create_pending_plan(
            user=user, plan_type='daily', plan_date=TODAY,
            available_hours=8.0, work_start_time='09:00', work_end_time='17:00',
        )
        assert plan.status == PlanStatus.PENDING
        assert len(plan.input_tasks) == len(tasks)
        assert all('id' in t and 'title' in t for t in plan.input_tasks)

    def test_snapshot_excludes_completed_tasks(self, user, tasks):
        from apps.tasks.models import Task
        Task.objects.filter(user=user).update(status='completed')
        plan = PlannerService().create_pending_plan(
            user=user, plan_type='daily', plan_date=TODAY,
            available_hours=8.0, work_start_time='09:00', work_end_time='17:00',
        )
        assert plan.input_tasks == []

@pytest.mark.django_db
class TestPlannerServiceGenerate:
    @patch.object(PlannerService, '_call_openai', return_value=MOCK_AI_RESPONSE)
    def test_generate_completes_plan(self, mock_ai, pending_plan):
        result = PlannerService().generate(pending_plan)
        assert result.status == PlanStatus.COMPLETED
        assert result.summary == 'A productive day ahead.'
        assert len(result.time_blocks) == 2
        assert len(result.recommended_order) == 1
        assert result.overall_score == 85
        assert result.generation_ms is not None

    @patch.object(PlannerService, '_call_openai', return_value=MOCK_AI_RESPONSE)
    def test_generate_saves_break_suggestions(self, mock_ai, pending_plan):
        result = PlannerService().generate(pending_plan)
        assert len(result.break_suggestions) == 1
        assert result.break_suggestions[0]['type'] == 'short'

    @patch.object(PlannerService, '_call_openai', return_value=MOCK_AI_RESPONSE)
    def test_generate_saves_overdue_risk(self, mock_ai, pending_plan):
        result = PlannerService().generate(pending_plan)
        assert result.overdue_risk['risk_level'] == 'low'

    @patch.object(PlannerService, '_call_openai', side_effect=Exception('API timeout'))
    def test_generate_marks_failed_on_openai_error(self, mock_ai, pending_plan):
        with pytest.raises(ServiceUnavailable):
            PlannerService().generate(pending_plan)
        pending_plan.refresh_from_db()
        assert pending_plan.status == PlanStatus.FAILED
        assert 'API timeout' in pending_plan.error_message

    @patch.object(PlannerService, '_call_openai', return_value={'summary': 'incomplete'})
    def test_generate_marks_failed_on_schema_error(self, mock_ai, pending_plan):
        with pytest.raises(ValidationError):
            PlannerService().generate(pending_plan)
        pending_plan.refresh_from_db()
        assert pending_plan.status == PlanStatus.FAILED

@pytest.mark.django_db
class TestPlannerServiceFeasibilityOverride:
    @patch.object(PlannerService, '_call_openai')
    def test_feasibility_corrected_downward_when_overloaded(self, mock_ai, pending_plan):
        """If tasks take 20h but only 8h available, feasibility must be ≤0."""
        overloaded_response = {
            **MOCK_AI_RESPONSE,
            'productivity_score': {
                **MOCK_AI_RESPONSE['productivity_score'],
                'feasibility': 95,  # AI is overconfident
                'overall': 95,
            },
        }
        pending_plan.input_tasks = [
            {'id': i, 'title': f'T{i}', 'priority': 'medium',
             'status': 'todo', 'estimated_minutes': 120, 'is_overdue': False}
            for i in range(10)  # 10 × 2h = 20h
        ]
        pending_plan.available_hours = 8.0
        pending_plan.save()
        mock_ai.return_value = overloaded_response

        result = PlannerService().generate(pending_plan)
        assert result.productivity_score['feasibility'] < 95

@pytest.mark.django_db
class TestPlannerServiceGetters:
    def test_get_plan_raises_not_found_for_wrong_user(self, completed_plan, other_user):
        with pytest.raises(Exception):
            PlannerService().get_plan(completed_plan.id, other_user)

    def test_get_latest_returns_completed_only(self, user, pending_plan, completed_plan):
        result = PlannerService().get_latest(user, 'daily')
        assert result.status == PlanStatus.COMPLETED

    def test_get_history_filters_by_plan_type(self, user, completed_plan):
        from apps.planner.models import AIPlan
        from django.utils import timezone
        AIPlan.objects.create(
            user=user, plan_date=timezone.now().date(), plan_type='weekly',
            status=PlanStatus.COMPLETED, available_hours=8.0,
        )
        history = list(PlannerService().get_history(user, 'daily'))
        assert all(p.plan_type == 'daily' for p in history)

@pytest.mark.django_db
class TestSerialiseTask:
    def test_serialise_includes_all_fields(self, user, tasks):
        t = tasks[0]
        data = _serialise_task(t)
        assert data['id'] == t.id
        assert data['title'] == t.title
        assert data['priority'] == t.priority
        assert data['status'] == t.status
        assert isinstance(data['tags'], list)
        assert isinstance(data['is_overdue'], bool)

    def test_serialise_overdue_true_for_past_deadline(self, user, overdue_task):
        data = _serialise_task(overdue_task)
        assert data['is_overdue'] is True
        assert data['deadline'] is not None

    def test_serialise_truncates_long_description(self, user):
        from apps.tasks.models import Task
        t = Task.objects.create(
            user=user, title='T',
            description='x' * 500,
            priority='low', status='todo',
        )
        data = _serialise_task(t)
        assert len(data['description']) <= 200

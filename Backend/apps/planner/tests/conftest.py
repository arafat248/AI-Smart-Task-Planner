from __future__ import annotations
import pytest
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.planner.models import AIPlan, PlanStatus
from apps.tasks.models import Category, Tag, Task
User = get_user_model()
TODAY = timezone.now().date().isoformat()

@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='planner@example.com',
        username='planneruser',
        password='testpassword123',
        is_email_verified=True,
    )

@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email='other@example.com',
        username='otherplanner',
        password='testpassword123',
    )
def bearer(u) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(u).access_token}')
    return client

@pytest.fixture
def auth_client(user):
    return bearer(user), user

@pytest.fixture
def other_client(other_user):
    return bearer(other_user), other_user

@pytest.fixture
def tasks(user):
    cat = Category.objects.create(user=user, name='Work', color='#3B82F6')
    tag = Tag.objects.create(user=user, name='important', color='#EF4444')
    t1 = Task.objects.create(
        user=user, title='Write quarterly report',
        priority='high', status='todo',
        estimated_time=timedelta(hours=3),
        deadline=timezone.now() + timedelta(days=1),
        category=cat,
    )
    t1.tags.add(tag)
    t2 = Task.objects.create(
        user=user, title='Review pull requests',
        priority='medium', status='in_progress',
        estimated_time=timedelta(hours=1),
    )
    t3 = Task.objects.create(
        user=user, title='Team standup',
        priority='urgent', status='todo',
        estimated_time=timedelta(minutes=30),
        deadline=timezone.now() + timedelta(hours=6),
    )
    return [t1, t2, t3]

@pytest.fixture
def overdue_task(user):
    return Task.objects.create(
        user=user, title='Overdue task',
        priority='urgent', status='todo',
        deadline=timezone.now() - timedelta(days=2),
        estimated_time=timedelta(hours=2),
    )

@pytest.fixture
def completed_plan(user):
    return AIPlan.objects.create(
        user=user,
        plan_date=TODAY,
        plan_type=AIPlan.PlanType.DAILY,
        status=PlanStatus.COMPLETED,
        available_hours=8.0,
        input_tasks=[
            {'id': 1, 'title': 'Sample task', 'priority': 'high',
             'status': 'todo', 'estimated_minutes': 60, 'is_overdue': False}
        ],
        summary='A productive day ahead.',
        recommended_order=[{
            'task_id': 1, 'title': 'Sample task',
            'rank': 1, 'reason': 'High priority', 'suggested_slot': '9:00-10:00', 'score': 85,
        }],
        time_blocks=[{
            'start': '09:00', 'end': '10:00',
            'title': 'Sample task', 'type': 'work', 'task_id': 1, 'notes': '',
        }],
        break_suggestions=[{
            'after_block': 1, 'time': '10:00',
            'duration_minutes': 10, 'type': 'short', 'reason': 'Rest after deep work',
        }],
        overdue_risk={
            'risk_level': 'low', 'risk_score': 15,
            'at_risk_tasks': [], 'overloaded_days': [],
            'analysis': 'Schedule is healthy.',
        },
        productivity_score={
            'overall': 82, 'focus': 85, 'feasibility': 90,
            'balance': 80, 'urgency_load': 30,
            'advice': ['Take a walk at lunch.', 'Batch similar tasks.', 'Turn off notifications.'],
        },
        tips=['Stay hydrated.', 'Use Pomodoro technique.', 'Review your plan at noon.'],
        generation_ms=1500,
    )

@pytest.fixture
def pending_plan(user):
    return AIPlan.objects.create(
        user=user,
        plan_date=TODAY,
        plan_type=AIPlan.PlanType.DAILY,
        status=PlanStatus.PENDING,
        available_hours=8.0,
        input_tasks=[],
    )

@pytest.fixture
def failed_plan(user):
    return AIPlan.objects.create(
        user=user,
        plan_date=TODAY,
        plan_type=AIPlan.PlanType.DAILY,
        status=PlanStatus.FAILED,
        available_hours=8.0,
        input_tasks=[],
        error_message='OpenAI API quota exceeded.',
    )

from __future__ import annotations
import pytest
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.tasks.models import Category, Tag, Task
User = get_user_model()
NOW  = timezone.now()

@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='dash@example.com', username='dashuser',
        password='pass1234', is_email_verified=True,
    )

@pytest.fixture
def other_user(db):
    return User.objects.create_user(
        email='other@example.com', username='otheruser', password='pass1234',
    )

@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}'
    )
    return client, user

@pytest.fixture
def category(user):
    return Category.objects.create(user=user, name='Work', color='#3B82F6', icon='briefcase')

@pytest.fixture
def tag(user):
    return Tag.objects.create(user=user, name='important', color='#EF4444')

@pytest.fixture
def task_set(user, category, tag):
    """
    Creates a representative set of tasks for dashboard testing.
    Returns a dict of all created tasks so tests can reference them.
    """
    def make(**kwargs):
        t = Task.objects.create(user=user, **kwargs)
        return t

    tasks = {}

    for i in range(3):
        t = make(
            title=f'Completed {i}',
            status='completed',
            priority='high',
            completed_at=NOW - timedelta(days=i),
            category=category,
            estimated_time=timedelta(hours=1),
        )
        t.tags.add(tag)
        tasks[f'completed_{i}'] = t

    tasks['in_progress_0'] = make(
        title='In Progress 0', status='in_progress',
        priority='urgent', estimated_time=timedelta(hours=2),
        deadline=NOW + timedelta(days=1),
    )
    tasks['in_progress_1'] = make(
        title='In Progress 1', status='in_progress',
        priority='medium', estimated_time=timedelta(hours=1),
    )

    tasks['todo_0'] = make(
        title='Todo 0', status='todo',
        priority='low', deadline=NOW + timedelta(days=3),
    )
    tasks['todo_1'] = make(
        title='Todo 1', status='todo',
        priority='high', deadline=NOW + timedelta(hours=12),
    )

    tasks['overdue'] = make(
        title='Overdue task', status='todo',
        priority='urgent',
        deadline=NOW - timedelta(days=2),
    )

    tasks['cancelled'] = make(
        title='Cancelled task', status='cancelled', priority='low',
    )

    deleted = make(title='Deleted task', status='todo', priority='low')
    deleted.soft_delete()
    tasks['deleted'] = deleted

    tasks['ai'] = make(
        title='AI task', status='todo', priority='medium',
        ai_generated=True, deadline=NOW + timedelta(days=5),
    )

    tasks['old_completed'] = make(
        title='Old completed', status='completed',
        priority='low',
        completed_at=NOW - timedelta(days=30),
        estimated_time=timedelta(minutes=30),
    )
    return tasks

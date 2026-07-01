from __future__ import annotations
import pytest
from datetime import date, datetime, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.tasks.models import Category, Tag, Task
User = get_user_model()
NOW  = timezone.now()
TODAY = NOW.date()

@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='cal@example.com', username='caluser',
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
    return Category.objects.create(
        user=user, name='Work', color='#3B82F6', icon='briefcase'
    )

@pytest.fixture
def tag(user):
    return Tag.objects.create(user=user, name='focus', color='#EF4444')

@pytest.fixture
def task_set(user, category, tag):
    def make(**kwargs):
        t = Task.objects.create(user=user, **kwargs)
        return t

    tasks = {}

    tasks['today_todo'] = make(
        title='Today Todo', status='todo', priority='high',
        deadline=NOW.replace(hour=10, minute=0, second=0, microsecond=0),
        estimated_time=timedelta(hours=2), category=category,
    )
    tasks['today_todo'].tags.add(tag)

    tasks['today_inprogress'] = make(
        title='Today In Progress', status='in_progress', priority='urgent',
        deadline=NOW.replace(hour=14, minute=0, second=0, microsecond=0),
        estimated_time=timedelta(hours=1),
    )
    tasks['today_completed'] = make(
        title='Today Completed', status='completed', priority='medium',
        deadline=NOW.replace(hour=9, minute=0, second=0, microsecond=0),
        completed_at=NOW,
    )
    tasks['tomorrow'] = make(
        title='Tomorrow Task', status='todo', priority='medium',
        deadline=NOW + timedelta(days=1),
    )
    tasks['this_week'] = make(
        title='This Week Task', status='todo', priority='low',
        deadline=NOW + timedelta(days=3),
        estimated_time=timedelta(minutes=45),
    )
    tasks['next_week'] = make(
        title='Next Week Task', status='todo', priority='low',
        deadline=NOW + timedelta(days=8),
    )
    tasks['overdue_recent'] = make(
        title='Overdue Recent', status='todo', priority='high',
        deadline=NOW - timedelta(days=2),
    )
    tasks['overdue_old'] = make(
        title='Overdue Old', status='in_progress', priority='urgent',
        deadline=NOW - timedelta(days=10),
    )
    tasks['overdue_but_done'] = make(
        title='Overdue But Done', status='completed', priority='low',
        deadline=NOW - timedelta(days=1),
        completed_at=NOW,
    )
    tasks['no_deadline'] = make(
        title='No Deadline', status='todo', priority='low',
    )
    tasks['recurring'] = make(
        title='Daily Standup', status='todo', priority='medium',
        deadline=NOW.replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1),
        recurrence='daily', estimated_time=timedelta(minutes=30),
    )
    deleted = make(
        title='Deleted Task', status='todo', priority='high',
        deadline=NOW,
    )
    deleted.soft_delete()
    tasks['deleted'] = deleted

    tasks['other_user_task'] = Task.objects.create(
        user=other_user, title='Not mine', status='todo',
        priority='high', deadline=NOW,
    )
    return tasks

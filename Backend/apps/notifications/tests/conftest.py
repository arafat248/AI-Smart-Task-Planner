"""
apps/notifications/tests/conftest.py
Shared fixtures for notification / reminder tests.
"""
from __future__ import annotations
import pytest
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.tasks.models import Task

User = get_user_model()

@pytest.fixture
def user(db):
    return User.objects.create_user(
        email='notif@example.com', username='notifuser',
        password='pass1234', is_email_verified=True,
    )

@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}'
    )
    return client, user

@pytest.fixture
def task_with_deadline(user):
    now = timezone.now()
    return Task.objects.create(
        user=user, title='Task with deadline', status='todo', priority='medium',
        deadline=now + timedelta(days=1),
        reminder_at=now + timedelta(hours=23),
    )

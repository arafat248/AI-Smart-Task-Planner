import pytest
from django.contrib.auth import get_user_model
User = get_user_model()

@pytest.fixture
def user(db):
    """A regular, active, unverified user with a known password."""
    u = User.objects.create_user(
        email='fixture@example.com',
        username='fixtureuser',
        password='testpassword123',
        first_name='Fixture',
        last_name='User',
        is_active=True,
        is_email_verified=False,
    )
    return u

@pytest.fixture
def verified_user(db):
    """A regular, active, verified user."""
    u = User.objects.create_user(
        email='verified@example.com',
        username='verifieduser',
        password='testpassword123',
        is_active=True,
        is_email_verified=True,
    )
    return u

@pytest.fixture
def admin_user(db):
    """A superuser."""
    return User.objects.create_superuser(
        email='admin@example.com',
        username='admin',
        password='adminpass123',
    )

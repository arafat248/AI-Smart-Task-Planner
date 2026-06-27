import pytest
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import (
    EmailVerificationToken,
    PasswordResetToken,
    Profile,
    User,
)

@pytest.mark.django_db
class TestUserModel:
    def test_create_user_uses_email_as_identifier(self):
        user = User.objects.create_user(
            email='test@example.com', username='testuser', password='pass1234'
        )
        assert user.email == 'test@example.com'
        assert str(user) == 'test@example.com'

    def test_email_is_unique(self):
        User.objects.create_user(email='dup@example.com', username='u1', password='pass1234')
        with pytest.raises(Exception):
            User.objects.create_user(email='dup@example.com', username='u2', password='pass1234')

    def test_is_email_verified_defaults_false(self):
        user = User.objects.create_user(
            email='unverified@example.com', username='uv', password='pass1234'
        )
        assert user.is_email_verified is False

    def test_get_full_name_with_names(self):
        user = User(first_name='Alice', last_name='Smith', email='a@b.com', username='a')
        assert user.get_full_name() == 'Alice Smith'

    def test_get_full_name_falls_back_to_email(self):
        user = User(email='fallback@b.com', username='fb')
        assert user.get_full_name() == 'fallback@b.com'


@pytest.mark.django_db
class TestProfileModel:
    def test_profile_created_with_user(self, user):
        assert hasattr(user, 'profile')
        assert isinstance(user.profile, Profile)

    def test_profile_str(self, user):
        assert 'Profile<' in str(user.profile)


@pytest.mark.django_db
class TestEmailVerificationToken:
    def test_is_valid_when_fresh(self, user):
        token = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        assert token.is_valid is True

    def test_is_invalid_when_expired(self, user):
        token = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        assert token.is_valid is False

    def test_is_invalid_when_used(self, user):
        token = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
            is_used=True,
        )
        assert token.is_valid is False

    def test_consume_marks_used(self, user):
        token = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        token.consume()
        token.refresh_from_db()
        assert token.is_used is True


@pytest.mark.django_db
class TestPasswordResetToken:
    def test_is_valid_when_fresh(self, user):
        token = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        assert token.is_valid is True

    def test_consume_marks_used(self, user):
        token = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        token.consume()
        token.refresh_from_db()
        assert token.is_used is True

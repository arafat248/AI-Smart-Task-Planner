import pytest
from unittest.mock import patch, MagicMock
from datetime import timedelta
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from apps.accounts.models import EmailVerificationToken, PasswordResetToken
from apps.accounts.services import (
    AuthService,
    EmailVerificationService,
    PasswordService,
    ProfileService,
)

@pytest.mark.django_db
class TestAuthServiceRegister:
    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_register_creates_user_and_returns_tokens(self, mock_email):
        result = AuthService().register({
            'email': 'alice@example.com',
            'password': 'SecurePass1!',
            'first_name': 'Alice',
            'last_name': 'Smith',
        })
        assert result['user'].email == 'alice@example.com'
        assert 'access' in result
        assert 'refresh' in result
        mock_email.assert_called_once()

    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_register_rejects_duplicate_email(self, mock_email, user):
        with pytest.raises(ValidationError) as exc_info:
            AuthService().register({
                'email': user.email,
                'password': 'SecurePass1!',
            })
        assert 'email' in str(exc_info.value.detail)

    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_register_normalises_email_to_lowercase(self, mock_email):
        result = AuthService().register({
            'email': 'UPPER@Example.COM',
            'password': 'SecurePass1!',
        })
        assert result['user'].email == 'upper@example.com'

@pytest.mark.django_db
class TestAuthServiceLogout:
    def test_logout_blacklists_token(self, user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        AuthService().logout(str(refresh))

    def test_logout_rejects_invalid_token(self):
        with pytest.raises(ValidationError):
            AuthService().logout('not-a-valid-token')

@pytest.mark.django_db
class TestPasswordService:
    def test_change_password_succeeds(self, user):
        PasswordService().change_password(user, 'testpassword123', 'NewSecure1!')
        user.refresh_from_db()
        assert user.check_password('NewSecure1!')

    def test_change_password_rejects_wrong_old_password(self, user):
        with pytest.raises(ValidationError) as exc:
            PasswordService().change_password(user, 'wrongpassword', 'NewSecure1!')
        assert 'old_password' in exc.value.detail

    def test_change_password_rejects_too_short_new_password(self, user):
        with pytest.raises(ValidationError):
            PasswordService().change_password(user, 'testpassword123', 'short')

    @patch('apps.accounts.services.EmailService.send_password_reset_email')
    def test_request_reset_sends_email(self, mock_email, user):
        PasswordService().request_password_reset(user.email)
        mock_email.assert_called_once()

    @patch('apps.accounts.services.EmailService.send_password_reset_email')
    def test_request_reset_silent_for_unknown_email(self, mock_email):
        PasswordService().request_password_reset('nobody@example.com')
        mock_email.assert_not_called()

    def test_reset_password_succeeds_with_valid_token(self, user):
        token_obj = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        PasswordService().reset_password(str(token_obj.token), 'NewSecure1!')
        user.refresh_from_db()
        assert user.check_password('NewSecure1!')
        token_obj.refresh_from_db()
        assert token_obj.is_used is True

    def test_reset_password_rejects_expired_token(self, user):
        token_obj = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with pytest.raises(ValidationError) as exc:
            PasswordService().reset_password(str(token_obj.token), 'NewSecure1!')
        assert 'token' in exc.value.detail

    def test_reset_password_rejects_used_token(self, user):
        token_obj = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
            is_used=True,
        )
        with pytest.raises(ValidationError):
            PasswordService().reset_password(str(token_obj.token), 'NewSecure1!')

    def test_reset_password_rejects_garbage_token(self, user):
        with pytest.raises(ValidationError):
            PasswordService().reset_password('not-a-uuid', 'NewSecure1!')

@pytest.mark.django_db
class TestEmailVerificationService:
    def test_confirm_verifies_user(self, user):
        token_obj = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        verified_user = EmailVerificationService().confirm(str(token_obj.token))
        assert verified_user.is_email_verified is True
        token_obj.refresh_from_db()
        assert token_obj.is_used is True

    def test_confirm_rejects_invalid_token(self):
        with pytest.raises(ValidationError) as exc:
            EmailVerificationService().confirm('00000000-0000-0000-0000-000000000000')
        assert 'token' in exc.value.detail

    def test_confirm_rejects_expired_token(self, user):
        token_obj = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        with pytest.raises(ValidationError):
            EmailVerificationService().confirm(str(token_obj.token))

    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_send_verification_raises_if_already_verified(self, mock_email, user):
        user.is_email_verified = True
        user.save()
        with pytest.raises(ValidationError) as exc:
            EmailVerificationService().send_verification(user)
        assert 'already verified' in str(exc.value.detail).lower()

@pytest.mark.django_db
class TestProfileService:
    def test_update_user_fields(self, user):
        updated = ProfileService().update(user, {'first_name': 'Bob'}, {})
        assert updated.first_name == 'Bob'

    def test_update_profile_fields(self, user):
        updated = ProfileService().update(user, {}, {'timezone': 'US/Eastern', 'bio': 'Hello'})
        updated.profile.refresh_from_db()
        assert updated.profile.timezone == 'US/Eastern'
        assert updated.profile.bio == 'Hello'

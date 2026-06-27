import pytest
from unittest.mock import patch
from datetime import timedelta
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from apps.accounts.models import EmailVerificationToken, PasswordResetToken

def make_client(user=None) -> APIClient:
    client = APIClient()
    if user:
        refresh = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client

@pytest.mark.django_db
class TestRegisterView:
    URL = '/api/auth/register/'

    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_success_returns_201_with_tokens(self, mock_email):
        client = APIClient()
        r = client.post(self.URL, {
            'email': 'new@example.com',
            'password': 'SecurePass1!',
            'first_name': 'New',
        })
        assert r.status_code == status.HTTP_201_CREATED
        data = r.data['data']
        assert 'access' in data
        assert 'refresh' in data
        assert data['user']['email'] == 'new@example.com'
        mock_email.assert_called_once()

    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_duplicate_email_returns_400(self, mock_email, user):
        client = APIClient()
        r = client.post(self.URL, {'email': user.email, 'password': 'SecurePass1!'})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_weak_password_returns_400(self):
        r = APIClient().post(self.URL, {'email': 'weak@example.com', 'password': '123'})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_missing_email_returns_400(self):
        r = APIClient().post(self.URL, {'password': 'SecurePass1!'})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
class TestLoginView:
    URL = '/api/auth/login/'

    def test_valid_credentials_return_tokens(self, user):
        r = APIClient().post(self.URL, {'email': user.email, 'password': 'testpassword123'})
        assert r.status_code == status.HTTP_200_OK
        data = r.data
        assert 'access' in data
        assert 'refresh' in data

    def test_wrong_password_returns_401(self, user):
        r = APIClient().post(self.URL, {'email': user.email, 'password': 'wrong'})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unknown_email_returns_401(self):
        r = APIClient().post(self.URL, {'email': 'ghost@example.com', 'password': 'pass'})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
class TestTokenRefresh:
    URL = '/api/auth/token/refresh/'

    def test_valid_refresh_returns_new_access(self, user):
        refresh = str(RefreshToken.for_user(user))
        r = APIClient().post(self.URL, {'refresh': refresh})
        assert r.status_code == status.HTTP_200_OK
        assert 'access' in r.data

    def test_invalid_refresh_returns_401(self):
        r = APIClient().post(self.URL, {'refresh': 'invalid'})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
class TestLogoutView:
    URL = '/api/auth/logout/'

    def test_logout_blacklists_token(self, user):
        refresh = RefreshToken.for_user(user)
        client = make_client(user)
        r = client.post(self.URL, {'refresh': str(refresh)})
        assert r.status_code == status.HTTP_204_NO_CONTENT

    def test_logout_requires_authentication(self):
        r = APIClient().post(self.URL, {'refresh': 'token'})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_logout_rejects_invalid_token(self, user):
        client = make_client(user)
        r = client.post(self.URL, {'refresh': 'garbage'})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
class TestChangePasswordView:
    URL = '/api/auth/change-password/'

    def test_success(self, user):
        client = make_client(user)
        r = client.post(self.URL, {
            'old_password': 'testpassword123',
            'new_password': 'NewSecure1!',
            'new_password_confirm': 'NewSecure1!',
        })
        assert r.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password('NewSecure1!')

    def test_wrong_old_password(self, user):
        r = make_client(user).post(self.URL, {
            'old_password': 'wrong',
            'new_password': 'NewSecure1!',
            'new_password_confirm': 'NewSecure1!',
        })
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_mismatched_new_passwords(self, user):
        r = make_client(user).post(self.URL, {
            'old_password': 'testpassword123',
            'new_password': 'NewSecure1!',
            'new_password_confirm': 'Different1!',
        })
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_unauthenticated_returns_401(self):
        r = APIClient().post(self.URL, {})
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

@pytest.mark.django_db
class TestForgotPasswordView:
    URL = '/api/auth/forgot-password/'

    @patch('apps.accounts.services.EmailService.send_password_reset_email')
    def test_known_email_sends_email_returns_200(self, mock_email, user):
        r = APIClient().post(self.URL, {'email': user.email})
        assert r.status_code == status.HTTP_200_OK
        mock_email.assert_called_once()

    @patch('apps.accounts.services.EmailService.send_password_reset_email')
    def test_unknown_email_returns_200_no_email(self, mock_email):
        r = APIClient().post(self.URL, {'email': 'nobody@example.com'})
        assert r.status_code == status.HTTP_200_OK
        mock_email.assert_not_called()

    def test_invalid_email_format_returns_400(self):
        r = APIClient().post(self.URL, {'email': 'not-an-email'})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
class TestResetPasswordView:
    URL = '/api/auth/reset-password/'

    def test_valid_token_resets_password(self, user):
        token_obj = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        r = APIClient().post(self.URL, {
            'token': str(token_obj.token),
            'new_password': 'NewSecure1!',
            'new_password_confirm': 'NewSecure1!',
        })
        assert r.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password('NewSecure1!')

    def test_expired_token_returns_400(self, user):
        token_obj = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        r = APIClient().post(self.URL, {
            'token': str(token_obj.token),
            'new_password': 'NewSecure1!',
            'new_password_confirm': 'NewSecure1!',
        })
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_mismatched_passwords_returns_400(self, user):
        token_obj = PasswordResetToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        r = APIClient().post(self.URL, {
            'token': str(token_obj.token),
            'new_password': 'NewSecure1!',
            'new_password_confirm': 'Different1!',
        })
        assert r.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
class TestVerifyEmailView:
    URL = '/api/auth/verify-email/'

    def test_valid_token_verifies_user(self, user):
        token_obj = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() + timedelta(hours=24),
        )
        r = APIClient().post(self.URL, {'token': str(token_obj.token)})
        assert r.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_email_verified is True

    def test_expired_token_returns_400(self, user):
        token_obj = EmailVerificationToken.objects.create(
            user=user,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        r = APIClient().post(self.URL, {'token': str(token_obj.token)})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

    def test_garbage_token_returns_400(self):
        r = APIClient().post(self.URL, {'token': 'not-a-uuid'})
        assert r.status_code == status.HTTP_400_BAD_REQUEST

@pytest.mark.django_db
class TestResendVerificationView:
    URL = '/api/auth/resend-verification/'

    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_unverified_user_gets_email(self, mock_email, user):
        assert not user.is_email_verified
        r = APIClient().post(self.URL, {'email': user.email})
        assert r.status_code == status.HTTP_200_OK
        mock_email.assert_called_once()

    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_already_verified_no_email(self, mock_email, user):
        user.is_email_verified = True
        user.save()
        r = APIClient().post(self.URL, {'email': user.email})
        assert r.status_code == status.HTTP_200_OK
        mock_email.assert_not_called()

    @patch('apps.accounts.services.EmailService.send_verification_email')
    def test_unknown_email_returns_200(self, mock_email):
        r = APIClient().post(self.URL, {'email': 'nobody@example.com'})
        assert r.status_code == status.HTTP_200_OK
        mock_email.assert_not_called()

@pytest.mark.django_db
class TestMeView:
    URL = '/api/auth/me/'

    def test_get_returns_user_data(self, user):
        r = make_client(user).get(self.URL)
        assert r.status_code == status.HTTP_200_OK
        data = r.data['data']
        assert data['email'] == user.email
        assert 'profile' in data

    def test_unauthenticated_returns_401(self):
        r = APIClient().get(self.URL)
        assert r.status_code == status.HTTP_401_UNAUTHORIZED

    def test_patch_updates_first_name(self, user):
        r = make_client(user).patch(self.URL, {'first_name': 'Updated'})
        assert r.status_code == status.HTTP_200_OK
        assert r.data['data']['first_name'] == 'Updated'

    def test_patch_updates_profile_timezone(self, user):
        r = make_client(user).patch(self.URL, {'timezone': 'US/Pacific'})
        assert r.status_code == status.HTTP_200_OK
        assert r.data['data']['profile']['timezone'] == 'US/Pacific'

    def test_patch_updates_bio(self, user):
        r = make_client(user).patch(self.URL, {'bio': 'Hello world'})
        assert r.status_code == status.HTTP_200_OK
        assert r.data['data']['profile']['bio'] == 'Hello world'

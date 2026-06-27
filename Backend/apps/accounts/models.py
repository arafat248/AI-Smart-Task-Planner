from __future__ import annotations
import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from core.mixins import TimestampMixin

class User(AbstractUser, TimestampMixin):
    email = models.EmailField(_('email address'), unique=True)
    is_email_verified = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        db_table = 'accounts_user'
        ordering = ['-date_joined']
        verbose_name = _('user')
        verbose_name_plural = _('users')

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        full = f'{self.first_name} {self.last_name}'.strip()
        return full or self.email


class Profile(TimestampMixin):
    """Extended user preferences and display data."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar_url = models.URLField(blank=True)
    timezone = models.CharField(max_length=64, default='UTC')
    bio = models.CharField(max_length=300, blank=True)
    preferences = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'accounts_profile'

    def __str__(self) -> str:
        return f'Profile<{self.user.email}>'


class EmailVerificationToken(TimestampMixin):
    """
    One-time token sent to the user's email to verify their address.
    Expires after EMAIL_VERIFICATION_TIMEOUT seconds (default 24 h).
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='email_verification_tokens'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'accounts_emailverificationtoken'
        ordering = ['-created_at']

    @property
    def is_valid(self) -> bool:
        return not self.is_used and timezone.now() < self.expires_at

    def consume(self) -> None:
        self.is_used = True
        self.save(update_fields=['is_used'])

    def __str__(self) -> str:
        return f'EmailToken<{self.user.email} valid={self.is_valid}>'


class PasswordResetToken(TimestampMixin):
    """
    Secure token emailed to the user for password reset.
    Single-use, expires after PASSWORD_RESET_TIMEOUT seconds (default 1 h).
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='password_reset_tokens'
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    is_used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'accounts_passwordresettoken'
        ordering = ['-created_at']

    @property
    def is_valid(self) -> bool:
        return not self.is_used and timezone.now() < self.expires_at

    def consume(self) -> None:
        self.is_used = True
        self.save(update_fields=['is_used'])

    def __str__(self) -> str:
        return f'PasswordReset<{self.user.email} valid={self.is_valid}>'

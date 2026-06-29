from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Any
from django.conf import settings

logger = logging.getLogger(__name__)

class PushProvider(ABC):
    """Abstract push notification provider."""

    @abstractmethod
    def send(self, user, title: str, body: str, data: dict[str, Any]) -> dict:
        """
        Send a push notification to a single user.
        Returns a dict with at minimum:
          { 'success': bool, 'provider': str }
        May also include:
          { 'error': str, 'retryable': bool, 'message_id': str }
        """
        ...

    @abstractmethod
    def send_bulk(self, users, title: str, body: str, data: dict[str, Any]) -> dict:
        """Send a push to multiple users. Returns aggregate stats."""
        ...

class NoOpProvider(PushProvider):
    """Logs the push but does nothing. Safe default for local dev."""

    def send(self, user, title: str, body: str, data: dict[str, Any]) -> dict:
        logger.info(
            '[NoOpProvider] Would send to user=%d: title=%r body=%r data=%r',
            getattr(user, 'id', None), title, body, data,
        )
        return {'success': True, 'provider': 'noop', 'message_id': None}

    def send_bulk(self, users, title: str, body: str, data: dict[str, Any]) -> dict:
        logger.info(
            '[NoOpProvider] Would send to %d users: title=%r',
            len(users), title,
        )
        return {'success': True, 'provider': 'noop', 'sent_count': len(users)}

class FCMProvider(PushProvider):
    def __init__(self):
        self._app = None
        self._messaging = None
        self._init()

    def _init(self):
        try:
            import firebase_admin
            from firebase_admin import credentials, messaging
        except ImportError:
            logger.error('firebase-admin is not installed. Run: pip install firebase-admin')
            return

        creds_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', None)
        if not creds_path:
            logger.warning('FIREBASE_CREDENTIALS_PATH not set — FCMProvider will be no-op')
            return

        try:
            cred = credentials.Certificate(creds_path)
            self._app = firebase_admin.initialize_app(cred, name='ai_task_planner_fcm')
            self._messaging = messaging
            logger.info('FCMProvider initialised successfully')
        except Exception as exc:
            logger.error('FCMProvider init failed: %s', exc)

    def _get_tokens(self, user) -> list[str]:
        """Extract FCM registration tokens from the user object."""
        # Option A: user.fcm_tokens is a JSONField list of strings
        tokens = getattr(user, 'fcm_tokens', None)
        if isinstance(tokens, list):
            return [t for t in tokens if isinstance(t, str) and t]
        # Option B: user has a related fcmdevice_set (django-fcm style)
        if hasattr(user, 'fcmdevice_set'):
            return list(user.fcmdevice_set.filter(active=True).values_list('token', flat=True))
        return []

    def send(self, user, title: str, body: str, data: dict[str, Any]) -> dict:
        if self._messaging is None:
            logger.warning('FCMProvider not initialised — push dropped')
            return {'success': False, 'provider': 'fcm', 'error': 'not_initialised', 'retryable': False}

        tokens = self._get_tokens(user)
        if not tokens:
            logger.debug('FCMProvider: no tokens for user %d', user.id)
            return {'success': False, 'provider': 'fcm', 'error': 'no_tokens', 'retryable': False}

        message = self._messaging.MulticastMessage(
            notification=self._messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in data.items()},
            tokens=tokens,
        )

        try:
            response = self._messaging.send_each_for_multicast(message, app=self._app)
            success = response.success_count > 0
            # Remove invalid tokens
            if response.failure_count > 0:
                invalid = [tokens[i] for i, r in enumerate(response.responses) if not r.success]
                self._invalidate_tokens(user, invalid)

            return {
                'success': success,
                'provider': 'fcm',
                'sent_count': response.success_count,
                'failure_count': response.failure_count,
                'retryable': False,
            }
        except Exception as exc:
            logger.exception('FCM send failed for user %d: %s', user.id, exc)
            return {'success': False, 'provider': 'fcm', 'error': str(exc), 'retryable': True}

    def send_bulk(self, users, title: str, body: str, data: dict[str, Any]) -> dict:
        total_sent = 0
        total_fail = 0
        for user in users:
            result = self.send(user, title, body, data)
            total_sent += result.get('sent_count', 0)
            total_fail += result.get('failure_count', 0)
        return {
            'success': total_fail == 0,
            'provider': 'fcm',
            'sent_count': total_sent,
            'failure_count': total_fail,
        }

    def _invalidate_tokens(self, user, invalid_tokens: list[str]):
        """Remove dead FCM tokens from the user's token list."""
        current = self._get_tokens(user)
        cleaned = [t for t in current if t not in invalid_tokens]
        if hasattr(user, 'fcm_tokens') and isinstance(user.fcm_tokens, list):
            user.fcm_tokens = cleaned
            user.save(update_fields=['fcm_tokens'])
        elif hasattr(user, 'fcmdevice_set'):
            user.fcmdevice_set.filter(token__in=invalid_tokens).update(active=False)

_PROVIDER_MAP: dict[str, type[PushProvider]] = {
    'noop': NoOpProvider,
    'fcm':  FCMProvider,
}

def get_push_provider() -> PushProvider:
    provider_name = getattr(settings, 'PUSH_PROVIDER', 'noop')
    cls = _PROVIDER_MAP.get(provider_name, NoOpProvider)
    return cls()

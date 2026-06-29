"""
apps/notifications/views.py

Notification + Reminder views.

Endpoints:
  GET  /api/notifications/              → list (last 30)
  PATCH /api/notifications/<id>/read/   → mark one read
  POST /api/notifications/mark-all-read/ → mark all read
  GET  /api/reminders/upcoming/         → upcoming reminders
  GET  /api/reminders/overdue/          → overdue tasks
  GET  /api/reminders/history/          → reminder history
"""
from __future__ import annotations
import logging

from django.shortcuts import get_object_or_404
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from core.permissions import IsOwner
from .models import Notification
from .reminder_services import ReminderManager
from .serializers import (
    NotificationSerializer,
    ReminderHistorySerializer,
    ReminderTaskSerializer,
)
from .services import NotificationService

logger = logging.getLogger(__name__)
TAG = ['notifications']

def _rl_key(group, request):
    if request.user.is_authenticated:
        return f'u:{request.user.id}'
    return request.META.get('REMOTE_ADDR', 'unknown')

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=TAG, summary='List notifications')
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def get(self, request):
        notifs = Notification.objects.filter(user=request.user).order_by('-created_at')[:30]
        return Response(NotificationSerializer(notifs, many=True).data)

class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=TAG, summary='Mark notification as read')
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    def patch(self, request, pk):
        notif = get_object_or_404(Notification, id=pk, user=request.user)
        NotificationService().mark_read(notif)
        return Response(NotificationSerializer(notif).data)

class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(tags=TAG, summary='Mark all notifications as read')
    @ratelimit(key=_rl_key, rate='10/m', block=True)
    def post(self, request):
        count = NotificationService().mark_all_read(request.user)
        return Response({'marked_read': count})

class ReminderViewSet(ViewSet):
    """Read-only reminders view."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=['reminders'],
        summary='Upcoming reminders',
        description='Tasks with a reminder scheduled in the next 24 hours.',
        responses={200: ReminderTaskSerializer(many=True)},
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=False, methods=['get'], url_path='upcoming')
    def upcoming(self, request):
        data = ReminderManager().upcoming(request.user, hours=24)
        return Response(ReminderTaskSerializer(data, many=True).data)

    @extend_schema(
        tags=['reminders'],
        summary='Overdue tasks',
        description='All overdue tasks for the current user.',
        responses={200: ReminderTaskSerializer(many=True)},
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=False, methods=['get'], url_path='overdue')
    def overdue(self, request):
        data = ReminderManager().overdue(request.user)
        return Response(ReminderTaskSerializer(data, many=True).data)

    @extend_schema(
        tags=['reminders'],
        summary='Reminder history',
        description='Past reminder notifications (sent + read).',
        responses={200: ReminderHistorySerializer(many=True)},
    )
    @ratelimit(key=_rl_key, rate='60/m', block=True)
    @action(detail=False, methods=['get'], url_path='history')
    def history(self, request):
        data = ReminderManager().history(request.user, limit=30)
        return Response(ReminderHistorySerializer(data, many=True).data)

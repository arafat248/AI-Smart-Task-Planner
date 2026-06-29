from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import NotificationListView, NotificationReadView, MarkAllReadView, ReminderViewSet

router = DefaultRouter()
router.register('reminders', ReminderViewSet, basename='reminder')

urlpatterns = [
    path('notifications/', NotificationListView.as_view(), name='notifications-list'),
    path('notifications/<int:pk>/read/', NotificationReadView.as_view(), name='notifications-read'),
    path('notifications/mark-all-read/', MarkAllReadView.as_view(), name='notifications-mark-all'),
    path('', include(router.urls)),
]

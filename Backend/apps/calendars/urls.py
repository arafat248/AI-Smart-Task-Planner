from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import CalendarViewSet

router = DefaultRouter()
router.register('calendar/events', CalendarViewSet, basename='calendar')

urlpatterns = [path('', include(router.urls))]

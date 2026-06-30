from django.urls import include, path
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, TagViewSet, TaskViewSet

router = DefaultRouter()
router.register('tasks', TaskViewSet, basename='task')
router.register('categories', CategoryViewSet, basename='category')
router.register('tags', TagViewSet, basename='tag')

urlpatterns = [path('', include(router.urls))]

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeacherViewSet, StudentViewSet, RoomViewSet, ScheduleViewSet

router = DefaultRouter()
router.register(r'teachers', TeacherViewSet)
router.register(r'students', StudentViewSet)
router.register(r'rooms', RoomViewSet)
router.register(r'schedule', ScheduleViewSet, basename='schedule')

urlpatterns = [
    path('', include(router.urls)),
]
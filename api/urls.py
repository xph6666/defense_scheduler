from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AuthLogoutView, AuthChangePasswordView, AuthLoginView, OperationLogViewSet, RoomViewSet, RuleConfigViewSet, ScheduleViewSet, StudentViewSet, TeacherViewSet

router = DefaultRouter()
router.register(r'teachers', TeacherViewSet)
router.register(r'students', StudentViewSet)
router.register(r'rooms', RoomViewSet)
router.register(r'rule-config', RuleConfigViewSet, basename='rule-config')
router.register(r'operation-logs', OperationLogViewSet, basename='operation-logs')
router.register(r'schedule', ScheduleViewSet, basename='schedule')

urlpatterns = [
    path('auth/logout/', AuthLogoutView.as_view(), name='auth-logout'),
    path('auth/login/', AuthLoginView.as_view(), name='auth-login'),
    path('auth/change-password/', AuthChangePasswordView.as_view(), name='auth-change-password'),
    path(
        'operation-logs/',
        OperationLogViewSet.as_view({
            'get': 'list',
            'post': 'create',
            'delete': 'clear',
        }),
        name='operation-logs-list',
    ),
    path('', include(router.urls)),
]

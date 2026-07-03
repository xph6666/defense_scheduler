from rest_framework.permissions import BasePermission, SAFE_METHODS


def is_admin_user(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


class IsAdminOrReadOnly(BasePermission):
    message = '需要管理员权限'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return is_admin_user(request.user)


class IsAdminUser(BasePermission):
    message = '需要管理员权限'

    def has_permission(self, request, view):
        return is_admin_user(request.user)

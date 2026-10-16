from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed, Throttled


class ExpiringTokenAuthentication(TokenAuthentication):
    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if token.created + timedelta(hours=settings.AUTH_TOKEN_TTL_HOURS) <= timezone.now():
            token.delete()
            raise AuthenticationFailed('登录已过期，请重新登录')
        return user, token


def login_attempt_key(request, username):
    # No clear-text usernames or passwords in cache keys.
    raw = f'{request.META.get("REMOTE_ADDR", "")}:{username}'
    return 'login-failures:' + sha256(raw.encode()).hexdigest()


def check_login_attempts(key):
    if cache.get(key, 0) >= 10:
        raise Throttled(wait=300, detail='登录失败次数过多，请稍后再试')


def record_login_failure(key):
    if not cache.add(key, 1, timeout=300):
        try:
            cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=300)

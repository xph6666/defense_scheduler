from datetime import timedelta
from hashlib import sha256

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed, Throttled


class LocalPasswordlessAuthentication(BaseAuthentication):
    """Allow the desktop user to enter directly, only over loopback."""

    def authenticate_header(self, request):
        # DRF uses the first authenticator's challenge for all failed logins.
        # Preserve token clients' 401 contract when loopback access is ineligible.
        return 'Token'

    def authenticate(self, request):
        from urllib.parse import urlsplit
        from django.contrib.auth import get_user_model

        loopback = {'127.0.0.1', '::1', 'localhost'}
        if request.META.get('REMOTE_ADDR') not in {'127.0.0.1', '::1'}:
            return None
        if urlsplit('http://' + request.get_host()).hostname not in loopback:
            return None
        # A browser request from another site must not gain local privileges.
        for header in ('HTTP_ORIGIN', 'HTTP_REFERER'):
            source = request.META.get(header)
            if source and urlsplit(source).netloc != request.get_host():
                return None
        if request.META.get('HTTP_SEC_FETCH_SITE') == 'cross-site':
            return None

        user, created = get_user_model().objects.get_or_create(
            username='local-admin',
            defaults={'is_staff': True, 'is_superuser': True},
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=['password'])
        return user, None


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

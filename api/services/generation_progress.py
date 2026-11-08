"""Request-scoped generation checkpoints, readable while the write transaction runs."""
from contextvars import ContextVar
from functools import wraps
from hashlib import sha256

from django.core.cache import cache
from rest_framework.response import Response

_reporter = ContextVar('schedule_progress', default=None)
TTL = 20 * 60


def progress_key(user_id, request_key):
    return 'schedule-progress:' + sha256(f'{user_id}:{request_key}'.encode()).hexdigest()


def report_progress(stage, message, percent, defense_type=None):
    callback = _reporter.get()
    if callback:
        callback(stage, message, percent, defense_type)


def track_generation(fn):
    """Wrap the transaction: 100% is only reported after a successful commit."""
    @wraps(fn)
    def wrapped(self, request, *args, **kwargs):
        key = request.data.get('request_key')
        if not isinstance(key, str) or not key or len(key) > 64:
            return fn(self, request, *args, **kwargs)
        cache_key = progress_key(request.user.pk, key)
        linked = fn.__name__ == 'generate_linked'

        def report(stage, message, percent, defense_type=None):
            if linked and defense_type:
                percent = (percent / 2) + (50 if defense_type == 'formal' else 0)
            cache.set(cache_key, {
                'stage': stage, 'message': message, 'percent': round(percent),
                'defenseType': defense_type, 'status': 'running',
            }, TTL)

        token = _reporter.set(report)
        report('waiting', '等待编排资源', 0)
        try:
            response = fn(self, request, *args, **kwargs)
            failed = response.status_code >= 400
            previous = cache.get(cache_key) or {}
            cache.set(cache_key, {**previous, 'status': 'failed' if failed else 'completed',
                'stage': 'failed' if failed else 'completed',
                'message': str(response.data.get('error', '生成失败')) if failed else '草稿已保存，编排完成',
                'percent': previous.get('percent', 0) if failed else 100}, TTL)
            return response
        except Exception:
            previous = cache.get(cache_key) or {}
            cache.set(cache_key, {**previous, 'status': 'failed', 'stage': 'failed',
                                 'message': '生成失败，请查看请求返回的错误'}, TTL)
            raise
        finally:
            _reporter.reset(token)
    return wrapped


def read_progress(user_id, key):
    if not isinstance(key, str) or not key or len(key) > 64:
        return Response({'error': '请求标识格式不正确'}, status=400)
    return Response(cache.get(progress_key(user_id, key)) or {
        'status': 'waiting', 'stage': 'waiting', 'percent': 0, 'message': '等待服务开始编排',
    })

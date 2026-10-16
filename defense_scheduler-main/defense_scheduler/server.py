"""Shared production WSGI entry point for Windows source and desktop builds."""
import os


def serve_application(host='127.0.0.1', port=8000):
    from waitress import serve
    from .wsgi import application
    options = dict(host=host, port=port, threads=8, max_request_body_size=6 * 1024 * 1024,
                   channel_timeout=180, expose_tracebacks=False)
    proxy = os.environ.get('DJANGO_TRUSTED_PROXY')
    if proxy:
        options.update(trusted_proxy=proxy, trusted_proxy_headers={'x-forwarded-proto'}, trusted_proxy_count=1)
    serve(application, **options)


if __name__ == '__main__':
    serve_application(os.environ.get('DEFENSE_SCHEDULER_HOST', '127.0.0.1'),
                      int(os.environ.get('DEFENSE_SCHEDULER_PORT', '8000')))

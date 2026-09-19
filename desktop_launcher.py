import os
import socket
import threading
import webbrowser

from defense_scheduler.runtime import configure_local_runtime, ensure_initial_admin


DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8000


def should_open_browser() -> bool:
    value = os.environ.get('DEFENSE_SCHEDULER_OPEN_BROWSER', 'true').strip().lower()
    return value not in {'0', 'false', 'no', 'off'}


def select_listen_port(host: str, preferred_port: int) -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, preferred_port))
        return preferred_port
    except OSError:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((host, 0))
            return int(probe.getsockname()[1])


def get_preferred_port() -> int:
    raw_port = os.environ.get('DEFENSE_SCHEDULER_PORT', str(DEFAULT_PORT))
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError('DEFENSE_SCHEDULER_PORT must be an integer') from exc
    if not 1 <= port <= 65535:
        raise ValueError('DEFENSE_SCHEDULER_PORT must be between 1 and 65535')
    return port


def main() -> None:
    runtime_config = configure_local_runtime()
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'defense_scheduler.settings')

    import django
    from django.core.management import call_command

    django.setup()
    from django.conf import settings
    from pathlib import Path
    from defense_scheduler.backup import backup_sqlite
    database_path = Path(settings.DATABASES['default']['NAME'])
    if settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3' and database_path.exists():
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            backup_sqlite(database_path, runtime_config.app_data_dir / 'backups')
    call_command('migrate', interactive=False, verbosity=1)
    credentials = ensure_initial_admin(runtime_config.app_data_dir)

    host = os.environ.get('DEFENSE_SCHEDULER_HOST', DEFAULT_HOST)
    port = select_listen_port(host, get_preferred_port())
    url = f'http://{host}:{port}'
    print(f'智能答辩分组编排系统已启动: {url}')
    print(f'数据目录: {runtime_config.app_data_dir}')
    if credentials:
        print(f'首次管理员账号: {credentials.username}')
        print(f'首次管理员密码已写入: {credentials.credentials_file}')

    if should_open_browser():
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    from defense_scheduler.server import serve_application
    serve_application(host, port)


if __name__ == '__main__':
    main()

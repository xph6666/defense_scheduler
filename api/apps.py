from django.apps import AppConfig
from django.db import DatabaseError
from django.db.backends.signals import connection_created


def _configure_sqlite(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    name = str(connection.settings_dict.get('NAME') or '')
    if not name or name == ':memory:' or 'mode=memory' in name or 'mode=ro' in name:
        return
    try:
        with connection.cursor() as cursor:
            cursor.execute('PRAGMA busy_timeout=30000;')
            mode = cursor.execute('PRAGMA journal_mode;').fetchone()
            if mode and str(mode[0]).lower() != 'wal':
                cursor.execute('PRAGMA journal_mode=WAL;')
            cursor.execute('PRAGMA synchronous=NORMAL;')
    except DatabaseError:
        pass


class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        connection_created.connect(_configure_sqlite, dispatch_uid='api_configure_sqlite')

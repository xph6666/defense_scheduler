from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from defense_scheduler.backup import backup_sqlite


class Command(BaseCommand):
    help = 'Create and verify a timestamped SQLite backup, including the application signing key.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default=None)

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        if db['ENGINE'] != 'django.db.backends.sqlite3':
            raise CommandError('PostgreSQL 请使用 pg_dump，并按运维文档保存应用密钥')
        try:
            source = Path(db['NAME'])
            output = backup_sqlite(source, options['output'] or source.parent / 'backups')
            (output / 'secret.key').write_text(settings.SECRET_KEY, encoding='utf-8')
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Backup verified: {output}'))

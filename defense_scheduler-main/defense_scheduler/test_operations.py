import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase
from .backup import backup_sqlite
from .env import load_env


class OperationalSafetyTests(SimpleTestCase):
    def test_backup_restores_committed_data_and_passes_integrity_check(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.sqlite3'
            with closing(sqlite3.connect(source)) as db, db:
                db.execute('CREATE TABLE sample (value TEXT)')
                db.execute('INSERT INTO sample VALUES (?)', ['before-upgrade'])
            folder = backup_sqlite(source, Path(temp) / 'backups')
            with closing(sqlite3.connect(source)) as db, db:
                db.execute('DELETE FROM sample')
            # Open the saved database separately: verifies a real recovery source,
            # without overwriting an active database.
            with closing(sqlite3.connect(folder / 'db.sqlite3')) as restored:
                self.assertEqual(restored.execute('SELECT value FROM sample').fetchone()[0], 'before-upgrade')
                self.assertEqual(restored.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertTrue((folder / 'manifest.json').is_file())

    def test_env_loading_preserves_explicit_environment_and_literal_values(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'REVIEW_EXISTING': 'process'}):
            path = Path(temp) / '.env'
            path.write_text('REVIEW_EXISTING=file\nREVIEW_LITERAL="$(literal)#value"\n', encoding='utf-8')
            load_env(path)
            self.assertEqual(os.environ['REVIEW_EXISTING'], 'process')
            self.assertEqual(os.environ['REVIEW_LITERAL'], '$(literal)#value')

"""Consistent SQLite backups; never copy an open database file directly."""
import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


def backup_sqlite(source, destination_root):
    source = Path(source).resolve()
    if not source.is_file():
        raise ValueError('数据库文件不存在')
    directory = Path(destination_root).resolve() / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    directory.mkdir(parents=True, exist_ok=False)
    output = directory / 'db.sqlite3'
    source_uri = source.as_uri() + '?mode=ro'
    with closing(sqlite3.connect(source_uri, uri=True)) as origin:
        with closing(sqlite3.connect(output)) as target:
            origin.backup(target)
            if target.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('备份数据库完整性检查失败')
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    (directory / 'manifest.json').write_text(json.dumps({
        'created_at': datetime.now(timezone.utc).isoformat(), 'database_sha256': digest,
        'source': str(source), 'integrity_check': 'ok',
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    return directory

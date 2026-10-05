#!/usr/bin/env python3
"""Create and integrity-check a private SQLite snapshot for local evaluation."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

for line in (ROOT / '.env').read_text().splitlines() if (ROOT / '.env').exists() else []:
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

def resolve(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path

def main() -> None:
    source_path = resolve(os.environ.get('DATABASE_PATH', 'marketplace.sqlite3'))
    backup_dir = resolve(os.environ.get('BACKUP_DIR', 'backups'))
    if not source_path.is_file():
        raise SystemExit(f'Database file not found: {source_path}')
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = backup_dir / f'bozorgg-{timestamp}.sqlite3'
    temporary = target.with_suffix('.sqlite3.tmp')
    source = sqlite3.connect(f'file:{source_path.resolve()}?mode=ro', uri=True)
    destination = sqlite3.connect(temporary)
    try:
        source.backup(destination)
        result = destination.execute('PRAGMA integrity_check').fetchone()
        if not result or result[0] != 'ok':
            raise RuntimeError(f'Backup integrity check failed: {result[0] if result else "no result"}')
    finally:
        destination.close()
        source.close()
    temporary.chmod(0o600)
    os.replace(temporary, target)
    target.chmod(0o600)
    print(f'Backup created and verified: {target}')

if __name__ == '__main__':
    main()

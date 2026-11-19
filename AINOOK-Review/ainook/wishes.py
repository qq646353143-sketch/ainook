"""Shared click totals with idempotent batch writes."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3


class Wishes:
    def __init__(self, path, platforms):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.platforms = frozenset(platforms)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS totals(platform TEXT PRIMARY KEY, total INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS batches(platform TEXT, batch_id TEXT, amount INTEGER NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(platform,batch_id));
            ''')
            db.executemany('INSERT OR IGNORE INTO totals VALUES(?,0)', [(p,) for p in self.platforms])

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    def totals(self):
        with self.connect() as db:
            return {key: total for key, total in db.execute('SELECT platform,total FROM totals') if key in self.platforms}

    def add(self, platform, amount, batch_id):
        if not isinstance(platform, str) or platform not in self.platforms or type(amount) is not int or not 1 <= amount <= 200:
            raise ValueError('点击批次无效')
        if not isinstance(batch_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{16,100}', batch_id):
            raise ValueError('批次标识无效')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT amount FROM batches WHERE platform=? AND batch_id=?', (platform, batch_id)).fetchone()
            if old and old[0] != amount:
                raise ValueError('同一批次不能更改点击数')
            if not old:
                db.execute('INSERT INTO batches VALUES(?,?,?,?)', (platform, batch_id, amount, datetime.now(timezone.utc).isoformat()))
                db.execute('UPDATE totals SET total=total+? WHERE platform=?', (amount, platform))
            total = db.execute('SELECT total FROM totals WHERE platform=?', (platform,)).fetchone()[0]
        return {'platform': platform, 'total': total, 'accepted': amount, 'duplicate': bool(old)}

"""Validate the content team's current issue before promoting it to the cloud build."""

import json
from datetime import datetime, time
import os
from pathlib import Path
import re
from runpy import run_path
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ainook.news_edition import NewsEdition
from ainook.quota import BEIJING, utcnow, write_snapshot
from ainook.reset_feed import fetch_json

REPOSITORY = 'qq646353143-sketch/ainook'
RAW = f'https://raw.githubusercontent.com/{REPOSITORY}'
URL = f'{RAW}/main/data/latest.json'
SOURCE = ROOT.parent / 'data/latest.json'
TARGET = ROOT / 'published/reader-cloud.json'
PUBLISH_TIME = time(8, 45)


def load_edition(path):
    validate = run_path(str(ROOT.parent / 'scripts/sync_edition.py'))['validate']
    _, count = validate(path.read_text(encoding='utf-8-sig'))
    return NewsEdition(path), count


def publish_time(edition):
    return max(edition.updated, datetime.combine(edition.updated.date(), PUBLISH_TIME, BEIJING))


def previous_edition(upcoming, backup, now, fetch=fetch_json):
    # The synced GitHub copy can lag if Actions missed its schedule. Use versioned source history.
    revision = os.environ.get('WORKERS_CI_COMMIT_SHA', '')
    params = urlencode({'path': 'data/latest.json', 'per_page': 10,
                        'sha': revision if re.fullmatch(r'[0-9a-f]{40}', revision) else 'main'})
    commits = fetch(f'https://api.github.com/repos/{REPOSITORY}/commits?{params}')
    if not isinstance(commits, list):
        raise ValueError('Cannot read the edition history')
    with TemporaryDirectory() as temporary:
        path = Path(temporary) / 'reader-edition.json'
        for commit in commits:
            sha = commit.get('sha', '') if isinstance(commit, dict) else ''
            if not re.fullmatch(r'[0-9a-f]{40}', sha):
                continue
            try:
                write_snapshot(path, fetch(f'{RAW}/{sha}/data/latest.json'))
                edition, _ = load_edition(path)
            except (OSError, ValueError, TypeError, KeyError):
                continue
            if edition.updated < upcoming.updated and publish_time(edition) <= now:
                if not backup or backup.updated <= edition.updated:
                    return edition
                break
    if backup and publish_time(backup) <= now:
        return backup
    raise ValueError('No valid earlier edition is available')


def build_editions(source=SOURCE, backup_path=TARGET, *, now=None, fetch=fetch_json):
    now = now or utcnow()
    edition, _ = load_edition(source)
    backup = load_edition(backup_path)[0] if backup_path.is_file() else None
    if backup and backup.updated > edition.updated:
        raise ValueError('Source edition is older than the synced copy')
    release = publish_time(edition)
    if release <= now:
        return edition, None, None
    previous = previous_edition(edition, backup if backup and publish_time(backup) <= now else None, now, fetch)
    return previous, edition, release


def sync():
    data = fetch_json(URL)
    with TemporaryDirectory() as temporary:
        candidate = Path(temporary) / 'reader-edition.json'
        write_snapshot(candidate, data)
        incoming, count = load_edition(candidate)
        if TARGET.exists():
            if incoming.updated < NewsEdition(TARGET).updated:
                raise ValueError('新下载的刊次比线上旧，保留当前刊次')
            if data == json.loads(TARGET.read_text(encoding='utf-8-sig')):
                print(f'Cloud news edition unchanged ({count} items)')
                return
        write_snapshot(TARGET, data)
        print(f'Cloud news edition published: {incoming.updated.isoformat()} ({count} items)')


if __name__ == '__main__':
    sync()

"""Validate the content team's current issue before promoting it to the cloud build."""

import json
from pathlib import Path
from runpy import run_path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ainook.news_edition import NewsEdition
from ainook.quota import write_snapshot
from ainook.reset_feed import fetch_json

URL = 'https://raw.githubusercontent.com/qq646353143-sketch/ainook/main/data/latest.json'
TARGET = ROOT / 'published/reader-cloud.json'


def sync():
    data = fetch_json(URL)
    validate = run_path(str(ROOT.parent / 'scripts/sync_edition.py'))['validate']
    _, count = validate(json.dumps(data, ensure_ascii=False))
    with TemporaryDirectory() as temporary:
        candidate = Path(temporary) / 'reader-edition.json'
        write_snapshot(candidate, data)
        incoming = NewsEdition(candidate)
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

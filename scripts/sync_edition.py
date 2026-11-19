# -*- coding: utf-8 -*-
"""从固定地址拉取《AI 每日速递》，校验后原子替换 reader-edition.json。

用法：
    EDITION_URL=https://example.com/latest.json python3 scripts/sync_edition.py

行为约定：
    - 拉取或校验失败时，绝不改动现有文件，直接以非零码退出。
    - 校验通过才写入，且先写临时文件再原子替换，避免读到半个文件。
"""
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / 'outputs' / 'ainook' / 'reader-edition.json'
MIN_ITEMS = 30          # 低于这个条数视为异常，不替换
TIMEOUT = 20

def fetch(url):
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
        return response.read().decode('utf-8')

def validate(text):
    data = json.loads(text)
    meta = data.get('meta') or {}
    if meta.get('timezone') != 'Asia/Shanghai':
        raise ValueError('meta.timezone 必须是 Asia/Shanghai')
    items = list(data.get('news') or []) + list(data.get('gossip') or [])
    if len(items) < MIN_ITEMS:
        raise ValueError('条数不足：%d' % len(items))
    ids = [item.get('id') for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError('资讯标识重复')
    bad = [item.get('id') for item in items if not item.get('u', '').startswith(('http://', 'https://'))]
    if bad:
        raise ValueError('原链接无效：%s' % bad[:3])
    return data, len(items)

def main():
    url = os.environ.get('EDITION_URL', '').strip()
    if not url.startswith(('http://', 'https://')):
        print('未设置 EDITION_URL，保持现有数据不动', file=sys.stderr)
        return 1
    try:
        text = fetch(url)
        _, count = validate(text)
    except Exception as error:
        print('同步失败，保留旧文件：%s' % error, file=sys.stderr)
        return 1
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=str(TARGET.parent), suffix='.tmp')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            out.write(text)
        os.replace(temp, TARGET)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    print('已更新 %d 条：%s' % (count, TARGET))
    return 0

if __name__ == '__main__':
    sys.exit(main())

"""Read the supplied AI Daily Dispatch edition without modifying the live news database."""
from datetime import datetime, timedelta
from hashlib import sha256
import json
from urllib.parse import urlsplit

from .quota import BEIJING

EDITION_FILE = 'reader-edition.json'
EDITIONS = {'/news': '精选简报', '/news/model': '模型更新', '/news/official': '官方公告',
            '/news/hot': '行业热点', '/news/world': '国际新闻', '/news/finance': '全球财经',
            '/rumors': '小道消息'}
CATEGORIES = {label: path.lstrip('/') for path, label in EDITIONS.items() if path.startswith('/news/')}
LEGACY_SECTIONS = {'/news/ai': '/news/model', '/updates': '/news/model',
                   '/official': '/news/official', '/hot': '/news/hot'}


def source_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
            or '\\' in value or any(ord(char) < 32 for char in value)):
        raise ValueError('原文链接无效')
    return value


class NewsEdition:
    def __init__(self, path):
        self.path = path
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        metadata = data['meta']
        if metadata['timezone'] != 'Asia/Shanghai':
            raise ValueError('导入的时间必须为北京时间')
        self.updated = datetime.fromisoformat(metadata['updated']).replace(tzinfo=BEIJING)
        self.sources = {}
        self.items = {}
        for name in ('news', 'gossip'):
            for raw in data[name]:
                item = self.read(raw, is_gossip=name == 'gossip')
                if item['id'] in self.items:
                    raise ValueError('资讯标识重复')
                self.items[item['id']] = item
                label = item['source']
                self.sources[label] = {'id': label, 'name': label}
        self.ordered = sorted(self.items.values(), key=lambda item: item['published_at'], reverse=True)

    def read(self, raw, *, is_gossip):
        timestamp = datetime.strptime(f"{self.updated.year}-{raw['d']}", '%Y-%m-%d %H:%M').replace(tzinfo=BEIJING)
        if timestamp.month == 12 and self.updated.month == 1:
            timestamp = timestamp.replace(year=timestamp.year - 1)
        if timestamp > self.updated:
            raise ValueError('资讯时间晚于刊次更新时间')
        title, summary, label = raw['t'], raw['s'], raw['n']
        body = raw['chat' if is_gossip else 'p']
        if not all(isinstance(value, str) and value.strip() for value in (title, summary, label, raw['id'])):
            raise ValueError('资讯缺少标题、摘要、来源或标识')
        if not isinstance(body, list) or not body or not all(isinstance(value, str) and value.strip() for value in body):
            raise ValueError('资讯缺少正文段落')
        identifier = sha256(('reader-edition:' + raw['id']).encode()).hexdigest()[:24]
        item = {
            'id': identifier, 'edition_id': raw['id'], 'title': title, 'summary': summary, 'body': body,
            'source': label, 'url': source_url(raw['u']), 'published_at': timestamp.isoformat(),
            'translation': 'imported', 'unverified': is_gossip,
            # Legacy or unregistered categories remain readable in the unfiltered edition.
            'section': 'rumors' if is_gossip else CATEGORIES.get(raw['c'], 'news'),
        }
        if is_gossip:
            if not all(isinstance(raw[key], str) for key in ('q', 'who')):
                raise ValueError('原话或人物信息格式不正确')
            item.update(quote=raw['q'], quote_credit=raw['who'])
        return item

    def article(self, identifier):
        return self.items.get(identifier)

    def articles(self, *, mode, query, source, days, offset):
        cutoff = None if days == 'all' else self.updated - timedelta(days=int(days))
        needle = query.casefold()
        rows = []
        for item in self.ordered:
            if mode != 'news' and item['section'] != mode:
                continue
            if source and item['source'] != source:
                continue
            if cutoff and datetime.fromisoformat(item['published_at']) < cutoff:
                continue
            if needle not in ' '.join((item['title'], item['summary'], item['source'], *item['body'])).casefold():
                continue
            rows.append(item)
        return rows[offset:offset + 20], len(rows)

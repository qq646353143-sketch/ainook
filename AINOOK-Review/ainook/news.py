"""Bounded collection from a fixed list of AI feeds and official release notes."""
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import sqlite3
import threading
from urllib.error import HTTPError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from easel.intelligence.collect import Document, PrimaryBody, changelog, clean, rich_feed
from easel.intelligence.model import canonical_url, normalize_time

from .news_events import additional_excerpt, event_attention, evidence_sentences, group_events, is_model_update, representative
from .news_copy import TRUNCATED, evidence_copy, reading_copy, select_reading_facts, useful_brief
from .quota import BEIJING, VendorRedirect, instant, utcnow

SOURCE_FILE = Path(__file__).with_name('news-sources.json')
TRANSLATION_METHOD = 'offline_v2'
MAX_BYTES = 8 * 1024 * 1024
USER_AGENT = 'AINOOKNews/1.0 (+public feed reader)'
AI = re.compile(r'\b(?:AI|LLMs?|GPT|OpenAI|Anthropic|DeepSeek|Gemini|Claude|Codex|ChatGPT|Copilot|Grok|xAI|Llama|Qwen|Hugging Face)\b|人工智能|大模型|语言模型|智能体', re.I)
MODEL = re.compile(r'\b(?:models?|GPT[- ]?\d|Gemini [\d.]+|Claude (?:Opus|Sonnet|Haiku|[\d.]+)|DeepSeek[ -][VR]\d|Grok [\d.]+|Llama \d|Qwen[\w.-]*)\b|模型', re.I)
RELEASE = re.compile(r'\b(?:launch\w*|new|introduc\w*|releas\w*|updat\w*|availab\w*|deprecat\w*|retir\w*|roll(?:ing)? out)\b|发布|更新|上线|开放|下线|推出|新增|停用', re.I)
IMPACT = re.compile(r'\b(?:rate limits?|quotas?|credits?|reset\w*|pricing|subscription\w*|outage\w*|security|vulnerabilit\w*|breach\w*|data leak|acqui[rs]\w*|merger\w*|antitrust|export controls?|resign\w*|appoint\w*|breakthrough\w*)\b|额度|限额|重置|赠送|价格|订阅|故障|安全|泄露|收购|合并|出口管制|辞职|任命|突破', re.I)
PERSON_ROLE = re.compile(r'\b(?:CEO|CTO|co-founder|founder|chief scientist)\b|创始人|首席科学家|首席执行官', re.I)
PERSON_NEWS = re.compile(r'\b(?:warn\w*|steps down|stepp\w* down|leaves|joins)\b|离职|警告|加入', re.I)
OPEN_TECH = re.compile(r'\b(?:open.source|researchers develop|new architecture|benchmark suite)\b|开源|新架构|评测基准', re.I)
UNCERTAIN = re.compile(r'\b(?:rumou?r(?:s|ed)?|reportedly|unconfirmed|allegedly|in talks|leaked (?:roadmap|model|benchmark|specs))\b|传闻|据传|爆料|未经证实|尚未证实', re.I)
LOW_VALUE = re.compile(r'^(?:how to\b|a guide to\b|show hn:|ask hn:)|\b(?:roundup|weekly digest|sponsored|buying guide|performance improvements and bug fixes|pay for .+ account)\b|每周汇总|付费推广|购买指南|常规修复', re.I)
CLI_PATCH = re.compile(r'^(?:codex|copilot|claude code)\s+(?:cli\s+)?v?0\.\d+\.\d+$', re.I)
SEARCH_METHODS = frozenset({'hn_search', 'gdelt_search'})
SCHEMA = '''
CREATE TABLE IF NOT EXISTS articles (
  id TEXT PRIMARY KEY, identity TEXT NOT NULL UNIQUE, title TEXT NOT NULL, title_key TEXT NOT NULL,
  summary TEXT NOT NULL, url TEXT NOT NULL, published TEXT NOT NULL, original_time TEXT NOT NULL,
  source TEXT NOT NULL, label TEXT NOT NULL, kind TEXT NOT NULL, language TEXT NOT NULL,
  is_model INTEGER NOT NULL, archived INTEGER NOT NULL, content_key TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS news_dates ON articles(published DESC);
CREATE INDEX IF NOT EXISTS news_titles ON articles(title_key, published);
CREATE TABLE IF NOT EXISTS article_signals (
  article_id TEXT PRIMARY KEY, priority INTEGER NOT NULL,
  hot INTEGER NOT NULL, unverified INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS event_representatives (
  article_id TEXT PRIMARY KEY, winner_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS event_winner ON event_representatives(winner_id);
CREATE TABLE IF NOT EXISTS event_attention (
  article_id TEXT PRIMARY KEY, evidence_count INTEGER NOT NULL, weight REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS news_heat (
  url TEXT PRIMARY KEY, points INTEGER NOT NULL, thread TEXT NOT NULL, checked TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS translation_retry (
  content_key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, next_at TEXT
);
CREATE TABLE IF NOT EXISTS excerpt_checks (
  article_id TEXT PRIMARY KEY, state TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS article_reading (
  article_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, body TEXT,
  state TEXT NOT NULL, checked_at TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0, next_at TEXT
);
CREATE TABLE IF NOT EXISTS daily_briefing (
  day TEXT NOT NULL, position INTEGER NOT NULL, article_id TEXT NOT NULL,
  PRIMARY KEY(day, position)
);
CREATE TABLE IF NOT EXISTS article_aliases (id TEXT PRIMARY KEY, article_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS translations (
  content_key TEXT PRIMARY KEY, title TEXT NOT NULL, summary TEXT NOT NULL,
  method TEXT NOT NULL, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS translation_briefs (
  content_key TEXT PRIMARY KEY, brief TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS source_state (
  id TEXT PRIMARY KEY, url TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending', error TEXT,
  attempted_at TEXT, success_at TEXT, etag TEXT, modified TEXT, hold_until TEXT,
  limits INTEGER NOT NULL DEFAULT 0, added INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS collection_log (
  sequence INTEGER PRIMARY KEY, source TEXT NOT NULL, at TEXT NOT NULL,
  state TEXT NOT NULL, detail TEXT NOT NULL, added INTEGER NOT NULL
);
'''


class Blocked(ValueError):
    pass


def content_key(title, summary):
    return sha256((title + '\0' + summary).encode()).hexdigest()


def text(value, limit):
    return re.sub(r'\s+', ' ', str(value or '').replace('\u200b', '')).strip()[:limit].rstrip()


def excerpt(value, limit):
    content = text(value, limit + 1)
    return content if len(content) <= limit else content[:limit - 1].rstrip() + '…'


def signals(title, summary, kind, is_model):
    material = title + ' ' + summary
    unverified = kind == 'lead' or (kind != 'official' and bool(UNCERTAIN.search(material if kind == 'voice' else title)))
    impact = bool(IMPACT.search(material) or (PERSON_ROLE.search(material) and PERSON_NEWS.search(title)))
    if LOW_VALUE.search(title) or (CLI_PATCH.fullmatch(title) and not (impact or is_model)):
        return 0, 0, int(unverified)
    major = bool(is_model or impact or (OPEN_TECH.search(title) and AI.search(material)))
    priority = {'official': 30, 'media': 16, 'platform': 14, 'voice': 18, 'lead': 8}.get(kind, 12)
    priority += 34 * int(bool(is_model)) + 28 * int(impact)
    return priority, int(major and not unverified), int(unverified)


def record(source, entry, now, *, archived=False, legacy_id=None):
    title = text(entry.get('title'), 501)
    raw_summary = str(entry.get('summary') or '').replace('\u200b', '')
    summary = evidence_copy(raw_summary, source.get('excerpt_limit', 520 if source['kind'] == 'media' else 1350))
    raw_time = entry.get('raw_time') or ''
    normalized = normalize_time(raw_time, now=now)
    published = normalized.get('utc') or normalized.get('date')
    if not title or len(title) > 500 or not published or published[:10] > now.astimezone(BEIJING).date().isoformat():
        return None
    if len(published) > 10 and instant(published) > now:
        return None
    if source.get('ai_only') and not AI.search(title + ' ' + summary):
        return None
    raw_url = entry.get('url') or ''
    url = canonical_url(raw_url)
    if not url:
        return None
    if source['method'] == 'changelog':
        key = url + '\0' + published + '\0' + title
    else:
        key = urlunsplit(urlsplit(url)._replace(fragment=''))
        if source['kind'] == 'lead':
            key = 'lead:' + key
    title_key = re.sub(r'[\W_]+', '', title.casefold())
    chinese = len(re.findall(r'[\u3400-\u9fff]', title))
    language = 'zh' if source.get('language') == 'zh' or chinese >= max(3, len(title) // 4) else 'en'
    return (
        legacy_id or sha256(key.encode()).hexdigest()[:24], key, title, title_key, summary, url, published,
        raw_time[:120], source['id'], source['name'], source['kind'], language,
        int(is_model_update(title, summary)),
        int(archived), content_key(title, summary),
    )


def search_url(source):
    keyword = source['keyword']
    if source['method'] == 'hn_search':
        earliest = int((utcnow() - timedelta(days=3)).timestamp())
        params = {'query': keyword, 'tags': 'story', 'hitsPerPage': 12,
                  'numericFilters': f'created_at_i>{earliest},points>{source.get("min_points", 10)}'}
    else:
        params = {'query': keyword, 'mode': 'ArtList', 'format': 'json', 'maxrecords': 8, 'timespan': '3d'}
    return source['url'] + '?' + urlencode(params)


def search_entries(source, raw):
    data = json.loads(raw)
    hn = source['method'] == 'hn_search'
    entries = data['hits' if hn else 'articles']
    results = []
    for item in entries[:12]:
        title, link = item.get('title'), item.get('url')
        url = canonical_url(link or '')
        if not title or not url or not (IMPACT.search(title) or (MODEL.search(title) and RELEASE.search(title))
                                        or (AI.search(title) and UNCERTAIN.search(title))):
            continue
        if hn:
            stamp = item.get('created_at')
        else:
            try:
                stamp = datetime.strptime(item['seendate'], '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc).isoformat()
            except (KeyError, TypeError, ValueError):
                continue
        entry = {'title': title, 'url': url, 'raw_time': stamp}
        if hn and type(item.get('points')) is int and str(item.get('objectID')).isdigit():
            entry.update(points=item['points'], thread='https://news.ycombinator.com/item?id=' + str(item['objectID']))
        results.append(entry)
    return results


def author_entries(source, raw):
    entries = []
    for item in json.loads(raw)['feed'][:12]:
        post = item.get('post') or {}
        profile = post.get('author') or {}
        record = post.get('record') or {}
        content = str(record.get('text') or '').strip()
        if profile.get('did') != source['actor'] or item.get('reason') or not AI.search(content):
            continue
        uri = post.get('uri', '')
        prefix = 'at://' + source['actor'] + '/app.bsky.feed.post/'
        if not uri.startswith(prefix) or not re.fullmatch(r'[A-Za-z0-9._~-]+', uri[len(prefix):]):
            continue
        author = source['name'].split(' · ', 1)[0]
        title = f'{author} · {reading_copy(content)[0]}'
        parent = (item.get('reply') or {}).get('parent') or {}
        parent_path = str(parent.get('uri', '')).split('/')
        if len(parent_path) == 5 and parent_path[3] == 'app.bsky.feed.post' and re.fullmatch(r'did:[A-Za-z0-9:.-]+', parent_path[2]) and re.fullmatch(r'[A-Za-z0-9._~-]+', parent_path[4]):
            parent_url = f'https://bsky.app/profile/{parent_path[2]}/post/{parent_path[4]}'
        else:
            parent_url = None
        entries.append({'title': title, 'summary': content, 'raw_time': record.get('createdAt', ''),
                        'url': f'https://bsky.app/profile/{source["actor"]}/post/{uri[len(prefix):]}',
                        'reply_parent': parent_url})
    return entries


def github_entries(raw):
    return [{'title': release.get('name') or release.get('tag_name'), 'url': release.get('html_url'),
             'summary': release.get('body'), 'raw_time': release.get('published_at')}
            for release in json.loads(raw)[:12] if not release.get('draft') and release.get('published_at')]


class StopRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def allowed_opener(url, redirects=(), *, follow=True):
    origin = urlsplit(url)
    opener = build_opener(VendorRedirect({origin.hostname, *redirects}) if follow else StopRedirect())
    robots = RobotFileParser()
    try:
        req = Request(f'https://{origin.netloc}/robots.txt', headers={'User-Agent': USER_AGENT})
        with opener.open(req, timeout=10) as response:
            raw_robots = limit_body(response, 256 * 1024)
            check_challenge(raw_robots)
            robots.parse(raw_robots.decode('utf-8', errors='replace').splitlines())
            if not robots.can_fetch(USER_AGENT, url):
                raise Blocked('robots.txt 禁止采集')
    except HTTPError as error:
        if error.code not in (404, 410):
            raise
    return opener


def checked_fetch(source, state):
    searching = source['method'] in SEARCH_METHODS
    url = search_url(source) if searching else source['url']
    if source['method'] == 'bluesky':
        url += '?' + urlencode({'actor': source['actor'], 'limit': 12, 'filter': 'posts_with_replies'})
    elif source['method'] == 'github_releases':
        url += '?per_page=12'
    opener = allowed_opener(url, source.get('redirect_hosts', []))
    headers = {'User-Agent': USER_AGENT, 'Accept': '*/*',
               'Accept-Encoding': 'gzip'}
    if state.get('etag') and not searching:
        headers['If-None-Match'] = state['etag']
    if state.get('modified') and not searching:
        headers['If-Modified-Since'] = state['modified']
    with opener.open(Request(url, headers=headers), timeout=15) as response:
        raw = limit_body(response, MAX_BYTES)
        final = response.url
        meta = {'etag': response.headers.get('ETag'), 'modified': response.headers.get('Last-Modified')}
    check_challenge(raw)
    if searching:
        return search_entries(source, raw), {}
    if source['method'] == 'bluesky':
        return author_entries(source, raw), meta
    if source['method'] == 'github_releases':
        return github_entries(raw), meta
    if source['method'] == 'rss':
        return rich_feed(raw, final), meta
    return changelog(raw, final), meta


def read_article_material(url, redirects=()):
    def download(address):
        opener = allowed_opener(address, follow=False)
        request = Request(address, headers={'User-Agent': USER_AGENT, 'Accept-Encoding': 'gzip'})
        with opener.open(request, timeout=9) as response:
            return limit_body(response, 4 * 1024 * 1024)

    try:
        raw = download(url)
    except HTTPError as error:
        target = urljoin(url, error.headers.get('Location', ''))
        parsed = urlsplit(target)
        if (error.code not in (301, 302, 307, 308) or parsed.scheme != 'https'
                or parsed.hostname not in {urlsplit(url).hostname, *redirects} or parsed.port not in (None, 443)
                or parsed.username or parsed.password or target == url):
            raise
        raw = download(target)
    check_challenge(raw)
    markup = raw.decode('utf-8', errors='replace')
    primary = PrimaryBody(('blog-content', 'editorial-content-block'))
    primary.feed(markup)
    body = ''.join(primary.chunks)
    if not body:
        article = re.search(r'<article\b[^>]*>([\s\S]*?)</article>', markup, re.I)
        body = article[1] if article else ''
    paragraphs = (re.sub(r'\s+', ' ', clean(part)).strip()
                  for _, part in re.findall(r'<(p|li)\b[^>]*>([\s\S]*?)</\1>', body, re.I))
    useful = [part for part in paragraphs if len(part) >= 52]
    if useful:
        return evidence_copy('\n\n'.join(useful[:24]), 6800)
    metadata = Document()
    metadata.feed(markup)
    return evidence_copy(metadata.meta.get('og:description') or metadata.meta.get('description') or '', 500)


def limit_body(response, maximum):
    raw = response.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('响应大小超出上限')
    if raw[:2] == b'\x1f\x8b':
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as archive:
            raw = archive.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('响应大小超出上限')
    return raw


def check_challenge(raw):
    start = raw[:2500].lower()
    if re.search(rb'<title[^>]*>[^<]*(?:just a moment|access denied|verify.*human|captcha)', start) or b'cf-chl-' in start:
        raise Blocked('来源返回验证码或访问验证')


def retry_time(header, now, fallback):
    try:
        if header and header.isdecimal():
            return now + timedelta(seconds=max(3600, int(header)))
        if header:
            return max(now + timedelta(hours=1), parsedate_to_datetime(header).astimezone(now.tzinfo))
    except (OverflowError, TypeError, ValueError):
        pass
    return now + fallback


class News:
    def __init__(self, directory, *, config_path=SOURCE_FILE):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'news.sqlite3'
        self.config = json.loads(Path(config_path).read_text(encoding='utf-8'))
        self.sources = {source['id']: source for source in self.config['sources']}
        self.interval = timedelta(hours=self.config['interval_hours'])
        self.lock = threading.Lock()
        with closing(self.connect()) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript(SCHEMA)
            db.execute('CREATE TABLE IF NOT EXISTS article_context (article_id TEXT PRIMARY KEY, reply_url TEXT NOT NULL)')
            db.executemany('INSERT OR IGNORE INTO source_state(id,url) VALUES (?,?)',
                           [(key, source['url']) for key, source in self.sources.items()])
            if db.execute('PRAGMA user_version').fetchone()[0] < 2:
                rows = db.execute('SELECT id,title,summary,kind FROM articles').fetchall()
                for identifier, title, summary, kind in rows:
                    model = is_model_update(title, summary)
                    db.execute('UPDATE articles SET is_model=? WHERE id=?', (model, identifier))
                    db.execute('INSERT OR REPLACE INTO article_signals VALUES (?,?,?,?)',
                               (identifier, *signals(title, summary, kind, model)))
                db.execute("UPDATE source_state SET etag=NULL,modified=NULL,attempted_at=NULL WHERE id IN ('google-ai','huggingface') AND state NOT IN ('disabled','rate_limited')")
                db.execute("DELETE FROM excerpt_checks WHERE state='ValueError' AND article_id IN (SELECT id FROM articles WHERE source='deepmind')")
                db.execute('PRAGMA user_version=2')
            if db.execute('PRAGMA user_version').fetchone()[0] < 3:
                db.execute("DELETE FROM translation_retry WHERE content_key IN (SELECT content_key FROM translations WHERE method='failed')")
                db.execute("""DELETE FROM excerpt_checks WHERE state='ok' AND article_id IN
                            (SELECT id FROM articles WHERE summary LIKE '%…' OR length(summary)<360)""")
                db.execute('PRAGMA user_version=3')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def save_article(self, db, row):
        if row is None:
            return False
        flags = signals(row[2], row[4], row[10], row[12])
        if not flags[0] and not row[13]:
            return False
        previous = db.execute('SELECT id,title,summary,source FROM articles WHERE identity=?', (row[1],)).fetchone()
        if previous:
            old_summary = previous['summary']
            if (not row[13] and previous['source'] == row[8] and len(row[4]) > len(old_summary)
                    and (previous['title'] == row[2] or row[10] == 'voice')
                    and (TRUNCATED.search(old_summary) or text(row[4], len(old_summary)) == text(old_summary, len(old_summary)))):
                db.execute('UPDATE articles SET title=?,title_key=?,summary=?,is_model=?,content_key=? WHERE id=?',
                           (row[2], row[3], row[4], row[12], row[14], previous['id']))
                db.execute('UPDATE article_signals SET priority=?,hot=?,unverified=? WHERE article_id=?',
                           (*flags, previous['id']))
            return False
        if row[10] == 'lead' and db.execute('SELECT 1 FROM articles WHERE identity=?',
                                          (row[1].removeprefix('lead:'),)).fetchone():
            return False
        if len(row[3]) >= 14 and self.duplicate_title(db, row):
            return False
        added = db.execute('INSERT OR IGNORE INTO articles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', row).rowcount
        if added:
            db.execute('INSERT INTO article_signals VALUES (?,?,?,?)', (row[0], *flags))
        return bool(added)

    def duplicate_title(self, db, row):
        return db.execute('''
            SELECT id FROM articles WHERE title_key=? AND abs(julianday(published)-julianday(?)) < 3
            AND (kind <> 'lead' OR ?) LIMIT 1
        ''', (row[3], row[6], row[10] == 'lead')).fetchone()

    def source_result(self, key, state, status, detail, now, *, meta=None, added=0, **updates):
        data = {**state, **updates, 'state': status, 'error': detail, 'attempted_at': now.isoformat(), 'added': added}
        if status in ('ok', 'unchanged'):
            data.update(meta or {}, success_at=now.isoformat(), limits=0, hold_until=None)
        fields = ('state', 'error', 'attempted_at', 'success_at', 'etag', 'modified', 'hold_until', 'limits', 'added')
        with closing(self.connect()) as db, db:
            db.execute('UPDATE source_state SET ' + ','.join(f'{field}=?' for field in fields) + ' WHERE id=?',
                       (*[data.get(field) for field in fields], key))
            db.execute('INSERT INTO collection_log(source,at,state,detail,added) VALUES (?,?,?,?,?)',
                       (key, now.isoformat(), status, detail or '', added))
        return {'id': key, 'state': status, 'added': added, 'detail': detail}

    def collect_source(self, source, state, now, fetch):
        key = source['id']
        try:
            entries, meta = fetch(source, state)
            if not entries and source['method'] not in SEARCH_METHODS and source['method'] not in ('bluesky', 'github_releases'):
                raise ValueError('来源没有可识别的条目')
            earliest = (now - timedelta(days=self.config['initial_days'])).date().isoformat()
            rows = [(row, entry) for entry in entries if (row := record(source, entry, now)) and row[6][:10] >= earliest]
            rows.sort(key=lambda pair: pair[0][6], reverse=True)
            limit = self.config['entries_per_source']
            if not state.get('success_at'):
                limit = min(limit, source.get('initial_limit', limit))
            with closing(self.connect()) as db, db:
                db.execute('BEGIN IMMEDIATE')
                added = 0
                for row, entry in rows[:limit]:
                    if 'points' in entry:
                        db.execute('''INSERT INTO news_heat VALUES (?,?,?,?)
                                      ON CONFLICT(url) DO UPDATE SET points=excluded.points,
                                      thread=excluded.thread, checked=excluded.checked''',
                                   (row[1].removeprefix('lead:'), entry['points'], entry['thread'], now.isoformat()))
                    if source['method'] in SEARCH_METHODS:
                        continue
                    if source.get('important_only') and not signals(row[2], row[4], row[10], row[12])[1]:
                        continue
                    if self.save_article(db, row):
                        added += 1
                        if entry.get('reply_parent'):
                            db.execute('INSERT INTO article_context VALUES (?,?)', (row[0], entry['reply_parent']))
        except Blocked as error:
            return self.source_result(key, state, 'disabled', str(error), now)
        except HTTPError as error:
            if error.code == 304:
                return self.source_result(key, state, 'unchanged', None, now)
            if error.code in (401, 403, 451):
                return self.source_result(key, state, 'disabled', f'HTTP {error.code}，来源拒绝访问', now)
            if error.code == 429:
                hits = state.get('limits', 0) + 1
                wait = retry_time(error.headers.get('Retry-After') if error.headers else None, now, self.interval)
                return self.source_result(key, state, 'disabled' if hits >= 2 else 'rate_limited',
                                          'HTTP 429，来源限流', now, limits=hits, hold_until=wait.isoformat())
            return self.source_result(key, state, 'error', f'HTTP {error.code}', now)
        except Exception as error:
            return self.source_result(key, state, 'error', type(error).__name__, now)
        return self.source_result(key, state, 'ok', None, now, meta=meta, added=added)

    def collect(self, *, force=False, fetch=checked_fetch):
        with self.lock:
            now = utcnow()
            with closing(self.connect()) as db:
                states = {row['id']: dict(row) for row in db.execute('SELECT * FROM source_state')}
            todo = []
            for key, source in self.sources.items():
                state = states[key]
                if not source['enabled'] or state['state'] == 'disabled':
                    continue
                if (hold := instant(state['hold_until'])) and hold > now:
                    continue
                attempted = instant(state['attempted_at'])
                if not force and attempted and now - attempted < self.interval:
                    continue
                todo.append((source, state))
            with ThreadPoolExecutor(max_workers=3) as workers:
                def collect_one(pair):
                    return self.collect_source(*pair, now, fetch)
                regular = [pair for pair in todo if pair[0]['method'] not in SEARCH_METHODS]
                discovery = [pair for pair in todo if pair[0]['method'] in SEARCH_METHODS]
                results = list(workers.map(collect_one, regular))
                return results + list(workers.map(collect_one, discovery))

    def statuses(self):
        with closing(self.connect()) as db:
            states = {row['id']: dict(row) for row in db.execute('SELECT * FROM source_state')}
            recent = [dict(row) for row in db.execute('SELECT * FROM collection_log ORDER BY sequence DESC LIMIT 40')]
        return [{**states[key], **source} for key, source in self.sources.items()], recent

    def merge_events(self):
        now = utcnow()
        owners = {key: source.get('owner') for key, source in self.sources.items()}
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('''
                SELECT a.id,a.title,a.source,a.summary,a.kind,a.published,a.url,h.points
                FROM articles a JOIN article_signals s ON s.article_id=a.id
                LEFT JOIN news_heat h ON h.url=a.identity AND julianday(h.checked)>=julianday('now','-7 days')
                WHERE a.archived=0 AND s.priority>0 AND s.unverified=0 AND a.kind<>'voice'
                ORDER BY a.published,a.id
            ''')
            mapping = {}
            attention = {}
            for members in group_events(rows):
                winner = representative(members)['id']
                mapping.update((member['id'], winner) for member in members)
                evidence_count, weight = event_attention(members, owners, now)
                if weight:
                    attention[winner] = (evidence_count, weight)
            if mapping != dict(db.execute('SELECT article_id,winner_id FROM event_representatives')):
                db.execute('DELETE FROM event_representatives')
                db.executemany('INSERT INTO event_representatives VALUES (?,?)', mapping.items())
            prior_attention = {row[0]: tuple(row[1:]) for row in db.execute('SELECT * FROM event_attention')}
            if prior_attention != attention:
                db.execute('DELETE FROM event_attention')
                db.executemany('INSERT INTO event_attention VALUES (?,?,?)',
                               ((identifier, *metrics) for identifier, metrics in attention.items()))
        return sum(article != winner for article, winner in mapping.items())

    def enrich_articles(self, *, fetch=read_article_material, limit=8):
        trusted = {source['id']: source for source in self.sources.values()
                   if source.get('article_host') and source['enabled']}
        if not trusted:
            return 0
        cutoff = (utcnow() - timedelta(days=7)).date().isoformat()
        placeholders = ','.join('?' for _ in trusted)
        with closing(self.connect()) as db:
            rows = db.execute(f'''
                SELECT a.id,a.source,a.url,a.title,a.summary,a.language FROM articles a
                LEFT JOIN article_reading material ON material.article_id=a.id
                LEFT JOIN event_representatives e ON e.article_id=a.id
                JOIN source_state ss ON ss.id=a.source
                LEFT JOIN translations t ON t.content_key=a.content_key
                JOIN article_signals s ON s.article_id=a.id
                WHERE a.archived=0 AND a.published>=? AND s.priority>0 AND s.unverified=0
                AND material.article_id IS NULL
                AND (e.winner_id IS NULL OR e.winner_id=a.id)
                AND ss.state NOT IN ('disabled','rate_limited') AND coalesce(t.method,'') <> 'reviewed'
                AND a.source IN ({placeholders})
                ORDER BY s.hot DESC, a.published DESC LIMIT ?
            ''', (cutoff, *trusted, limit)).fetchall()

        def read(row):
            config = trusted[row['source']]
            try:
                url = urlsplit(row['url'])
                if (url.scheme != 'https' or url.hostname != config['article_host']
                        or url.port not in (None, 443) or url.username or url.password):
                    return row, '', 'blocked'
                original = fetch(row['url'], config.get('article_redirect_hosts', []))
                return row, original, 'checked'
            except HTTPError as error:
                return row, '', f'HTTP {error.code}'
            except (OSError, ValueError) as error:
                return row, '', type(error).__name__

        added = 0
        with ThreadPoolExecutor(max_workers=3) as pool:
            for row, original, state in pool.map(read, rows):
                evidence = select_reading_facts(original, row['summary'])
                if state == 'checked':
                    state = 'ready' if evidence else 'insufficient'
                with closing(self.connect()) as db, db:
                    db.execute('''INSERT OR IGNORE INTO article_reading (article_id,evidence,body,state,checked_at)
                                  VALUES (?,?,?,?,?)''',
                               (row['id'], evidence, evidence if row['language'] == 'zh' and evidence else None,
                                state, utcnow().isoformat()))
                    if not row['summary'] and original:
                        available = evidence_copy(original, 480)
                        db.execute('UPDATE articles SET summary=?,content_key=? WHERE id=? AND summary=?',
                                   (available, content_key(row['title'], available), row['id'], row['summary']))
                added += bool(evidence)
        return added

    def refresh_briefing(self, *, now=None):
        now = (now or utcnow()).astimezone(timezone.utc)
        day = now.astimezone(BEIJING).date().isoformat()
        cutoff = (now - timedelta(hours=24)).isoformat()
        with closing(self.connect()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            candidates = db.execute('''
                SELECT a.id, a.source, a.title_key FROM articles a
                JOIN article_signals s ON s.article_id=a.id
                LEFT JOIN translations t ON t.content_key=a.content_key
                LEFT JOIN event_representatives e ON e.article_id=a.id
                WHERE a.archived=0 AND s.hot=1 AND s.unverified=0 AND a.kind<>'voice'
                AND (e.winner_id IS NULL OR e.winner_id=a.id)
                AND ''' + PUBLISHABLE + '''
                AND ((length(a.published)=10 AND a.published=?)
                  OR (length(a.published)>10 AND a.published BETWEEN ? AND ?))
                ORDER BY s.priority DESC, a.published DESC, a.id DESC LIMIT 30
            ''', (day, cutoff, now.isoformat()))
            selected, titles, counts = [], set(), {}
            for row in candidates:
                key = row['title_key']
                source = row['source']
                if key in titles or counts.get(source, 0) >= 2:
                    continue
                selected.append(row['id'])
                titles.add(key)
                counts[source] = counts.get(source, 0) + 1
                if len(selected) == 5:
                    break
            previous = [row[0] for row in db.execute(
                'SELECT article_id FROM daily_briefing WHERE day=? ORDER BY position', (day,))]
            if previous != selected:
                db.execute('DELETE FROM daily_briefing WHERE day=?', (day,))
                db.executemany('INSERT INTO daily_briefing VALUES (?,?,?)',
                               ((day, position, identifier) for position, identifier in enumerate(selected)))
        return {'day': day, 'items': len(selected)}

    def briefing(self):
        with closing(self.connect()) as db:
            day = db.execute('SELECT max(day) FROM daily_briefing').fetchone()[0]
            rows = db.execute('SELECT ' + ARTICLE_FIELDS + JOIN
                              + ' JOIN daily_briefing b ON b.article_id=a.id'
                                ' WHERE b.day=? AND (e.winner_id IS NULL OR e.winner_id=a.id) AND '
                              + PUBLISHABLE + ' ORDER BY b.position', (day,)).fetchall()
        return day, [present(row) for row in rows]

    def run_cycle(self, *, force=False):
        from .news_translate import translate_pending

        collection = self.collect(force=force)
        merged = self.merge_events()
        enriched = self.enrich_articles()
        translation = translate_pending(self)
        briefing = self.refresh_briefing()
        return {'collection': collection, 'longer_excerpts': enriched, 'merged_reports': merged,
                'briefing': briefing, 'translation': translation}

    def articles(self, *, mode='news', query='', source='', days='30', offset=0):
        conditions = ['(s.priority > 0 OR ?)', '(e.winner_id IS NULL OR e.winner_id=a.id)', PUBLISHABLE]
        params = [source == 'archive']
        if mode in ('updates', 'official', 'hot', 'rumors'):
            conditions.append(ARTICLE_SECTION + ' = ?')
            params.append(mode)
        else:
            conditions.append("s.unverified=0 AND a.kind<>'voice'")
        if query:
            conditions.append("instr(lower(a.title||' '||a.summary||' '||a.label||' '||coalesce(t.title,'')||' '||coalesce(t.summary,'')||' '||coalesce(tb.brief,'')), lower(?)) > 0")
            params.append(query)
        if source == 'archive':
            conditions.append('archived=1')
        elif source:
            conditions.append('a.source=?')
            params.append(source)
        elif mode != 'news':
            conditions.append('a.archived=0')
        if days != 'all':
            conditions.append('a.published>=?')
            params.append((utcnow() - timedelta(days=int(days))).date().isoformat())
        where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
        order = ("CASE WHEN julianday(a.published)>=julianday('now','-2 days') THEN 1 ELSE 0 END DESC,"
                 " COALESCE(h.points,0) DESC,COALESCE(att.weight,0) DESC,s.priority DESC,"
                 if mode == 'hot' else '')
        with closing(self.connect()) as db:
            total = db.execute('SELECT count(*) ' + JOIN + where, params).fetchone()[0]
            rows = db.execute('SELECT ' + ARTICLE_FIELDS
                              + JOIN + where + ' ORDER BY ' + order + ' a.published DESC, a.id DESC LIMIT 20 OFFSET ?',
                              (*params, offset)).fetchall()
        return [present(row) for row in rows], total

    def article(self, identifier):
        with closing(self.connect()) as db:
            row = db.execute('SELECT ' + ARTICLE_FIELDS + JOIN + '''
                WHERE a.kind<>'lead' AND (a.kind='voice' OR s.unverified=0) AND ''' + PUBLISHABLE + '''
                AND a.id=COALESCE((SELECT winner_id FROM event_representatives WHERE article_id=
                                    COALESCE((SELECT article_id FROM article_aliases WHERE id=?), ?)),
                                 (SELECT article_id FROM article_aliases WHERE id=?), ?)
            ''', (identifier, identifier, identifier, identifier)).fetchone()
            if not row:
                return None
            result = present(row)
            reading = db.execute('SELECT body FROM article_reading WHERE article_id=?', (row['id'],)).fetchone()
            if reading and reading['body'] and row['method'] != 'reviewed':
                _, paragraphs = reading_copy(reading['body'])
                result['body'] = paragraphs
                result['reading_intro'] = result['summary']
            related = db.execute('''
                SELECT a.label,a.url,a.published,a.title,t.title AS zh_title,
                       CASE WHEN a.language='zh' THEN a.summary ELSE t.summary END AS translated_excerpt
                FROM event_representatives e JOIN articles a ON a.id=e.article_id
                LEFT JOIN translations t ON t.content_key=a.content_key
                WHERE e.winner_id=? AND a.id<>? ORDER BY a.published DESC LIMIT 5
            ''', (row['id'], row['id']))
            result['related'] = []
            seen = [(key, figures) for _, key, figures in evidence_sentences(' '.join(result['body']))]
            for source in related:
                extra = additional_excerpt(source['translated_excerpt'] or '', seen)
                result['related'].append({'source': source['label'], 'url': source['url'],
                                          'published_at': source['published'],
                                          'title': source['zh_title'] or source['title'],
                                          'excerpt': excerpt(extra, 240)})
            return result


ARTICLE_FIELDS = ('a.*, t.title AS zh_title, t.summary AS zh_summary, t.method, tb.brief, s.unverified, '
                  'h.points, h.thread, c.reply_url ')
PUBLISHABLE = f"""((a.language='zh' AND length(trim(a.summary))>0)
               OR (t.method IN ('{TRANSLATION_METHOD}','reviewed') AND length(trim(t.summary))>0))"""
ARTICLE_SECTION = """CASE
    WHEN a.kind='voice' THEN 'rumors'
    WHEN s.unverified=1 THEN NULL
    WHEN a.is_model=1 THEN 'updates'
    WHEN a.kind='official' THEN 'official'
    WHEN s.hot=1 OR h.points>=25 OR att.evidence_count>=2 THEN 'hot'
END"""
JOIN = ('FROM articles a JOIN article_signals s ON s.article_id=a.id '
        'LEFT JOIN translations t ON t.content_key=a.content_key '
        'LEFT JOIN translation_briefs tb ON tb.content_key=a.content_key '
        'LEFT JOIN event_representatives e ON e.article_id=a.id '
        'LEFT JOIN event_attention att ON att.article_id=a.id '
        "LEFT JOIN news_heat h ON h.url=a.identity AND julianday(h.checked)>=julianday('now','-7 days') "
        'LEFT JOIN article_context c ON c.article_id=a.id')


def present(row):
    method = 'official_zh' if row['language'] == 'zh' and row['kind'] == 'official' else row['method']
    if method == TRANSLATION_METHOD:
        method = 'offline'
    title = row['zh_title'] or row['title']
    summary, body = reading_copy(row['zh_summary'] or row['summary'])
    summary = row['brief'] or useful_brief(title, summary, body)
    discovery = row['kind'] == 'lead'
    voice = None
    if row['kind'] == 'voice':
        if row['unverified']:
            voice = '未经证实'
        elif re.search(r'\bI (?:think|suspect|believe)|我认为|我猜', row['summary'], re.I):
            voice = '个人观点或推测'
        elif re.search(r"\b(?:I|we)(?:'ve| have)? (?:released|launched|published|shipped)\b|我(?:们)?已发布", row['summary'], re.I):
            voice = '本人发布的动态'
        else:
            voice = '本人公开发言'
    return {
        'id': row['id'], 'title': title, 'original_title': row['title'],
        'summary': summary, 'body': body, 'original_summary': row['summary'],
        'url': row['url'], 'published_at': None if discovery else row['published'],
        'observed_at': row['published'] if discovery else None,
        'time_label': '线索记录时间' if discovery else '发布时间',
        'original_time': row['original_time'], 'unverified': bool(row['unverified']),
        'voice_status': voice, 'reply_url': row['reply_url'],
        'community_points': row['points'], 'community_thread': row['thread'],
        'source': row['label'], 'source_id': row['source'], 'kind': row['kind'],
        'translation': method or ('zh' if row['language'] == 'zh' else 'original'),
        'is_model': bool(row['is_model']), 'archived': bool(row['archived']),
    }


def main():
    parser = ArgumentParser(description='AINOOK 固定来源资讯采集')
    parser.add_argument('--data-dir', type=Path, default=Path('outputs/ainook'))
    parser.add_argument('--config', type=Path, default=SOURCE_FILE, help='使用指定来源清单验证采集')
    parser.add_argument('--force', action='store_true', help='立即核对启用的来源，仍跳过停用和限流等待')
    parser.add_argument('--import-archive', type=Path)
    args = parser.parse_args()
    news = News(args.data_dir, config_path=args.config)
    if args.import_archive:
        from .news_archive import import_archive
        print(json.dumps(import_archive(news, args.import_archive), ensure_ascii=False))
    print(json.dumps(news.run_cycle(force=args.force), ensure_ascii=False))


if __name__ == '__main__':
    main()

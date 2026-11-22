"""Fetch public, curated quota evidence and keep a last-known-good projection."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

CATALOG = Path(__file__).with_name('catalog.json')
BEIJING = timezone(timedelta(hours=8))
CHECK_INTERVAL = 10 * 60
MAX_AGE = timedelta(hours=48)
MAX_BYTES = 4 * 1024 * 1024


def utcnow():
    return datetime.now(timezone.utc)


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def json_file(path, default):
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def write_snapshot(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, encoding='utf-8', mode='w', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(state, stream, ensure_ascii=False, indent=2)
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def http_retry_at(error, now):
    if not isinstance(error, HTTPError):
        return None
    fallback = now + timedelta(seconds=CHECK_INTERVAL)
    if error.code in (401, 402, 403):
        fallback = now + timedelta(hours=1)
    if error.code not in (401, 402, 403, 429, 503):
        return None
    headers = error.headers or {}
    retry_after = headers.get('Retry-After', '')
    try:
        retry = now + timedelta(seconds=int(retry_after))
    except (ValueError, OverflowError):
        try:
            retry = parsedate_to_datetime(retry_after)
            if retry.tzinfo is None:
                retry = retry.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            retry = fallback
    try:
        reset = datetime.fromtimestamp(int(headers.get('x-rate-limit-reset', '')), timezone.utc)
    except (ValueError, OSError, OverflowError):
        reset = fallback
    return max(fallback, retry, reset)


class PageText(HTMLParser):
    hidden_tags = {'script', 'style', 'svg', 'template'}

    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, _):
        if tag in self.hidden_tags:
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in self.hidden_tags and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def normalize(text):
    return re.sub(r'\s+', ' ', text.translate(str.maketrans('’‘–—', "''--"))).casefold().strip()


class VendorRedirect(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if (target.scheme != 'https' or target.hostname not in self.hosts
                or target.port not in (None, 443) or target.username or target.password):
            raise ValueError('非配置的官方跳转')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_text(source):
    url = source['url']
    if source.get('format') == 'x_embed':
        # X's public oEmbed API verifies the post without embedding scripts or logging in.
        match = re.fullmatch(r'https://x\.com/([A-Za-z0-9_]+)/status/(\d+)', url)
        if not match:
            raise ValueError('无法识别公开帖子来源')
        handle, post_id = match.groups()
        endpoint = 'https://publish.twitter.com/oembed?' + urlencode({'url': url, 'omit_script': 'true'})
        opener = build_opener(VendorRedirect({'publish.twitter.com', 'publish.x.com'}))
        with opener.open(endpoint, timeout=12) as response:
            data = json.loads(response.read(65536))
        author = urlsplit(data.get('author_url', ''))
        markup = data.get('html', '')
        if author.hostname not in ('x.com', 'twitter.com') or author.path.casefold() != f'/{handle.casefold()}':
            raise ValueError('帖子作者不匹配')
        if not re.search(r'/(?:' + re.escape(handle) + r')/status/' + post_id + r'(?:[?"/]|$)', markup, re.I):
            raise ValueError('帖子编号不匹配')
        return readable_text(markup)
    opener = build_opener(VendorRedirect({urlsplit(url).hostname, *source.get('redirect_hosts', [])}))
    request = Request(url, headers={
        'Accept': 'text/html',
        'User-Agent': 'AINOOK/1.0 quota reference (public documentation)',
    })
    with opener.open(request, timeout=12) as response:
        if response.headers.get_content_type() != 'text/html':
            raise ValueError('不支持的内容类型')
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('官方页面超过大小上限')
    return readable_text(raw.decode('utf-8', errors='replace'))


def readable_text(markup):
    parser = PageText()
    parser.feed(markup)
    return normalize(' '.join(parser.parts))


class Quota:
    def __init__(self, data_path, *, catalog_path=CATALOG):
        self.catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
        self.platforms = self.catalog['platforms']
        self.data_path = Path(data_path)
        self.discovery_path = self.data_path.with_name('quota-discovery.json')

    def sync(self, fetch=fetch_text, *, now=None):
        now = now or utcnow()
        previous = json_file(self.data_path, {})
        sources = [source for platform in self.platforms for source in platform['sources']]

        def check(source):
            old = previous.get(source['id'], {})
            retry_at = instant(old.get('retry_at'))
            if retry_at and retry_at > now:
                return source['id'], old
            verified = dict(old.get('verified', {}))
            state = {'checked_at': now.isoformat(), 'verified': verified, 'review': old.get('review', [])}
            try:
                text = fetch(source)
                mismatches = []
                for record in source['records']:
                    if all(normalize(phrase) in text for phrase in record['evidence']):
                        verified[record['id']] = now.isoformat()
                    else:
                        mismatches.append(record['id'])
                state['review'] = mismatches
            except (OSError, ValueError) as exc:
                state['error'] = getattr(exc, 'code', None) or type(exc).__name__
                if retry := http_retry_at(exc, now):
                    state['retry_at'] = retry.isoformat()
            return source['id'], state

        with ThreadPoolExecutor(max_workers=3) as workers:
            state = dict(workers.map(check, sources))
        write_snapshot(self.data_path, state)
        return {key: {'error': row.get('error'), 'review': row.get('review', [])}
                for key, row in state.items()}

    def overview(self, *, now=None):
        now = now or utcnow()
        cache = json_file(self.data_path, {})
        discovered = json_file(self.discovery_path, {}).get('records', {})
        result = []
        for platform in self.platforms:
            item = {key: platform[key] for key in ('id', 'name', 'owner', 'logo', 'account_url', 'account_hint')}
            item['records'] = []
            for source in platform['sources']:
                state = cache.get(source['id'], {})
                evidence = state.get('verified', {})
                failure = state.get('error')
                temporary_failure = (failure == 429 or isinstance(failure, int) and failure >= 500
                                     or failure in ('TimeoutError', 'URLError', 'OSError', 'ConnectionError'))
                for record in source['records']:
                    last_verified = evidence.get(record['id'], self.catalog['reviewed_at'])
                    verified = instant(last_verified)
                    expired = instant(record.get('expires_at'))
                    starts = instant(record.get('starts_at'))
                    cached_event = (temporary_failure and record['id'] in evidence
                                    and (record.get('confirmed_issued') or record.get('signal_until')
                                         or record.get('scheduled_at')))
                    if expired and now >= expired:
                        status = 'expired'
                    elif record['id'] in state.get('review', []):
                        status = 'review'
                    elif not verified or now - verified > MAX_AGE or (failure and not cached_event):
                        status = 'stale'
                    elif starts and starts > now:
                        status = 'scheduled'
                    elif record['type'] == 'offer' and not expired:
                        status = 'conditional'
                    else:
                        status = 'verified'
                    public = {key: value for key, value in record.items() if key != 'evidence'}
                    public.update(source=source['label'], url=source['url'], verified_at=last_verified,
                                  checked_at=state.get('checked_at'), status=status)
                    item['records'].append(public)
            known_urls = {record['url'].casefold() for record in item['records']}
            item['records'].extend(record for record in discovered.values()
                                   if record['platform'] == item['id'] and record['url'].casefold() not in known_urls)
            result.append(item)
        return result

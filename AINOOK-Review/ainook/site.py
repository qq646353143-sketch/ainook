"""Public HTTP entry point for the standalone allowance tool."""
import argparse
from collections import defaultdict, deque
import gzip
from hashlib import sha256
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sqlite3
import threading
import time
from urllib.parse import parse_qs, urlsplit

from .quota import CHECK_INTERVAL, Quota, json_file
from .news import News
from .news_edition import EDITION_FILE, EDITIONS, LEGACY_SECTIONS, NewsEdition
from . import news_views
from .views import PAGES, SECURITY_POLICY, STATIC, card_events, page
from .wishes import Wishes

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / 'outputs/ainook'
DEFAULT_WISHES = ROOT / 'outputs/prototypes/home-v1/wishes.sqlite3'
DEFAULT_ORIGIN = ROOT / 'outputs/releases/runtime/public-origin.json'
PUBLIC_ASSETS = {'Geist-Variable.woff2': 'font/woff2', 'Geist-Variable.ttf': 'font/ttf',
                 'night-sky.webp': 'image/webp'}
ROBOTS = 'User-agent: *\nDisallow: /api/\n'
RETIRED_PATHS = {'/briefing', '/voices', '/intelligence'}


def https_origin(config):
    try:
        parsed = urlsplit(config.get('origin', ''))
        if (config.get('public_scope') in ('manual', 'official') and parsed.scheme == 'https'
                and re.fullmatch(r'[a-z0-9.-]+', parsed.hostname or '')
                and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                and parsed.path in ('', '/')):
            port = f':{parsed.port}' if parsed.port and parsed.port != 443 else ''
            return f'https://{parsed.hostname}{port}'
    except ValueError:
        pass
    return ''


def accepts_gzip(header):
    for coding in header.lower().split(','):
        name, _, parameters = coding.partition(';')
        if name.strip() == 'gzip':
            try:
                return not parameters or float(parameters.strip().removeprefix('q=')) > 0
            except ValueError:
                return False
    return False


class AllowanceSite:
    def __init__(self, data_dir, wish_path, origin_file):
        self.origin_file = Path(origin_file)
        self.quota = Quota(Path(data_dir) / 'verified.json')
        self.wishes = Wishes(wish_path, [item['id'] for item in self.quota.platforms])
        self.assets = {**PUBLIC_ASSETS, **news_views.IMAGE_ASSETS,
                       **{item['logo']: 'image/svg+xml' for item in self.quota.platforms}}
        self.rates = defaultdict(deque)
        self.rate_lock = threading.Lock()
        self.last_prune = 0.0
        self.stop_event = threading.Event()
        try:
            edition = Path(data_dir) / EDITION_FILE
            self.news = NewsEdition(edition) if edition.is_file() else News(data_dir)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            print(f'AINOOK 资讯初始化失败: {type(error).__name__}', flush=True)
            self.news = None

    def config(self):
        value = json_file(self.origin_file, {})
        return value if isinstance(value, dict) else {}

    def cards(self):
        overview = self.quota.overview()
        fields = ('id', 'name', 'owner', 'logo')
        try:
            totals = self.wishes.totals()
        except sqlite3.Error:
            totals = {}
        return {'items': [{**{key: row[key] for key in fields}, **card_events(row['records'])}
                          for row in overview], 'totals': totals}

    def allow_write(self, client):
        now = time.monotonic()
        with self.rate_lock:
            if now - self.last_prune >= 60:
                self.rates = defaultdict(deque, {key: queue for key, queue in self.rates.items() if queue[-1] > now - 60})
                self.last_prune = now
            if client not in self.rates and len(self.rates) >= 5000:
                return False
            queue = self.rates[client]
            while queue and queue[0] <= now - 60:
                queue.popleft()
            if len(queue) >= 120:
                return False
            queue.append(now)
            return True

    def start_checks(self):
        def work():
            while not self.stop_event.is_set():
                try:
                    result = self.quota.sync()
                    print('AINOOK quota check:', json.dumps(result, ensure_ascii=False), flush=True)
                except (OSError, ValueError) as exc:
                    print('AINOOK quota check:', type(exc).__name__, flush=True)
                self.stop_event.wait(CHECK_INTERVAL)
        threading.Thread(target=work, name='ainook-quota-check', daemon=True).start()

    def start_news(self):
        if not isinstance(self.news, News):
            return

        def work():
            while not self.stop_event.is_set():
                try:
                    result = self.news.run_cycle()
                    print('AINOOK 资讯:', json.dumps(result, ensure_ascii=False), flush=True)
                except Exception as error:
                    print(f'AINOOK 资讯任务失败: {type(error).__name__}', flush=True)
                self.stop_event.wait(self.news.interval.total_seconds())
        threading.Thread(target=work, name='ainook-news-collection', daemon=True).start()


class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def get_request(self):
        conn, address = super().get_request()
        conn.settimeout(12)
        return conn, address


def serve(port=7880, *, bind='127.0.0.1', scheduler=True, quota_scheduler=True, data_dir=DEFAULT_DATA,
          wish_path=DEFAULT_WISHES, origin_file=DEFAULT_ORIGIN):
    app = AllowanceSite(data_dir, wish_path, origin_file)
    if not ipaddress.ip_address(bind).is_loopback and not https_origin(app.config()):
        raise ValueError('对外监听前，请配置 HTTPS 公开来源。')
    local = {f'http://127.0.0.1:{port}', f'http://localhost:{port}'}

    class Handler(BaseHTTPRequestHandler):
        server_version = 'ainook'
        sys_version = ''

        def log_message(self, *args):
            pass

        def respond(self, status, value, mime='application/json; charset=utf-8', extra=None, *, age=0):
            raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if mime.startswith('application/json') else value
            headers = {
                'Content-Type': mime,
                'Cache-Control': f'public, max-age={age}' if age else 'no-store',
                'X-Content-Type-Options': 'nosniff',
                'Referrer-Policy': 'no-referrer',
                'Content-Security-Policy': SECURITY_POLICY,
            }
            if status == 200 and len(raw) >= 1024 and mime.startswith(('text/', 'application/json', 'image/svg+xml')):
                headers['Vary'] = 'Accept-Encoding'
                if accepts_gzip(self.headers.get('Accept-Encoding', '')):
                    raw = gzip.compress(raw, compresslevel=4, mtime=0)
                    headers['Content-Encoding'] = 'gzip'
            if age:
                etag = '"' + sha256(raw).hexdigest() + '"'
                headers['ETag'] = etag
                tags = {tag.strip().removeprefix('W/') for tag in self.headers.get('If-None-Match', '').split(',')}
                if etag in tags or '*' in tags:
                    status = 304
            if status not in (204, 304):
                headers['Content-Length'] = str(len(raw))
            self.send_response(status)
            for name, content in {**headers, **(extra or {})}.items():
                self.send_header(name, content)
            self.end_headers()
            if self.command != 'HEAD' and status not in (204, 304):
                self.wfile.write(raw)

        def do_GET(self):
            self.dispatch()

        def do_HEAD(self):
            self.dispatch()

        def do_POST(self):
            self.dispatch()

        def html_page(self, path, data, canonical, status=200):
            body, policy = page(path, data, canonical)
            headers = {'Content-Security-Policy': policy}
            if not canonical:
                headers['X-Robots-Tag'] = 'noindex'
            return self.respond(status, body, 'text/html; charset=utf-8', headers)

        def read_news(self, path, query, canonical):
            api = path.startswith('/api/site/')
            route = path.removeprefix('/api/site') if api else path
            news = app.news
            edition = news if isinstance(news, NewsEdition) else None
            sections = EDITIONS if edition else news_views.SECTIONS
            if edition and route in LEGACY_SECTIONS:
                route = LEGACY_SECTIONS[route]
                if not api:
                    suffix = '?' + query if query else ''
                    return self.respond(302, b'', 'text/plain', {'Location': route + suffix})
            if news is None:
                if api:
                    return self.respond(503, {'error': '资讯服务暂不可用'})
                data = {'title': 'AI 资讯', 'news_html': news_views.unavailable(route, '资讯暂不可用，请稍后重试。')}
                return self.html_page(path, data, canonical, 503)
            title = sections.get(route) or news_views.PAGES.get(route, 'AI 资讯')
            status = 200
            if route.startswith('/article/'):
                identifier = route.removeprefix('/article/')
                item = news.article(identifier) if re.fullmatch(r'[a-f0-9]{24}', identifier) else None
                if api:
                    return self.respond(200 if item else 404, item or {'error': '资讯不存在'})
                if item and query == 'inline=1':
                    return self.respond(200, news_views.article_content(item, inline=True).encode(),
                                        'text/html; charset=utf-8', {'X-Robots-Tag': 'noindex'})
                body = (news_views.detail(item, sections=sections, active='/' + item['section'] if edition else '')
                        if item else news_views.unavailable(route, '未找到这条资讯。'))
                title, status = (item['title'], 200) if item else ('资讯不存在', 404)
            elif route == '/news/sources':
                if edition:
                    if api:
                        return self.respond(200, {'mode': 'edition', 'updated': edition.updated.isoformat(),
                                                  'sources': list(edition.sources.values())})
                    return self.respond(302, b'', 'text/plain', {'Location': '/news'})
                sources, logs = news.statuses()
                if api:
                    visible = ('id', 'name', 'url', 'method', 'kind', 'enabled', 'state', 'error', 'success_at', 'added')
                    return self.respond(200, {'sources': [{key: source[key] for key in visible} for source in sources]})
                body = news_views.source_page(sources, logs)
            elif route == '/models':
                if api:
                    return self.respond(200, {'status': 'not_configured', 'items': []})
                return self.respond(302, b'', 'text/plain', {'Location': '/news/model'})
            elif route == '/news' and not api and not edition:
                day, items = news.briefing()
                body = news_views.briefing_page(day, items)
            else:
                mode = route.lstrip('/')
                params = parse_qs(query, max_num_fields=20)
                default_days = 'all' if edition else '30'
                days = params.get('days', [default_days])[-1]
                source = params.get('source', [''])[-1]
                filters = {
                    'query': params.get('q', [''])[-1].strip()[:140],
                    'source': source if source in news.sources or (not edition and source == 'archive') else '',
                    'days': days if days in news_views.PERIODS else default_days,
                    'offset': min(10000, max(0, int(params.get('offset', ['0'])[-1]))),
                }
                items, total = news.articles(mode=mode, **filters)
                if api:
                    return self.respond(200, {'items': items, 'total': total, 'offset': filters['offset'], 'limit': 20})
                body = news_views.list_page(route, items, total, list(news.sources.values()), sections=sections,
                                            edition_at=edition.updated.isoformat() if edition else None, **filters)
            return self.html_page(path, {'title': title, 'news_html': body}, canonical, status)

        def dispatch(self):
            config = app.config()
            origin = https_origin(config)
            scopes = local | ({origin} if origin else set())
            cloud = self.headers.get('CF-Ray') or self.headers.get('CF-Connecting-IP')
            try:
                if (cloud and not origin) or self.headers.get('Host') not in {urlsplit(url).netloc for url in scopes}:
                    return self.respond(403, {'error': '访问地址未启用'})
                target = urlsplit(self.path)
                path = target.path
                if self.command == 'POST':
                    if path != '/api/site/wishes':
                        return self.respond(404, {'error': '接口不存在'})
                    if self.headers.get('Origin') not in scopes:
                        return self.respond(403, {'error': '拒绝跨站写入'})
                    client = self.client_address[0]
                    if origin and self.headers.get('CF-Ray') and ipaddress.ip_address(client).is_loopback:
                        supplied = self.headers.get('CF-Connecting-IP', '')
                        try:
                            client = str(ipaddress.ip_address(supplied))
                        except ValueError:
                            pass
                    if not app.allow_write(client):
                        return self.respond(429, {'error': '请求过于频繁，请稍后重试'}, extra={'Retry-After': '60'})
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 2048 or self.headers.get_content_type() != 'application/json':
                        raise ValueError()
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError()
                    return self.respond(200, app.wishes.add(data.get('platform'), data.get('count'), data.get('batch_id')))

                if path == '/api/site/status':
                    return self.respond(200, {'service': 'ainook-quota'})
                if path == '/api/site/cards':
                    return self.respond(200, app.cards())
                if path == '/api/site/wishes':
                    return self.respond(200, {'totals': app.wishes.totals()})
                canonical = origin if origin and not urlsplit(origin).hostname.endswith('.trycloudflare.com') else ''
                news_route = path.removeprefix('/api/site') if path.startswith('/api/site/') else path
                if (news_route in news_views.PAGES or news_route.startswith('/article/')
                        or (isinstance(app.news, NewsEdition)
                            and (news_route in EDITIONS or news_route in LEGACY_SECTIONS))):
                    try:
                        return self.read_news(path, target.query, canonical)
                    except sqlite3.Error:
                        if path.startswith('/api/'):
                            return self.respond(503, {'error': '资讯数据库暂不可用'})
                        body = news_views.unavailable(news_route, '资讯数据库暂不可用。')
                        return self.html_page(path, {'title': 'AI 资讯', 'news_html': body}, canonical, 503)
                if path in PAGES:
                    if path == '/':
                        data = app.cards()
                    elif path == '/quota':
                        query = parse_qs(target.query, max_num_fields=20)
                        data = {'items': app.quota.overview(), 'days': query.get('days', ['30'])[-1],
                                'platform': query.get('platform', [''])[-1]}
                    else:
                        data = {}
                    return self.html_page(path, data, canonical)
                if path in ('/abc/focus.html', '/quota/', '/privacy/'):
                    return self.respond(301, b'', 'text/plain', {'Location': '/' if path.startswith('/abc') else path.rstrip('/')})
                if path.startswith('/assets/'):
                    name = path.removeprefix('/assets/')
                    if name in app.assets and re.fullmatch(r'[a-zA-Z0-9_.-]+', name):
                        return self.respond(200, (STATIC / 'assets' / name).read_bytes(), app.assets[name], age=600)
                if path == '/robots.txt':
                    rules = ROBOTS + f'Sitemap: {canonical}/sitemap.xml\n' if canonical else 'User-agent: *\nDisallow: /\n'
                    return self.respond(200, rules.encode(), 'text/plain; charset=utf-8')
                if path == '/sitemap.xml' and canonical:
                    urls = ''.join(f'<url><loc>{escape(canonical + route)}</loc></url>' for route in PAGES)
                    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
                    return self.respond(200, xml.encode(), 'application/xml; charset=utf-8')
                if path == '/favicon.ico':
                    return self.respond(204, b'', 'image/x-icon')
                if path.startswith('/api/'):
                    return self.respond(404, {'error': '接口不存在'})
                closed = path.rstrip('/') in RETIRED_PATHS or path.startswith('/article/')
                heading = '此栏目已下线' if closed else '页面不存在'
                html = f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{heading} · ainook.</title><h1>{heading}</h1><a href="/quota">查看额度与权益</a></html>'
                return self.respond(410 if closed else 404, html.encode(), 'text/html; charset=utf-8')
            except (BrokenPipeError, ConnectionError, TimeoutError):
                pass
            except (TypeError, ValueError):
                self.respond(400, {'error': '请求参数无效'})
            except (OSError, sqlite3.Error):
                self.respond(503, {'error': '服务暂时不可用，请稍后重试'})

    server = LocalHTTPServer((bind, port), Handler)
    if scheduler:
        if quota_scheduler:
            app.start_checks()
        app.start_news()
    print(f'AINOOK 监听 http://{bind}:{port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop_event.set()
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=7880)
    parser.add_argument('--bind', choices=('127.0.0.1', '0.0.0.0'), default='127.0.0.1')
    parser.add_argument('--no-scheduler', action='store_true')
    parser.add_argument('--no-quota-scheduler', action='store_true', help='并行预览时复用额度快照，避免重复检查')
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--wish-db', type=Path, default=DEFAULT_WISHES)
    parser.add_argument('--origin-file', type=Path, default=DEFAULT_ORIGIN)
    args = parser.parse_args()
    serve(args.port, scheduler=not args.no_scheduler, quota_scheduler=not args.no_quota_scheduler, bind=args.bind, data_dir=args.data_dir,
          wish_path=args.wish_db, origin_file=args.origin_file)

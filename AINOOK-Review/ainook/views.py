"""Shared layout and server-rendered allowance records."""
from base64 import b64encode
from datetime import date, timedelta
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from .quota import BEIJING, instant, utcnow

STATIC = Path(__file__).with_name('static')
PAGES = {
    '/': ('ainook. · AI 额度重置与权益查询', '查找 OpenAI Codex、Claude 和 Grok 的额度恢复规则、官方权益和个人用量入口。'),
    '/quota': ('额度与权益 · ainook.', '查看 AI 工具官方恢复周期、临时赠送、限额变化与历史记录。'),
    '/author': ('作者小屋 · ainook.', '了解 ainook. 与作者爱学习。'),
    '/privacy': ('隐私说明 · ainook.', '了解 ainook. 的点击计数、浏览器存储和连接数据。'),
}
SECURITY_POLICY = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
TYPES = {'cycle': '常规恢复', 'offer': '临时权益', 'policy': '限额变化',
         'banked': '重置卡', 'reset': '临时重置'}
RANGES = {'7': '7 天', '30': '30 天', '90': '90 天', 'all': '全部'}
STATES = {
    'verified': '来源已核对', 'expired': '已到期 · 历史记录', 'scheduled': '尚未开始',
    'review': '来源措辞变化 · 待复核', 'stale': '暂未复核 · 保留上次资料', 'conditional': '以账户资格为准',
}


def static(name):
    return (STATIC / name).read_text(encoding='utf-8')


def source_hash(content):
    return "'sha256-" + b64encode(sha256(content.encode()).digest()).decode('ascii') + "'"


def china_time(value):
    stamp = instant(value)
    return stamp.astimezone(BEIJING).strftime('%Y-%m-%d %H:%M') + ' 北京时间' if stamp else '时间待确认'


def event_day(record):
    stamp = instant(record.get('published_at'))
    if stamp:
        return stamp.astimezone(BEIJING).date()
    return date.fromisoformat(record['announced_on']) if record.get('announced_on') else None


def event_caption(record):
    if record.get('published_at'):
        return f'原帖发布 {china_time(record["published_at"])}'
    return f'公告日期 {event_day(record).isoformat()}（原公告日期）'


def ordered_events(records):
    events = [record for record in records if event_day(record)]
    return sorted(events, key=lambda record: (event_day(record), record.get('published_at', '')), reverse=True)


def card_events(records, *, now=None):
    now = now or utcnow()
    today = now.astimezone(BEIJING).date()
    events = [record for record in ordered_events(records)
              if event_day(record) <= today and (instant(record.get('published_at')) or now) <= now]
    trusted = [record for record in records if record['status'] in ('verified', 'conditional', 'scheduled')]
    issued = next((record for record in events if record.get('confirmed_issued')
                   and record['status'] == 'verified'), None)
    scheduled = [(instant(record.get('scheduled_at')), record) for record in trusted]
    upcoming = min(((stamp, record) for stamp, record in scheduled if stamp and stamp > now),
                   key=lambda item: item[0], default=None)
    result = {
        'latest': None,
        'issued_day': (issued.get('issued_on') or event_day(issued).isoformat()) if issued else None,
        'next_event': {'at': upcoming[0].isoformat(), 'id': upcoming[1]['id'],
                       'url': upcoming[1]['url']} if upcoming else None,
        'estimate': None,
    }
    if not events:
        return result
    latest = events[0]
    when = instant(latest.get('published_at'))
    result['latest'] = {
        'id': latest['id'], 'date': event_day(latest).isoformat(),
        'time': when.astimezone(BEIJING).strftime('%H:%M') if when else None,
        'published_at': latest.get('published_at'),
        'type': TYPES[latest['type']], 'title': latest['title'],
        'status': STATES[latest['status']] if latest['status'] in ('stale', 'review', 'expired') else '',
    }
    same_type = [record for record in events if record['type'] == latest['type']
                 and record['status'] not in ('stale', 'review')]
    points = sorted({stamp for record in same_type
                     if (stamp := instant(record.get('published_at')))})[-5:]
    intervals = [later - earlier for earlier, later in zip(points, points[1:])]
    if (len(intervals) >= 2 and latest['type'] in ('banked', 'reset')
            and when == points[-1]):
        result['estimate'] = {
            'from': (when + min(intervals)).astimezone(BEIJING).date().isoformat(),
            'to': (when + max(intervals)).astimezone(BEIJING).date().isoformat(),
            'samples': len(points), 'type': TYPES[latest['type']],
        }
    return result


def history_chart(events, start, today):
    timed = [(record, instant(record.get('published_at'))) for record in events]
    if not any(stamp for _, stamp in timed):
        return ''
    days = max(1, (today - start).days)
    guides = ''.join(
        f'<line x1="69" y1="{y}" x2="650" y2="{y}"/><text x="61" y="{y+4}" text-anchor="end">{hour}:00</text>'
        for hour, y in ((24, 16), (18, 49), (12, 82), (6, 115), (0, 148))
    )
    dates = ''.join(
        f'<text x="{69+581*fraction:.1f}" y="175" text-anchor="{align}">{day:%m/%d}</text>'
        for fraction, day, align in ((0, start, 'start'), (1, today, 'end'))
    )
    points = []
    for record, stamp in timed:
        if not stamp:
            continue
        stamp = stamp.astimezone(BEIJING)
        x = 69 + 581 * (stamp.date() - start).days / days
        y = 148 - (stamp.hour * 60 + stamp.minute) * 132 / 1440
        label = escape(f'{record["name"]}，{event_caption(record)}，{record["title"]}')
        points.append(f'<a href="#{escape(record["id"])}" aria-label="{label}"><circle cx="{x:.1f}" cy="{y:.1f}" r="5"><title>{label}</title></circle></a>')
    return (
        '<figure class="history-chart"><figcaption>原帖发布时间 · 北京时间</figcaption>'
        '<svg viewBox="0 0 682 182" role="group" aria-label="原帖发布时间分布">'
        f'{guides}{dates}{"".join(points)}</svg></figure>'
    )


def history(platforms, days, platform):
    days = days if days in RANGES else '30'
    choices = {'': '全部平台', **{item['id']: item['name'] for item in platforms}}
    platform = platform if platform in choices else ''
    today = utcnow().astimezone(BEIJING).date()
    events = ordered_events({**record, 'name': item['name']} for item in platforms
                            if not platform or platform == item['id'] for record in item['records'])
    start = event_day(events[-1]) if days == 'all' and events else today
    if days != 'all':
        start = today - timedelta(days=int(days) - 1)
    events = [record for record in events if start <= event_day(record) <= today]

    def link(span, product, title, active):
        query = urlencode({'days': span, 'platform': product})
        state = ' aria-current="true"' if active else ''
        return f'<a href="/quota?{escape(query)}#history"{state}>{escape(title)}</a>'

    ranges = ''.join(link(key, platform, label, key == days) for key, label in RANGES.items())
    tabs = ''.join(link(days, key, label, key == platform) for key, label in choices.items())
    records = ''.join(quota_record(record, in_history=True) for record in events)
    if not records:
        records = '<p class="quota-meta">这段时间暂无已收录公告。可切换到更长的时间范围。</p>'
    return (
        '<section id="history" class="history-panel"><header><h2>恢复记录</h2>'
        f'<p class="quota-meta">已收录 {len(events)} 条。公告时间与到账时间可能不同。</p></header>'
        f'<nav class="history-filters" aria-label="选择平台">{tabs}</nav>'
        f'<nav class="history-filters" aria-label="时间范围">{ranges}</nav>'
        f'{history_chart(events, start, today)}<div class="history-records">{records}</div></section>'
    )


def quota_record(record, *, in_history=False):
    state = record['status']
    color = ' quota-stale' if state in ('review', 'stale', 'expired') else ''
    dates = f'<p class="quota-meta">{event_caption(record)}</p>' if event_day(record) else ''
    if 'expires_at' in record:
        dates += f'<p class="quota-meta">官方截止 {china_time(record["expires_at"])}</p>'
    if 'scheduled_at' in record:
        dates += f'<p class="quota-meta">官方计划 {china_time(record["scheduled_at"])}</p>'
    source_name = f'{record["name"]} · ' if in_history else ''
    return (
        f'<article id="{escape(record["id"])}">'
        f'<p class="quota-status{color}">{escape(source_name)}{TYPES[record["type"]]} · {STATES[state]}</p>'
        f'<h3>{escape(record["title"])}</h3><p>{escape(record["summary"])}</p>'
        f'<p class="quota-meta">适用 {escape(record["audience"])}</p>{dates}'
        f'<p class="quota-meta">上次核对 {china_time(record["verified_at"])}</p>'
        f'<a href="{escape(record["url"])}" target="_blank" rel="noopener noreferrer">{escape(record["source"])} ↗</a>'
        '</article>'
    )


def quota_page(platforms, days, platform):
    sections, index = [], []
    for item in platforms:
        key, name = escape(item['id']), escape(item['name'])
        index.append(f'<a href="#{key}">{name}</a>')
        blocks = ''.join(quota_record(record) for record in item['records'] if not event_day(record))
        sections.append(
            f'<section id="{key}"><h2>{name} <span class="quota-meta">{escape(item["owner"])}</span></h2>'
            f'<p>{escape(item["account_hint"])} <a href="{escape(item["account_url"])}" target="_blank" rel="noopener noreferrer">打开官方账户页面 ↗</a></p>'
            f'{blocks}</section>'
        )
    return (
        '<main class="quota-page" id="main"><h1>额度与权益</h1>'
        '<p>查常规恢复规则和官方权益。个人剩余额度及下次恢复时间，以各平台的账户页面为准。</p>'
        f'{history(platforms, days, platform)}'
        '<h2 class="rules-heading" id="rules">各平台恢复规则</h2>'
        f'<nav aria-label="平台规则">{"".join(index)}</nav>{"".join(sections)}'
        '<a href="/privacy">隐私说明</a></main>'
    )


def page(path, data, canonical):
    is_news = 'news_html' in data
    title, description = (data['title'] + ' · ainook.', 'AINOOK AI 资讯、模型更新与官方公告。') if is_news else PAGES[path]
    css, theme = static('home.css'), static('theme.js')
    css += '\n' + static('interaction.css')
    if is_news:
        css += '\n' + static('news.css')
    elif path == '/':
        css += '\n' + static('corner.css')
    policy = SECURITY_POLICY.replace("style-src 'self'", f"style-src 'self' {source_hash(css)}")
    scripts = [theme]
    if is_news:
        main = data['news_html']
        if 'data-news-preview=' in main:
            reader = static('news-reader.js')
            scripts.append(reader)
            main += f'<script>{reader}</script>'
    elif path == '/':
        app = '\n'.join(static(name) for name in ('burst.js', 'press.js', 'home.js', 'corner.js'))
        scripts.append(app)
        payload = escape(json.dumps(data, ensure_ascii=False, allow_nan=False), quote=False)
        cards = static('cards.html')
        cards = re.sub(r'<details class="more-card" id="more">.*?</details>',
                       lambda _: static('corner-button.html').strip(), cards, count=1, flags=re.S)
        main = f'{cards}<template id="initial-cards">{payload}</template><script>{app}</script>'
    elif path == '/quota':
        main = quota_page(data['items'], data['days'], data['platform'])
    else:
        main = static('author.html' if path == '/author' else 'privacy.html')
    policy = policy.replace("script-src 'self'", "script-src 'self' " + ' '.join(map(source_hash, scripts)))
    values = {
        'title': escape(title), 'description': escape(description),
        'canonical': f'<link rel="canonical" href="{escape(canonical + path)}">' if canonical else '',
        'head': f'<script>{theme}</script><style>{css}</style>',
        'home_current': ' aria-current="page"' if path == '/' else '',
        'news_current': ' aria-current="page"' if is_news else '',
        'author_current': ' aria-current="page"' if path == '/author' else '', 'main': main,
    }
    layout = static('layout.html').replace(
        '<a href="/"{{home_current}}>首页</a>',
        '<a href="/"{{home_current}}>额度追踪</a>\n        <a href="/news"{{news_current}}>前沿资讯</a>',
        1,
    )
    html = re.sub(r'\{\{(\w+)\}\}', lambda match: values[match[1]], layout)
    return html.encode('utf-8'), policy

"""News content rendered inside AINOOK's current shared shell."""
from html import escape
import json
from pathlib import Path
from urllib.parse import urlencode

from .quota import BEIJING, utcnow
from .views import china_time

SECTIONS = {'/news': '精选简报', '/news/model': '模型更新', '/news/official': '官方公告',
            '/news/hot': '行业热点', '/news/world': '国际新闻', '/news/finance': '全球财经',
            '/rumors': '小道消息'}
PAGES = {**SECTIONS, '/news/sources': '采集来源', '/models': '模型排行榜'}
METHODS = {'rss': 'RSS / Atom', 'changelog': '官方更新日志', 'hn_search': '公开社区搜索',
           'gdelt_search': '公开网页搜索', 'bluesky': '公开作者动态', 'github_releases': 'GitHub 公开发布 API'}
STATES = {'ok': '正常', 'unchanged': '未更新', 'pending': '待采集',
          'error': '暂时失败', 'disabled': '停用', 'rate_limited': '限流等待'}
PERIODS = {'7': '近 7 天', '30': '近 30 天', '90': '近 90 天', 'all': '全部日期'}
_PICTURES = json.loads(Path(__file__).with_name('news-images.json').read_text(encoding='utf-8')).values()
ARTICLE_IMAGES = {identifier: picture for picture in _PICTURES for identifier in picture['articles']}
IMAGE_ASSETS = {picture['file']: 'image/webp' for picture in _PICTURES}


def paragraph(value):
    return f'<p>{escape(value)}</p>' if value else ''


def original_link(url, label):
    return f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(label)} ↗</a>'


def figure(identifier):
    picture = ARTICLE_IMAGES.get(identifier)
    if not picture:
        return ''
    credit = original_link(picture['source'], picture['credit'])
    license_text = ' · ' + original_link(picture['license_url'], picture['license']) if picture['license'] else ''
    return (f'<figure class="news-figure"><img src="/assets/{escape(picture["file"])}" '
            f'width="{picture["width"]}" height="{picture["height"]}" alt="{escape(picture["alt"])}" '
            f'loading="lazy" decoding="async"><figcaption>{escape(picture["caption"])} · {credit}'
            f'{license_text} · 缩放为 WebP</figcaption></figure>')


def article_content(item, *, inline=False):
    status = item.get('voice_status') or ('未经证实' if item['unverified'] else '')
    notice = f'<p class="news-meta"><strong>{escape(status)}</strong></p>' if status else ''
    lead = item.get('reading_intro')
    paragraphs = item['body']
    if not lead and item['translation'] == 'reviewed' and len(paragraphs) >= 3:
        lead, *paragraphs = paragraphs
    if inline:
        if lead == item['summary']:
            lead = ''
        if paragraphs and paragraphs[0] == item['summary']:
            paragraphs = paragraphs[1:]
    quote = ''
    if item.get('quote'):
        quote = (f'<blockquote class="news-quote">{paragraph(item["quote"])}'
                 f'<footer>{escape(item["quote_credit"])}</footer></blockquote>')
    body = quote + ''.join(paragraph(part) for part in paragraphs)
    if not body and not inline:
        body = '<p>来源暂未提供更多内容，请查看原文。</p>'
    value = item['published_at'] or item['observed_at']
    date = value if len(value) == 10 else china_time(value)
    source = original_link(item['url'], item['source'] + ' · 原文')
    footer = f'<p class="news-meta">{source} · <time datetime="{escape(value)}">{escape(date)}</time></p>'
    context = []
    if item.get('reply_url'):
        context.append(f'<p>{original_link(item["reply_url"], "所回复的原帖")}</p>')
    if item.get('community_thread'):
        context.append(f'<p>{original_link(item["community_thread"], "Hacker News 讨论")}</p>')
    for related in item.get('related', []):
        label = related['source'] + ' · ' + related['title']
        context.append(f'<p>{original_link(related["url"], label)}</p>')
    if context:
        footer += '<details><summary>补充来源</summary>' + ''.join(context) + '</details>'
    intro = f'<p class="news-intro">{escape(lead)}</p>' if lead and lead not in paragraphs else ''
    reading = f'<div class="news-reading">{body}</div>' if body else ''
    return f'{notice}{intro}{figure(item["id"])}{reading}<footer class="news-byline">{footer}</footer>'


def detail(item, *, sections=SECTIONS, active=''):
    return frame(active, f'<article class="news-story"><h1>{escape(item["title"])}</h1>'
                         f'{article_content(item)}</article>', sections=sections)


def frame(path, body, *, sections=SECTIONS):
    links = ''.join(f'<a href="{route}"' + (' aria-current="page"' if path == route else '')
                    + f'>{title}</a>' for route, title in sections.items())
    return f'<main class="quota-page news-page" id="main"><nav class="news-nav" aria-label="资讯导航">{links}</nav>{body}</main>'


def options(values, selected):
    return ''.join(f'<option value="{escape(key)}"' + (' selected' if key == selected else '')
                   + f'>{escape(label)}</option>' for key, label in values.items())


def article_rows(items):
    rows = []
    for item in items:
        title = ('【未经证实】' if item['unverified'] else '') + item['title']
        identifier = escape(item['id'], quote=True)
        rows.append(f'<article class="news-preview"><h2><a href="/article/{identifier}" '
                    f'data-news-preview="{identifier}">{escape(title)}</a></h2>'
                    f'{paragraph(item["summary"])}'
                    f'<div class="news-expansion" id="news-{identifier}" hidden></div></article>')
    return ''.join(rows)


def briefing_page(day, items):
    heading = ''
    if day:
        label = '本期简报' if day == utcnow().astimezone(BEIJING).date().isoformat() else '上次简报'
        heading = f'<p class="news-meta">{label} · <time datetime="{escape(day)}">{escape(day)}</time> · 北京时间</p>'
    status = '<p class="news-meta"><a href="/news/sources">采集来源与状态</a></p>'
    body = article_rows(items) or '<p>暂无符合条件的资讯。</p>'
    return frame('/news', f'<h1>精选简报</h1>{heading}{status}<div class="news-results">{body}</div>')


def list_page(path, items, total, sources, *, sections=SECTIONS, edition_at=None, **filters):
    query, source, days, offset = (filters[key] for key in ('query', 'source', 'days', 'offset'))
    labels = {'': '全部来源', **{item['id']: item['name'] for item in sources}}
    if not edition_at:
        labels['archive'] = '恢复的历史记录'
    source_options = options(labels, source)
    period = options(PERIODS, days)
    form = (
        f'<form class="news-search" action="{path}"><label>关键词'
        f'<input type="search" name="q" value="{escape(query)}" placeholder="标题、摘要或来源" maxlength="140"></label>'
        f'<label>信息源<select name="source">{source_options}</select></label>'
        f'<label>日期<select name="days">{period}</select></label><button type="submit">查找</button></form>'
    )
    rows = article_rows(items)
    if edition_at:
        stamp = escape(china_time(edition_at))
        count = f'<p class="news-meta">{total} 条 · AI 每日速递 · {stamp}</p>'
    else:
        count = f'<p class="news-meta">{total} 条 · <a href="/news/sources">采集来源与状态</a></p>'
    page_links = []
    for label, position in (('上一页', offset - 20), ('下一页', offset + 20)):
        if 0 <= position < total:
            params = urlencode({'q': query, 'source': source, 'days': days, 'offset': position})
            page_links.append(f'<a href="{path}?{escape(params)}">{label}</a>')
    footer = '<nav class="news-nav" aria-label="分页">' + ''.join(page_links) + '</nav>' if page_links else ''
    title = '前沿资讯' if path == '/news' and edition_at else sections[path]
    return frame(path, f'<h1>{title}</h1>{form}{count}<div class="news-results">'
                       + (rows or '<p>当前没有符合条件的资讯。</p>') + '</div>' + footer,
                 sections=sections)


def source_page(sources, logs):
    rows = []
    for source in sources:
        state = STATES[source['state']] if source['enabled'] else '配置停用'
        method = METHODS[source['method']]
        detail = f' · {escape(source["error"])}' if source.get('error') else ''
        at = f' · 上次成功 {china_time(source["success_at"])}' if source.get('success_at') else ''
        rows.append(f'<article><h2><a href="{escape(source.get("profile") or source["url"])}" target="_blank" rel="noopener noreferrer">'
                    f'{escape(source["name"])}</a></h2><p class="news-meta">{method} · {state}{detail}{at}</p></article>')
    names = {source['id']: source['name'] for source in sources}
    recent = ''.join(f'<li>{china_time(row["at"])} · {escape(names.get(row["source"], row["source"]))}'
                     f' · {STATES[row["state"]]} · 新增 {row["added"]}'
                     + (f' · {escape(row["detail"])}' if row['detail'] else '') + '</li>' for row in logs[:20])
    return frame('/news/sources', '<h1>采集来源</h1><div class="news-results">' + ''.join(rows)
                 + f'</div><details class="news-log"><summary>最近采集日志</summary><ul>{recent}</ul></details>')


def unavailable(path, detail):
    return frame(path, f'<h1>{PAGES.get(path, "AI 资讯")}</h1><p>{escape(detail)}</p>')

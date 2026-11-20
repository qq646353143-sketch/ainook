"""News content rendered inside AINOOK's current shared shell."""
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
from urllib.parse import urlencode

from .news_edition import EDITIONS
from .quota import BEIJING, utcnow
from .views import china_time

SECTIONS = EDITIONS
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


def frame(path, body, *, sections=SECTIONS):
    links = ''.join(f'<a href="{route}"' + (' aria-current="page"' if path == route else '')
                    + f'>{title}</a>' for route, title in sections.items())
    return f'<main class="quota-page news-page" id="main"><nav class="news-nav news-section-nav" aria-label="资讯导航">{links}</nav>{body}</main>'


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


HEADLINE_AMOUNT = re.compile(r'(\d[\d,.]*[ \u00a0]?(?:万亿美元|万亿元|亿美元|亿元|万亿|%))')


def headline(value):
    parts = HEADLINE_AMOUNT.split(value)
    return ''.join(
        f'<span class="editorial-amount">{escape(part)}</span>' if index % 2 else escape(part)
        for index, part in enumerate(parts)
    )


def editorial_frame(path, body, sections, *, heading='', reading=False):
    links = ''.join(
        f'<a href="{route}"' + (' aria-current="page"' if path == route else '') + f'>{label}</a>'
        for route, label in sections.items()
    )
    nav = f'<nav class="editorial-tabs" aria-label="资讯导航">{links}</nav>'
    view = ' editorial-article' if reading else ''
    body = body + nav if reading else heading + nav + body
    return f'<main class="quota-page news-page editorial-news{view}" id="main">{body}</main>'


def masthead(path, edition_at, sections):
    title = '前沿资讯' if path == '/news' else sections[path]
    issue = ''
    if edition_at:
        stamp = datetime.fromisoformat(edition_at).astimezone(BEIJING)
        issue = (
            f'<time class="editorial-issue" datetime="{escape(edition_at)}">'
            f'<span class="editorial-issue-date">{stamp:%m.%d}</span>'
            f'<span class="editorial-issue-meta"><span>AI 每日速递</span>'
            f'<span>{stamp:%Y} 年 · {stamp:%H:%M} 北京时间</span></span></time>'
        )
    return f'<header class="editorial-masthead"><h1>{escape(title)}</h1>{issue}</header>'


def filter_form(path, sources, query, source, days, edition_at):
    labels = {'': '全部来源', **{item['id']: item['name'] for item in sources}}
    if not edition_at:
        labels['archive'] = '恢复的历史记录'
    return (
        f'<form class="editorial-filters" action="{path}" role="search" aria-label="搜索资讯">'
        '<label class="editorial-search-field"><span class="sr-only">关键词</span>'
        '<span class="editorial-search-icon" aria-hidden="true"></span>'
        f'<input type="search" name="q" value="{escape(query)}" placeholder="搜索标题、摘要或来源" maxlength="140">'
        '</label><label class="editorial-select"><span class="sr-only">信息源</span>'
        f'<select name="source">{options(labels, source)}</select></label>'
        '<label class="editorial-select"><span class="sr-only">日期</span>'
        f'<select name="days">{options(PERIODS, days)}</select></label>'
        '<button type="submit">查找</button></form>'
    )


def category(item, sections):
    return sections.get('/' + item.get('section', ''), sections['/news'])


def article_url(item):
    return '/article/' + escape(item['id'])


def published(item, *, short=False):
    value = item['published_at'] or item['observed_at']
    date = value if len(value) == 10 else china_time(value)
    label = date[5:16] if short and len(date) >= 16 and date[4] == '-' else date
    return f'<time datetime="{escape(value)}" title="{escape(date)}">{escape(label)}</time>'


def flag(item):
    return '<span class="editorial-notice">未经证实</span>' if item['unverified'] else ''


def arrow():
    return '<span class="editorial-arrow" aria-hidden="true">↗</span>'


def feature(item, quick_items, sections):
    details = (
        f'<span>{escape(item["source"])}</span>{published(item, short=True)}'
    )
    lead = (
        '<article class="editorial-feature">'
        f'<div class="editorial-feature-label"><span>本期头条</span><span>{escape(category(item, sections))}</span></div>'
        f'<h2><a href="{article_url(item)}">{headline(item["title"])}{arrow()}</a></h2>'
        f'<p class="editorial-deck">{escape(item["summary"])}</p>'
        f'<div class="editorial-feature-meta">{details}</div></article>'
    )
    if not quick_items:
        return f'<div class="editorial-spotlight editorial-spotlight-single">{lead}</div>'
    entries = ''.join(
        f'<li><p class="editorial-quick-meta"><span>{escape(category(entry, sections))}</span>'
        f'{published(entry, short=True)}<span>{escape(entry["source"])}</span>{flag(entry)}</p>'
        f'<a href="{article_url(entry)}">{escape(entry["title"])}</a></li>'
        for entry in quick_items
    )
    return (
        f'<div class="editorial-spotlight">{lead}<aside class="editorial-quick" aria-labelledby="quick-heading">'
        f'<h2 id="quick-heading">本期速览</h2><ul>{entries}</ul></aside></div>'
    )


def article_row(item, sections):
    return (
        '<article class="editorial-row"><div class="editorial-row-index">'
        f'<span class="editorial-category">{escape(category(item, sections))}</span>'
        f'{published(item, short=True)}</div><div class="editorial-row-copy">'
        f'<h3><a href="{article_url(item)}">{escape(item["title"])}{arrow()}</a></h3>'
        f'<p class="editorial-row-summary">{escape(item["summary"])}</p>'
        f'<p class="editorial-row-source">{escape(item["source"])}{flag(item)}</p>'
        '</div></article>'
    )


def pagination(path, query, source, days, offset, total):
    links = []
    for label, position in (('← 上一页', offset - 20), ('下一页 →', offset + 20)):
        if 0 <= position < total:
            params = urlencode({'q': query, 'source': source, 'days': days, 'offset': position})
            links.append(f'<a href="{path}?{escape(params)}">{label}</a>')
    if not links:
        return ''
    page = f'第 {offset // 20 + 1} / {(total + 19) // 20} 页'
    return (
        f'<nav class="editorial-pages" aria-label="分页"><span>{page}</span>'
        f'<div>{"".join(links)}</div></nav>'
    )


def list_page(path, items, total, sources, *, sections=SECTIONS, edition_at=None, **filters):
    query, source, days, offset = (filters[key] for key in ('query', 'source', 'days', 'offset'))
    active_filters = bool(query or source or days != ('all' if edition_at else '30'))
    search = filter_form(path, sources, query, source, days, edition_at)
    spotlight = ''
    rows = items
    if path == '/news' and not active_filters and offset == 0:
        top_story = next((item for item in items if not item['unverified']), None)
        if top_story:
            remaining = [item for item in items if item['id'] != top_story['id']]
            spotlight = feature(top_story, remaining[:3], sections)
            rows = remaining[3:]
    heading = '搜索结果' if active_filters else ('本期资讯' if edition_at else '资讯列表')
    clear = f'<a class="editorial-clear" href="{path}">清除筛选</a>' if active_filters else ''
    results = (
        '<section class="editorial-feed" aria-labelledby="feed-heading">'
        f'<header class="editorial-feed-head"><h2 id="feed-heading">{heading}</h2>'
        f'<div><span>{total} 条资讯</span>{clear}</div></header>'
        + ''.join(article_row(item, sections) for item in rows)
        + ('<p class="editorial-empty">当前没有符合条件的资讯。</p>' if not items else '')
        + '</section>'
    )
    footer = pagination(path, query, source, days, offset, total)
    return editorial_frame(path, search + spotlight + results + footer, sections, heading=masthead(path, edition_at, sections))


def detail(item, *, sections=SECTIONS, active=''):
    target = active if active in sections else '/news'
    label = sections[target]
    category_label = escape(category(item, sections))
    excerpt = item['summary']
    if excerpt in item['body'] or excerpt == item.get('reading_intro'):
        excerpt = ''
    summary = f'<p class="editorial-deck">{escape(excerpt)}</p>' if excerpt else ''
    back = (
        f'<div class="editorial-return"><a class="editorial-back" href="{target}">'
        f'<span aria-hidden="true">←</span> 返回{escape(label)}</a></div>'
    )
    body = (
        f'{back}<article class="editorial-document"><header class="editorial-document-head">'
        f'<p class="editorial-category">{category_label}</p>'
        f'<h1>{headline(item["title"])}</h1>{summary}'
        f'<div class="editorial-document-meta"><span>{escape(item["source"])}</span>{published(item)}</div>'
        f'</header><div class="editorial-document-body">{article_content(item)}</div></article>'
    )
    return editorial_frame(target, body, sections, reading=True)

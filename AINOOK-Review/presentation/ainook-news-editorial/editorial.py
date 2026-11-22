"""Editorial list and reading templates mounted by the local preview."""
from datetime import datetime
from html import escape
import re
from urllib.parse import urlencode

from ainook.news_views import (
    IMAGE_ASSETS, PAGES, PERIODS, SECTIONS, article_content, article_source,
    briefing_page, options, published, source_page, unavailable,
)
from ainook.quota import BEIJING

HEADLINE_AMOUNT = re.compile(r'(\d[\d,.]*[ \u00a0]?(?:万亿美元|万亿元|亿美元|亿元|万亿|%))')


def headline(value):
    parts = HEADLINE_AMOUNT.split(value)
    return ''.join(
        f'<span class="editorial-amount">{escape(part)}</span>' if index % 2 else escape(part)
        for index, part in enumerate(parts)
    )


def channel_attr(route):
    return f'data-channel="{escape(route.rsplit("/", 1)[-1])}"'


def channel_nav(path, sections):
    links = []
    for route, label in sections.items():
        current = ' aria-current="page"' if path == route else ''
        if route == '/rumors':
            link = (f'<a class="editorial-channel-rumor" href="{route}" {channel_attr(route)}{current} '
                    f'aria-label="{escape(label)}" aria-describedby="editorial-rumor-note">'
                    '<span class="editorial-channel-icon" aria-hidden="true"></span>'
                    f'<span class="editorial-rumor-label">{escape(label)}'
                    '<small id="editorial-rumor-note">未经证实</small></span></a>')
        else:
            link = (f'<a class="editorial-channel" href="{route}" {channel_attr(route)}{current}>'
                    '<span class="editorial-channel-icon" aria-hidden="true"></span>'
                    f'<span>{escape(label)}</span></a>')
        links.append(link)
    return '<nav class="editorial-tabs" aria-label="资讯导航">' + ''.join(links) + '</nav>'


def frame(path, body, sections, *, heading='', reading=False):
    nav = channel_nav(path, sections)
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


def category_route(item, sections):
    route = '/' + item.get('section', '')
    return route if route in sections else '/news'


def category_tag(route, sections):
    return f'<span class="editorial-category" {channel_attr(route)}>{escape(sections[route])}</span>'


def article_url(item):
    return '/article/' + escape(item['id'])


def flag(item):
    return '<span class="editorial-notice">未经证实</span>' if item['unverified'] else ''


def arrow():
    return '<span class="editorial-arrow" aria-hidden="true">↗</span>'


def feature(item, quick_items, sections):
    route = category_route(item, sections)
    details = (
        f'<span>{escape(item["source"])}</span>{published(item, short=True)}'
    )
    lead = (
        f'<article class="editorial-feature" {channel_attr(route)}>'
        f'<div class="editorial-feature-label"><span>本期头条</span>{category_tag(route, sections)}</div>'
        f'<h2><a href="{article_url(item)}">{headline(item["title"])}{arrow()}</a></h2>'
        f'<p class="editorial-deck">{escape(item["summary"])}</p>'
        f'<div class="editorial-feature-meta">{details}</div></article>'
    )
    if not quick_items:
        return f'<div class="editorial-spotlight editorial-spotlight-single">{lead}</div>'
    entries = ''.join(
        f'<li><p class="editorial-quick-meta">{category_tag(category_route(entry, sections), sections)}'
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
        f'{category_tag(category_route(item, sections), sections)}'
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
    return frame(path, search + spotlight + results + footer, sections, heading=masthead(path, edition_at, sections))


def detail(item, *, sections=SECTIONS, active=''):
    target = active if active in sections else '/news'
    label = sections[target]
    route = category_route(item, sections)
    excerpt = item['summary']
    if excerpt in item['body'] or excerpt == item.get('reading_intro'):
        excerpt = ''
    summary = f'<p class="editorial-deck">{escape(excerpt)}</p>' if excerpt else ''
    back = (
        f'<div class="editorial-return"><a class="editorial-back" href="{target}">'
        f'<span aria-hidden="true">←</span> 返回{escape(label)}</a></div>'
    )
    body = (
        f'{back}<article class="editorial-document" {channel_attr(route)}><header class="editorial-document-head">'
        f'<div class="editorial-document-category">{category_tag(route, sections)}</div>'
        f'<h1>{headline(item["title"])}</h1>{summary}'
        f'<div class="editorial-document-meta">{article_source(item)}{published(item)}</div>'
        f'</header><div class="editorial-document-body">{article_content(item)}</div></article>'
    )
    return frame(target, body, sections, reading=True)

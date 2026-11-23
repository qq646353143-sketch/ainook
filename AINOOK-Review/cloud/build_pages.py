"""Render the public news edition as an independent GitHub Pages backup."""

from argparse import ArgumentParser
from html import escape
import json
from pathlib import Path
import re
from shutil import copyfile
import sys
from time import sleep
from urllib.parse import urlsplit

from sync_edition import ROOT, SOURCE, load_edition, publish_time

from ainook import views
from ainook.news_edition import EDITIONS
from ainook.quota import utcnow

PRESENTATION = ROOT / 'presentation/ainook-news-editorial'
sys.path.insert(0, str(PRESENTATION))
import editorial

PRIMARY = 'https://ainook.ainook-cloud.workers.dev'
PUBLIC_PATH = re.compile(r'(href|src|action)="(/(?!/)[^"]*)"')
NEWS_ARTICLE = re.compile(r'/article/[a-f0-9]{24}')
THEME_AND_STYLE = re.compile(r'<script>.*?</script><style>.*?</style>', re.S)
NAVIGATION = re.compile(r'(<nav class="site-nav"[^>]*>).*?(<button class="theme-switch")', re.S)


def internal_path(path, base):
    parsed = urlsplit(path)
    page = parsed.path
    if page.startswith('/assets/'):
        return base + path
    if page in ('/', '/news'):
        return base + '/'
    if page in EDITIONS or page == '/news/sources' or NEWS_ARTICLE.fullmatch(page):
        suffix = path[len(page):]
        return base + page + '/' + suffix
    return PRIMARY + path


def rewrite_links(html, base):
    def link(match):
        name, path = match.groups()
        return f'{name}="{internal_path(path, base)}"'
    return PUBLIC_PATH.sub(link, html)


def build_pages(edition, destination, base):
    stylesheet = (PRESENTATION / 'editorial.css').read_text(encoding='utf-8')
    read_static = views.static
    views.static = lambda name: stylesheet if name == 'news-editorial.css' else read_static(name)
    edition_at = edition.updated.isoformat()
    sources = list(edition.sources.values())
    assets = destination / 'assets'
    assets.mkdir(parents=True, exist_ok=True)

    def write_page(route, title, body, *, filtering=False):
        html, _ = views.page(route, {'title': title + ' · 备用入口', 'news_html': body}, '')
        html = html.decode('utf-8')
        html = NAVIGATION.sub(
            r'\1<a href="/news" aria-current="page">资讯备用入口</a>'
            rf'<a href="{PRIMARY}/">AINOOK 主站 ↗</a>\2', html, count=1)
        html = THEME_AND_STYLE.sub(
            '<script src="/assets/theme.js"></script><link rel="stylesheet" href="/assets/backup-news.css">',
            html, count=1)
        if filtering:
            html = html.replace('</head>', '<script src="/assets/backup-search.js" defer></script></head>', 1)
            html = html.replace('class="editorial-filters"', 'class="editorial-filters" data-edition="' +
                                escape(edition_at) + '"', 1)
        page_dir = destination if route == '/news' else destination / route.lstrip('/')
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / 'index.html').write_text(rewrite_links(html, base), encoding='utf-8')

    def save_index(route, entries):
        directory = destination if route == '/news' else destination / route.lstrip('/')
        payload = [{
            'source': row['source'], 'publishedAt': row['published_at'],
            'search': ' '.join((row['title'], row['summary'], row['source'], *row['body'])).casefold(),
            'html': rewrite_links(editorial.article_row(row, EDITIONS), base),
        } for row in entries]
        (directory / 'search.json').write_text(
            json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    try:
        css = '\n'.join(views.static(name) for name in ('home.css', 'interaction.css', 'news.css', 'news-editorial.css'))
        css = css.replace("'/assets/", f"'{base}/assets/")
        (assets / 'backup-news.css').write_text(css, encoding='utf-8')
        (assets / 'theme.js').write_text(views.static('theme.js'), encoding='utf-8')
        copyfile(Path(__file__).with_name('pages_search.js'), assets / 'backup-search.js')
        for name in ('Geist-Variable.woff2', 'Geist-Variable.ttf', 'Geist-OFL.txt', 'night-sky.webp', *editorial.IMAGE_ASSETS):
            copyfile(views.STATIC / 'assets' / name, assets / name)

        for route, title in EDITIONS.items():
            rows = [row for row in edition.ordered if route == '/news' or '/' + row['section'] == route]
            body = editorial.list_page(route, rows, len(rows), sources, sections=EDITIONS,
                                       edition_at=edition_at, query='', source='', days='all', offset=0)
            # The static edition includes the whole list on one page.
            body = re.sub(r'<nav class="editorial-pages"[^>]*>.*?</nav>', '', body)
            write_page(route, title, body, filtering=True)
            save_index(route, rows)
        for row in edition.ordered:
            route = '/article/' + row['id']
            body = editorial.detail(row, sections=EDITIONS, active='/' + row['section'])
            write_page(route, row['title'], body)
        write_page('/news/sources', '资讯数据来源', editorial.source_page(sections=EDITIONS))
    finally:
        views.static = read_static
    (destination / '.nojekyll').touch()
    print(f'AINOOK Pages news edition: {edition_at}, {len(edition.ordered)} items')


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--edition', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base', default='/ainook')
    parser.add_argument('--wait-for-release', action='store_true')
    args = parser.parse_args()
    edition, _ = load_edition(args.edition)
    delay = (publish_time(edition) - utcnow()).total_seconds()
    if args.wait_for_release and delay > 0:
        if delay > 7200:
            raise ValueError('Edition timestamp is more than two hours ahead')
        print(f'Waiting until {publish_time(edition).isoformat()}', flush=True)
        sleep(delay)
    build_pages(edition, args.output, args.base.rstrip('/'))


if __name__ == '__main__':
    main()

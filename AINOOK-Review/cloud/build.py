"""Package the existing AINOOK renderers as Cloudflare static assets."""

from argparse import ArgumentParser
import json
from pathlib import Path
from runpy import run_path
from shutil import copyfile
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from ainook import site, views
from ainook.news_edition import EDITIONS, LEGACY_SECTIONS, NewsEdition


def build(edition_path, reset_path, assets, generated):
    files = run_path(str(ROOT / 'presentation/ainook-author-gallery/serve.py'))
    editorial = files['editorial']
    gallery = files['RoomGallery']()
    origin = ''
    internal = assets / '_ainook'
    internal.mkdir(parents=True, exist_ok=True)
    generated.mkdir(parents=True, exist_ok=True)
    policies = {}

    def html(name, render):
        body, policy = render
        file = internal / (name + '.html')
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(body)
        policies['/_ainook/' + name + '.html'] = policy

    def write_json(path, data):
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    original = views.static
    views.static = lambda name: (files['file_text'](files['NEWS'] / 'editorial.css')
                                 if name == 'news-editorial.css' else original(name))
    try:
        with TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            copyfile(reset_path, data_dir / 'reset-watch-hourly.json')
            app = site.AllowanceSite(data_dir, data_dir / 'wishes.sqlite3', data_dir / 'origin.json')
            cards = app.cards()
            html('home', views.page('/', cards, origin))
            for days in views.RANGES:
                for platform in ('', *cards['totals']):
                    html(f'quota/{days}-{platform or "all"}', views.page(
                        '/quota', {'items': app.quota.overview(), 'days': days, 'platform': platform}, origin))
        html('privacy', views.page('/privacy', {}, origin))
        for theme in ('', 'day', 'night'):
            options = {'theme-preview': [theme]} if theme else {}
            suffix = '-' + theme if theme else ''
            html('author/directory' + suffix, gallery.render('/author', {}, origin, options))
            for key in gallery.scenes:
                html('author/room-' + key + suffix, gallery.render('/author', {}, origin, {**options, 'room': [key]}))
            for key in gallery.friend_scenes:
                html('author/friend-' + key + suffix, gallery.render('/author', {}, origin, {**options, 'friend': [key]}))
            if gallery.acan_original:
                html('author/friend-acan-original' + suffix, gallery.render(
                    '/author', {}, origin, {**options, 'friend': ['acan'], 'scene': ['original']}))
        edition = NewsEdition(edition_path)
        updated = edition.updated.isoformat()
        sources = list(edition.sources.values())
        for route, title in EDITIONS.items():
            filters = dict(query='', source='', days='all', offset=0)
            items, total = edition.articles(mode=route.lstrip('/'), **filters)
            body = editorial.list_page(route, items, total, sources, sections=EDITIONS, edition_at=updated, **filters)
            html(route.removeprefix('/'), views.page(route, {'title': title, 'news_html': body}, origin))
        article_files = internal / 'article'
        article_files.mkdir(exist_ok=True)
        index = []
        for item in edition.ordered:
            path = 'article/' + item['id']
            body = editorial.detail(item, sections=EDITIONS, active='/' + item['section'])
            html(path, views.page('/' + path, {'title': item['title'], 'news_html': body}, origin))
            inline = editorial.article_content(item, inline=True)
            (internal / (path + '-inline.html')).write_text(inline, encoding='utf-8')
            write_json(internal / (path + '.json'), item)
            search = ' '.join((item['title'], item['summary'], item['source'], *item['body'])).casefold()
            index.append({key: item[key] for key in ('id', 'section', 'source', 'published_at')} |
                         {'search': search, 'row': editorial.article_row(item, EDITIONS)})
        body = editorial.source_page(sections=EDITIONS)
        html('news/sources', views.page('/news/sources',
             {'title': editorial.PAGES['/news/sources'], 'news_html': body}, origin))
    finally:
        views.static = original
    write_json(internal / 'news-index.json', {'updated': updated, 'sources': sources, 'items': index})
    copyfile(reset_path, internal / 'resets.json')
    write_json(internal / 'initial-cards.json', cards)
    write_json(generated / 'routes.json', {'policies': policies, 'news': list(EDITIONS), 'legacy': LEGACY_SECTIONS,
                                         'rooms': list(gallery.scenes), 'friends': list(gallery.friend_scenes)})

    target = assets / 'assets'
    target.mkdir(exist_ok=True)
    for name in {**app.assets, **editorial.IMAGE_ASSETS}:
        copyfile(views.STATIC / 'assets' / name, target / name)
    for name, (raw, _) in gallery.assets.items():
        (target / name).write_bytes(raw)
    (assets / '_headers').write_text(
        '/assets/room-*.webp\n  Cache-Control: public, max-age=31536000, immutable\n'
        '/assets/*\n  X-Content-Type-Options: nosniff\n', encoding='utf-8')
    print(f'AINOOK build: {len(index)} news items, {len(policies)} pages, {len(gallery.assets)} room images.')


if __name__ == '__main__':
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--edition', type=Path, default=ROOT / 'published/reader-cloud.json')
    parser.add_argument('--resets', type=Path, default=ROOT / 'published/reset-watch-hourly.json')
    parser.add_argument('--assets', type=Path, default=HERE / 'public')
    parser.add_argument('--generated', type=Path, default=HERE / 'generated')
    args = parser.parse_args()
    build(args.edition, args.resets, args.assets, args.generated)

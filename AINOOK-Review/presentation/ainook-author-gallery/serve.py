"""Run AINOOK with the current editorial pages and author-room gallery."""
import argparse
from contextlib import closing
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sqlite3
import sys
from urllib.parse import parse_qs, urlencode, urlsplit

GALLERY = Path(__file__).resolve().parent
PROTOTYPES = GALLERY.parent
CLASSIC = PROTOTYPES / 'ainook-author-room'
STUDIES = PROTOTYPES / 'ainook-author-room-studies'
LAKESIDE = PROTOTYPES / 'ainook-author-lakeside'
CRAFT = PROTOTYPES / 'ainook-author-lakeside-craft'
NEWS = PROTOTYPES / 'ainook-news-editorial'
DIRECTORY_TITLE = '一些奇思妙想'
ROOT = GALLERY.parents[1]
sys.path[:0] = [str(ROOT), str(NEWS)]

from ainook import site, views
from ainook.wishes import Wishes

import editorial


def file_text(path):
    return path.read_text(encoding='utf-8')


def wish_path():
    target = GALLERY / 'preview-wishes.sqlite3'
    source = NEWS / 'preview-wishes.sqlite3'
    if not target.exists() and source.is_file():
        with closing(sqlite3.connect(f'{source.as_uri()}?mode=ro', uri=True)) as db:
            totals = db.execute('SELECT platform, total FROM totals ORDER BY rowid').fetchall()
        wishes = Wishes(target, [platform for platform, _ in totals])
        with wishes.connect() as db:
            db.executemany('INSERT OR REPLACE INTO totals VALUES(?, ?)', totals)
    return target


class RoomGallery:
    def __init__(self):
        self.assets = {}
        studies = json.loads(file_text(STUDIES / 'rooms.json'))
        corrections = json.loads(file_text(GALLERY / 'study-corrections.json'))
        for room in studies:
            fixes = corrections.get(room['id'], {})
            room['objects'] = [{**item, **fixes.get(item['name'], {})} for item in room['objects']]
        self.studies = {room['id']: room for room in studies}
        self.names = {'classic': '初版书房', **{room['id']: room['name'] for room in studies},
                      'lakeside': '湖边小屋', 'craft': '湖畔木作', 'tram': '山坡电车'}
        friends = json.loads(file_text(GALLERY / 'friends' / 'rooms.json'))
        self.friends = {friend['id']: friend for friend in friends}
        self.classic_day = self.image_uri(CLASSIC / 'author-room.webp')
        self.classic_night = self.image_uri(GALLERY / 'art' / 'classic-night.webp')
        self.guest = self.image_uri(LAKESIDE / 'art' / 'guest.webp')
        self.scenes = {room: self.load_scene(room) for room in self.names}
        self.friend_scenes = {key: self.friend_scene(key) for key in self.friends}
        self.acan_original = self.friend_scene('acan', original=True) if 'acan' in self.friends else None
        self.residents = [{
            'id': 'author', 'title': '作者小屋', 'room': self.names['tram'], 'route': {'room': 'tram'},
            'image': self.image_uri(GALLERY / 'tram' / 'thumb.webp'),
        }]
        self.residents.extend({
            **friend, 'title': friend['name'] + '的小屋', 'route': {'friend': key},
            'image': self.image_uri(GALLERY / 'friends' / key / 'thumb.webp'),
        } for key, friend in self.friends.items())

    def image_uri(self, path):
        raw = path.read_bytes()
        name = f'room-{sha256(raw).hexdigest()[:24]}.webp'
        self.assets[name] = (raw, 'image/webp')
        return f'/assets/{name}'

    def load_scene(self, room):
        if room == 'classic':
            return self.classic_scene()
        if room in self.studies:
            return self.study_scene(room)
        if room == 'tram':
            folder = GALLERY / room
            image = self.image_uri(folder / f'{room}.webp')
            html = file_text(folder / 'author.html').replace(f'__{room.upper()}_IMAGE__', image)
            css = file_text(folder / f'{room}.css')
            return html, css, file_text(folder / f'{room}.js')
        return self.lakeside_scene(room)

    def classic_scene(self):
        html = file_text(CLASSIC / 'author.html').replace('__ROOM_IMAGE__', self.classic_day)
        img = ('<img class="gallery-classic-night" alt="夜里的微缩书房。窗外的山林隐在蓝色夜色里，远处有几盏灯。" '
               'width="1536" height="1024" src="' + self.classic_night + '">')
        html = html.replace('<div class="miniature-room-lamp"', img + '\n        <div class="miniature-room-lamp"', 1)
        css = file_text(CLASSIC / 'room.css') + '\n' + file_text(GALLERY / 'classic.css')
        return html, css, file_text(CLASSIC / 'room.js')

    def study_scene(self, room):
        data = {**self.studies[room], 'image': self.image_uri(STUDIES / 'art' / f'{room}.webp')}
        payload = escape(json.dumps([data], ensure_ascii=False), quote=False)
        html = file_text(STUDIES / 'author.html').replace('__ROOM_STUDIES__', payload)
        html = html.replace('      <nav class="room-studies-choices" aria-label="小屋预览方案" hidden></nav>\n', '', 1)
        script = file_text(STUDIES / 'room.js')
        css = file_text(STUDIES / 'room.css') + '\n' + file_text(GALLERY / 'studies.css')
        return html, css, script

    def lakeside_scene(self, room):
        root = CRAFT if room == 'craft' else LAKESIDE
        html = file_text(LAKESIDE / 'author.html').replace('__LAKESIDE_SCENE__', self.image_uri(root / 'art' / 'lakeside.webp'))
        html = html.replace('__LAKESIDE_GUEST__', self.guest)
        css = file_text(LAKESIDE / 'room.css')
        if root == CRAFT:
            css += '\n' + file_text(CRAFT / 'room.css')
        css += '\n' + file_text(GALLERY / f'{room}.css')
        return html, css, file_text(LAKESIDE / 'room.js')

    def friend_scene(self, key, original=False):
        folder = GALLERY / 'friends' / key
        friend = self.friends[key]
        duo = GALLERY / 'duo'
        template, artwork, script = (duo / 'author.html', folder / 'original-web.webp', duo / 'duo.js') if original else (
            folder / 'room.html', folder / 'room.webp', folder / 'room.js')
        html = file_text(template)
        html = html.replace('__FRIEND_IMAGE__', self.image_uri(artwork))
        if '__FRIEND_MOBILE_IMAGE__' in html:
            html = html.replace('__FRIEND_MOBILE_IMAGE__', self.image_uri(folder / 'room-mobile.webp'))
        html = html.replace('__FRIEND_NAME__', escape(friend['name'])).replace('__FRIEND_INTRO__', escape(friend['intro']))
        css = file_text(STUDIES / 'room.css')
        if friend.get('base') == 'duo':
            css += '\n' + file_text(duo / 'duo.css')
        scene_css = 'original.css' if original else 'room.css'
        return html, css + '\n' + file_text(folder / scene_css), file_text(script)

    @staticmethod
    def link(query, theme):
        if theme in ('day', 'night'):
            query = {**query, 'theme-preview': theme}
        return escape('/author' + ('?' + urlencode(query) if query else ''))

    def directory(self, theme):
        cards = []
        for resident in self.residents:
            link = self.link(resident['route'], theme)
            cards.append(
                f'<li><a class="house-door" href="{link}" data-house-link data-resident="{escape(resident["id"])}">'
                f'<div class="house-door-art"><img src="{resident["image"]}" alt="" width="512" height="768" loading="lazy" decoding="async"></div>'
                f'<div class="house-door-label"><h2>{escape(resident["title"])}</h2>'
                f'<span aria-hidden="true">进屋 →</span><p>{escape(resident["room"])}</p></div></a></li>'
            )
        return (f'<main class="house-directory" id="main"><h1>{DIRECTORY_TITLE}</h1>'
                '<ul class="house-doors">' + ''.join(cards) + '</ul></main>')

    def nav(self, selected, theme):
        links = []
        for room, name in self.names.items():
            href = self.link({'room': room}, theme)
            current = ' aria-current="page"' if room == selected else ''
            links.append(f'<a href="{href}" data-house-link data-room-choice="{room}"{current}>{name}</a>')
        return '<nav class="author-gallery-variants" aria-label="作者小屋方案">' + ''.join(links) + '</nav>'

    def render(self, path, data, canonical, search):
        selected = search.get('room', [''])[0]
        theme = search.get('theme-preview', [''])[0]
        friend = search.get('friend', ['acan' if selected == 'duo' else ''])[0]
        individual = True
        if friend in self.friend_scenes:
            main, css, script = self.friend_scenes[friend]
            if friend == 'acan':
                original = search.get('scene') == ['original']
                if original:
                    main, css, script = self.acan_original
                links = []
                for scene, label in (('original', '初版电竞房'), ('studio', '写歌电竞房')):
                    query = {'friend': friend, 'scene': 'original'} if scene == 'original' else {'friend': friend}
                    active = ' aria-current="page"' if (scene == 'original') == original else ''
                    links.append(f'<a href="{self.link(query, theme)}" data-house-link data-room-choice="{scene}"{active}>{label}</a>')
                nav = f'<nav class="author-gallery-variants friend-gallery-variants" aria-label="阿灿的小屋版本">{"".join(links)}</nav>'
                main = main.replace('</header>', nav + '\n    </header>', 1)
            main = main.replace('id="main"', f'id="main" data-room-variant="friend" data-friend="{friend}"', 1)
            title = self.friends[friend]['name'] + '的小屋'
        elif not friend and selected in self.scenes and search.get('wing') != ['friends']:
            html, css, script = self.scenes[selected]
            html = html.replace('<h1>作者小屋</h1>\n      ', '', 1)
            html = html.replace('<h2 id="author-name">爱学习x</h2>', '<h1 id="author-name">爱学习x</h1>', 1)
            main = html.replace('</section>', '</section>\n' + self.nav(selected, theme), 1)
            main = main.replace('id="main"', f'id="main" data-room-variant="{selected}"', 1)
            title = '爱学习x的小屋'
        else:
            individual = False
            main, css, script = self.directory(theme), '', ''
            title = DIRECTORY_TITLE
        if individual:
            opening, rest = main.split('>', 1)
            back = f'<a class="house-back" href="{self.link({}, theme)}" data-house-link>← {DIRECTORY_TITLE}</a>'
            main = opening + '>\n' + back + rest
        css += '\n' + file_text(GALLERY / 'gallery.css')
        gallery_script = file_text(GALLERY / 'gallery.js')
        script += '\n' + gallery_script
        body, policy = views.page(path, data, canonical)
        previous_title = f'<title>{escape(views.PAGES[path][0])}</title>'.encode()
        body = body.replace(previous_title, f'<title>{escape(title)} · ainook.</title>'.encode(), 1)
        body = body.replace(views.static('author.html').encode(), main.encode(), 1)
        body = body.replace(b'</head>', f'<style>{css}</style>\n</head>'.encode(), 1)
        body = body.replace(b'</body>', f'<script>{script}</script>\n</body>'.encode(), 1)
        policy = policy.replace("style-src 'self'", f"style-src 'self' {views.source_hash(css)}", 1)
        policy = policy.replace("script-src 'self'", f"script-src 'self' {views.source_hash(script)}", 1)
        return body, policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=7896)
    parser.add_argument('--bind', choices=('127.0.0.1', '0.0.0.0'), default='127.0.0.1')
    parser.add_argument('--data-dir', type=Path, default=ROOT.parent / 'outputs/ainook')
    parser.add_argument('--wish-db', type=Path)
    parser.add_argument('--origin-file', type=Path)
    parser.add_argument('--production', action='store_true')
    parser.add_argument('--no-quota-scheduler', action='store_true')
    parser.add_argument('--reset-feed-url', default=site.PUBLISHED_URL)
    parser.add_argument('--trial-dir', type=Path, help='Use a separate origin configuration and visitor counter for a public test.')
    args = parser.parse_args()
    if args.production:
        config = site.json_file(args.origin_file, {}) if args.origin_file else {}
        if not isinstance(config, dict) or not site.https_origin(config):
            parser.error('Production requires an HTTPS origin in --origin-file.')
        if not args.wish_db:
            parser.error('Production requires a persistent --wish-db.')
        if args.trial_dir:
            parser.error('Use a production origin and database rather than --trial-dir.')
        try:
            site.NewsEdition(args.data_dir / site.EDITION_FILE)
        except (OSError, ValueError, KeyError, TypeError) as error:
            parser.error(f'Production requires a readable reader-edition.json ({type(error).__name__}).')
    gallery = RoomGallery()
    original_static = views.static

    def preview_static(name):
        return file_text(NEWS / 'editorial.css') if name == 'news-editorial.css' else original_static(name)

    class GalleryServer(site.LocalHTTPServer):
        def __init__(self, address, handler):
            class GalleryHandler(handler):
                def html_page(self, path, data, canonical, status=200):
                    if path != '/author':
                        return super().html_page(path, data, canonical, status)
                    search = parse_qs(urlsplit(self.path).query)
                    body, policy = gallery.render(path, data, canonical, search)
                    headers = {'Content-Security-Policy': policy}
                    if not canonical:
                        headers['X-Robots-Tag'] = 'noindex'
                    return self.respond(status, body, 'text/html; charset=utf-8', headers)

            super().__init__(address, GalleryHandler)

    views.static = preview_static
    site.news_views = editorial
    site.LocalHTTPServer = GalleryServer
    if args.trial_dir:
        args.trial_dir.mkdir(parents=True, exist_ok=True)
        counter = args.trial_dir / 'wishes.sqlite3'
        origin = args.trial_dir / 'public-origin.json'
    else:
        counter = args.wish_db or wish_path()
        origin = args.origin_file or GALLERY / 'local-origin.json'
    site.serve(port=args.port, bind=args.bind, scheduler=args.production,
               quota_scheduler=not args.no_quota_scheduler, data_dir=args.data_dir, wish_path=counter,
               origin_file=origin, versioned_assets=gallery.assets,
               reset_feed_url=None if args.no_quota_scheduler or not (args.production or args.trial_dir)
               else args.reset_feed_url)


if __name__ == '__main__':
    main()

"""Allowance boundary and degraded-source behavior, using isolated state."""
from datetime import datetime, timedelta, timezone
from contextlib import closing
import gzip
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ainook.quota import Quota, normalize
from ainook.news import News, search_entries
from ainook.news_copy import evidence_copy, reading_copy
from ainook.news_events import additional_excerpt, event_attention, evidence_sentences, same_event, story_key
from ainook.news_translate import MARKER, translate_article, translate_pending
from ainook.news_views import article_rows, detail
from ainook.views import card_events
from ainook.wishes import Wishes


class AllowanceDataTests(unittest.TestCase):
    def test_forecast_and_announcement_are_separate(self):
        now = datetime.fromisoformat('2026-11-18T13:00:00+00:00')
        with tempfile.TemporaryDirectory() as tmp:
            quota = Quota(Path(tmp) / 'verified.json')
            quota.sync(lambda source: normalize(' '.join(
                phrase for record in source['records'] for phrase in record['evidence'])), now=now)
            codex, claude, grok = [card_events(item['records'], now=now) for item in quota.overview(now=now)]
        self.assertIsNone(codex['next_event'])
        self.assertIsNone(codex['issued_day'])
        self.assertEqual(codex['estimate']['samples'], 3)
        self.assertEqual(claude['issued_day'], '2026-11-11')
        self.assertIsNone(claude['estimate'])
        self.assertEqual(grok['issued_day'], '2026-11-10')

        published = {'id': 'future-test', 'type': 'reset', 'status': 'verified',
                     'url': 'https://quota.example/official'}
        at = (now + timedelta(days=1)).isoformat()
        self.assertEqual(card_events([{**published, 'scheduled_at': at}], now=now)['next_event']['at'], at)
        self.assertIsNone(card_events([{**published, 'status': 'stale', 'scheduled_at': at}], now=now)['next_event'])

    def test_failure_and_changed_content_preserve_last_verified_record(self):
        now = datetime.fromisoformat('2026-11-18T13:00:00+00:00')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            quota = Quota(path / 'verified.json')
            quota.sync(lambda source: normalize(' '.join(
                phrase for record in source['records'] for phrase in record['evidence'])), now=now)
            claude = quota.overview(now=now)[1]
            self.assertEqual(claude['records'][1]['status'], 'expired')
            self.assertEqual(claude['records'][2]['status'], 'verified')

            def offline(_):
                raise OSError('no connection')

            later = now + timedelta(hours=6)
            quota.sync(offline, now=later)
            older = quota.overview(now=later)[1]['records'][0]
            self.assertEqual(older['status'], 'stale')
            self.assertEqual(older['verified_at'], now.isoformat())
            self.assertEqual(older['checked_at'], later.isoformat())

            quota.sync(lambda _: 'new content', now=later)
            changed = quota.overview(now=later)[1]['records'][0]
            self.assertEqual(changed['status'], 'review')
            self.assertEqual(changed['summary'], older['summary'])

    def test_wishes_survive_reopen_and_duplicate_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'wishes.sqlite3'
            wishes = Wishes(path, ['codex'])
            self.assertEqual(wishes.add('codex', 20, 'test-batch-key-0001')['total'], 20)
            wishes = Wishes(path, ['codex', 'another-platform'])
            self.assertTrue(wishes.add('codex', 20, 'test-batch-key-0001')['duplicate'])
            self.assertEqual(wishes.totals(), {'codex': 20, 'another-platform': 0})


class PublicHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        data = Path(cls.tmp.name)
        cls.scope = data / 'origin.json'
        with socket.socket() as free:
            free.bind(('127.0.0.1', 0))
            port = free.getsockname()[1]
        cls.base = f'http://127.0.0.1:{port}'
        cls.process = subprocess.Popen(
            [sys.executable, '-m', 'ainook.site', '--port', str(port), '--no-scheduler',
             '--data-dir', str(data), '--wish-db', str(data / 'wishes.sqlite3'), '--origin-file', str(cls.scope)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(60):
            try:
                with urlopen(cls.base + '/api/site/status', timeout=1):
                    return
            except OSError:
                time.sleep(.05)
        cls.tearDownClass()
        raise RuntimeError('test server unavailable')

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=8)
        cls.tmp.cleanup()

    def request(self, path, headers=None, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        req = Request(self.base + path, body, headers or {})
        try:
            response = urlopen(req, timeout=5)
        except HTTPError as exc:
            response = exc
        with response:
            return response.code, response.headers, response.read()

    def test_pages_assets_and_routes(self):
        code, headers, body = self.request('/', {'Accept-Encoding': 'gzip'})
        self.assertEqual(code, 200)
        self.assertEqual(headers['X-Robots-Tag'], 'noindex')
        self.assertEqual(headers['Content-Encoding'], 'gzip')
        self.assertIn(b'initial-cards', gzip.decompress(body))
        quota = self.request('/quota')[2].decode()
        self.assertIn('历史记录', quota)
        self.assertIn('个人剩余额度', quota)
        self.assertIn('上次核对', quota)
        self.assertIn('原帖发布时间 · 北京时间', quota)
        self.assertNotIn('站主历史记录', quota)
        code, _, author = self.request('/author')
        self.assertEqual(code, 200)
        self.assertIn('作者小屋 · ainook.'.encode(), author)
        self.assertEqual(self.request('/privacy')[0], 200)
        for path in ['/voices', '/briefing']:
            self.assertEqual(self.request(path)[0], 410)
        for path in ['/news', '/news/model', '/news/official', '/news/hot', '/news/world',
                     '/news/finance', '/rumors', '/models', '/news/sources', '/api/site/news']:
            self.assertEqual(self.request(path)[0], 200)
        self.assertIn('精选简报'.encode(),self.request('/news')[2])
        self.assertNotIn('模型排行榜'.encode(),self.request('/news')[2])
        for path in ['/api/site/refresh', '/api/site/article/a', '/article/abcdef', '/.env',
                     '/outputs/intelligence/intelligence.sqlite3', '/config/home_reset_records.json']:
            self.assertEqual(self.request(path)[0], 404)
        code, headers, _ = self.request('/assets/Geist-Variable.woff2')
        self.assertEqual(code, 200)
        self.assertEqual(self.request('/assets/Geist-Variable.woff2', {'If-None-Match': headers['ETag']})[0], 304)
        code, headers, image = self.request('/assets/night-sky.webp')
        self.assertEqual((code, headers['Content-Type'], image[8:12]), (200, 'image/webp', b'WEBP'))

    def test_write_guard_and_batch(self):
        url = '/api/site/wishes'
        payload = {'platform':'codex', 'count':2, 'batch_id':'site-sample-batch-002'}
        headers = {'Content-Type':'application/json', 'Origin':self.base}
        self.assertEqual(self.request(url, {**headers,'Origin':'https://example.org'}, payload)[0], 403)
        self.assertEqual(self.request(url, headers, {**payload,'count':201})[0], 400)
        first = json.loads(self.request(url, headers, payload)[2])
        retry = json.loads(self.request(url, headers, payload)[2])
        self.assertTrue(retry['duplicate'])
        self.assertEqual(first['total'], retry['total'])
        self.assertEqual(self.request('/', {'Host':'unconfigured.example'})[0], 403)

    def test_official_scope_and_sitemap(self):
        self.scope.write_text(json.dumps({'origin':'https://quota.example', 'public_scope':'official'}))
        try:
            cards = json.loads(self.request('/api/site/cards')[2])['items']
            self.assertTrue(all('manual' not in card and 'latest' in card for card in cards))
            code, _, body = self.request('/sitemap.xml')
            self.assertEqual(code, 200)
            self.assertIn(b'https://quota.example/quota</loc>', body)
            self.assertNotIn(b'/news', body)
            self.assertIn(b'<link rel="canonical" href="https://quota.example/quota">', self.request('/quota')[2])
        finally:
            self.scope.unlink()

    def test_history_filters_and_scope(self):
        grok = self.request('/quota?days=all&platform=grok')[2].decode()
        self.assertIn('id="grok-20261110"', grok)
        self.assertIn('公告范围限于 Grok Bot', grok)
        self.assertNotIn('id="codex-20261113"', grok)
        claude = self.request('/quota?days=all&platform=claude')[2].decode()
        self.assertIn('2026-12-11 06:00 北京时间', claude)
        self.assertNotIn('id="grok-20261110"', claude)


class NewsCollectionTests(unittest.TestCase):
    def test_lexical_recall_uses_source_leads_without_merging_followups(self):
        lead = '公司今天向开发者发布了新的代码生成工具。开发者可直接在官方控制台试用，并能查看每次调用的详细计费记录。'
        primary = story_key('公司发布全新的代码生成工具', lead)
        alternate = story_key('公司推出全新的代码生成工具供开发者试用', lead)
        self.assertTrue(same_event(primary, alternate))
        self.assertFalse(same_event(primary, story_key('公司回应全新的代码生成工具实测问题', lead)))
        self.assertFalse(same_event(story_key('正式发布 GPT-4.7'), story_key('正式发布 GPT-4.8')))

    def test_latency_weight_uses_distinct_owners_and_provenance_sentences(self):
        now = datetime.now(timezone.utc)
        rows = [
            {'source': source, 'url': f'https://{source}.example/story', 'published': stamp.isoformat()}
            for source, stamp in (('a', now), ('b', now - timedelta(hours=10)), ('c', now - timedelta(hours=24)),
                                  ('d', now - timedelta(hours=50)))
        ]
        self.assertEqual(event_attention(rows, {'a': 'same-owner', 'b': 'same-owner'}, now), (2, 1.5))
        primary = '原文称试用额度是每人 20 次，适用于个人用户。'
        seen = [(key, figures) for _, key, figures in evidence_sentences(primary)]
        self.assertEqual(additional_excerpt(primary + '企业用户仍需使用独立的管理入口。', seen),
                         '企业用户仍需使用独立的管理入口。')

    def test_briefing_reuses_articles_from_mutually_exclusive_sections(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            news = News(root)
            def fetch(source, _):
                entries = {
                    'openai-news': [('Model 4 is now available', 'https://example.org/release'),
                                    ('ChatGPT desktop settings update', 'https://example.org/settings'),
                                    ('How to use the model', 'https://example.org/tutorial')],
                    'ars-ai': [('AI security update', 'https://example.org/security'),
                               ('AI pricing reportedly changing', 'https://example.org/tip')],
                    'hn-ai-search': [('New AI model released', 'https://example.org/release'),
                                     ('New AI model reportedly released', 'https://example.org/lead')],
                    'simon-voice': [('AI model reportedly released', 'https://example.org/author/post')],
                }
                return [{'title': title, 'url': url, 'raw_time': now.isoformat(), 'summary': 'Details are now available.'}
                        for title, url in entries.get(source['id'], [])], {}
            added = sum(item['added'] for item in news.collect(force=True, fetch=fetch))
            self.assertEqual(added, 5)
            self.assertEqual(sum(item['added'] for item in news.collect(force=True, fetch=fetch)), 0)
            class FixtureTranslator:
                def __init__(self, _):
                    pass

                def translate(self, fields):
                    return ['测试译文 ' + ' '.join(match.group() for match in MARKER.finditer(field))
                            for field in fields]

            self.assertEqual(translate_pending(news, factory=FixtureTranslator)['translated'], 4)
            self.assertEqual(news.refresh_briefing(now=now)['items'], 2)
            day, stories = news.briefing()
            self.assertEqual([story['original_title'] for story in stories], ['Model 4 is now available', 'AI security update'])
            self.assertEqual(News(root).briefing()[0], day)
            updates, update_count = news.articles(mode='updates')
            official, official_count = news.articles(mode='official')
            hot, hot_count = news.articles(mode='hot')
            self.assertEqual((update_count, official_count, hot_count), (1, 1, 1))
            self.assertEqual(updates[0]['original_title'], 'Model 4 is now available')
            self.assertEqual(official[0]['original_title'], 'ChatGPT desktop settings update')
            self.assertEqual(hot[0]['original_title'], 'AI security update')
            self.assertEqual([item['id'] for item in stories], [updates[0]['id'], hot[0]['id']])
            leads, count = news.articles(mode='rumors')
            self.assertEqual(count, 1)
            discovered = leads[0]
            self.assertEqual(discovered['kind'], 'voice')
            self.assertIsNotNone(discovered['published_at'])
            self.assertIn('未经证实', detail(news.article(discovered['id'])))

    def test_event_group_uses_comparable_points_and_preserves_other_sources(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            news = News(tmp)
            def fetch(source, _):
                def report(title, slug, summary=''):
                    return {'title': title, 'url': f'https://example.org/{slug}',
                            'raw_time': now.isoformat(), 'summary': summary}
                lines = {
                    'openai-news': [report('GPT-4.7 正式发布', 'official', '官方披露了模型能力和开放详情。')],
                    'ars-ai': [report('GPT-4.7 正式亮相', 'media', '媒体公开报道这一发布。'),
                               report('GPT-4.8 正式发布', 'other', '不同模型版本。')],
                    'hn-ai-search': [dict(report('GPT-4.7 released', 'official'), points=20,
                                          thread='https://news.ycombinator.com/item?id=10'),
                                     dict(report('GPT-4.7 launches', 'media'), points=50,
                                          thread='https://news.ycombinator.com/item?id=11')],
                }
                return lines.get(source['id'], []), {}
            news.collect(force=True, fetch=fetch)
            self.assertEqual(news.merge_events(), 1)
            items, total = news.articles(mode='updates', days='all')
            self.assertEqual(total, 2)
            winner = next(item for item in items if item['url'].endswith('/media'))
            info = news.article(winner['id'])
            self.assertEqual(info['community_points'], 50)
            self.assertEqual([source['url'] for source in info['related']], ['https://example.org/official'])
            self.assertIn('开放详情', info['related'][0]['excerpt'])

    def test_failed_translation_is_unpublished_until_delayed_retry_succeeds(self):
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            news = News(tmp)
            def fetch(source, _):
                return ([{'title': 'AI security update', 'summary': 'The provider released a patch.',
                          'url': 'https://example.org/security',
                          'raw_time': now.isoformat()}] if source['id'] == 'ars-ai' else []), {}
            class Translator:
                good = False

                def __init__(self, _):
                    pass

                def translate(self, fields):
                    return ['安全更新' if self.good else 'not translated' for _ in fields]

            news.collect(force=True, fetch=fetch)
            self.assertEqual(translate_pending(news, factory=Translator)['failed'], 1)
            self.assertEqual(news.articles(mode='hot')[1], 0)
            self.assertEqual(translate_pending(news, factory=Translator)['failed'], 0)
            with closing(news.connect()) as db, db:
                db.execute('UPDATE translation_retry SET next_at=?', ((now - timedelta(hours=1)).isoformat(),))
            Translator.good = True
            self.assertEqual(translate_pending(news, factory=Translator)['translated'], 1)
            self.assertEqual(news.articles(mode='hot')[0][0]['title'], '安全更新')
            self.assertEqual(translate_pending(news, factory=Translator)['translated'], 0)

    def test_search_without_publication_date_keeps_index_stamp(self):
        payload = {'articles': [{'title': 'OpenAI releases new model', 'url': 'https://example.org/model',
                                 'seendate': '20261118T120000Z'},
                                {'title': 'New model announced', 'url': 'https://example.org/no-date'}]}
        results = search_entries({'method': 'gdelt_search'}, json.dumps(payload))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['raw_time'], '2026-11-18T12:00:00+00:00')

    def test_blocked_source_skipped_and_incremental_translation_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = [
                {'id': key, 'name': key, 'url': f'https://{key}.example/feed', 'method': 'rss',
                 'kind': 'official', 'language': 'en', 'enabled': True} for key in ('denied', 'working')
            ]
            config = root / 'source.json'
            config.write_text(json.dumps({'sources': sources, 'initial_days': 30, 'interval_hours': 6,
                                          'translate_per_cycle': 10, 'entries_per_source': 5}))
            news = News(root, config_path=config)
            calls = []
            published = datetime.now(timezone.utc).isoformat()

            def fetch(source, state):
                calls.append(source['id'])
                if source['id'] == 'denied':
                    raise HTTPError(source['url'], 403, 'Forbidden', {}, None)
                return [{'title': 'Model 4 is now available', 'summary': 'The API supports the model.',
                         'url': 'https://working.example/article?utm_source=rss', 'raw_time': published}], {'etag': 'v1'}

            first = news.collect(force=True, fetch=fetch)
            self.assertEqual(first[0]['state'], 'disabled')
            self.assertEqual(first[1]['added'], 1)
            calls.clear()
            self.assertEqual(news.collect(force=True, fetch=fetch)[0]['added'], 0)
            self.assertEqual(calls, ['working'])

            class FakeTranslator:
                def __init__(self, _):
                    pass

                def translate(self, values):
                    return ['模型 [NAME_0] 现已上线', '接口支持该模型。']

            self.assertEqual(translate_pending(news, factory=FakeTranslator)['translated'], 1)
            self.assertEqual(translate_pending(news, factory=FakeTranslator)['translated'], 0)
            items, total = news.articles(query='上线', days='all')
            self.assertEqual(total, 1)
            self.assertEqual(items[0]['original_title'], 'Model 4 is now available')
            self.assertEqual(items[0]['translation'], 'offline')

    def test_reading_copy_uses_complete_sentences_and_keeps_paragraphs(self):
        raw = 'GPT-6.2 is available. The previous summary cut this in th'
        self.assertEqual(evidence_copy(raw, 250), 'GPT-6.2 is available.')
        raw = 'GPT-6.2 is available. A second sentence was cut in the mid…'
        self.assertEqual(evidence_copy(raw, 250), 'GPT-6.2 is available.')
        first = '模型现已开放。'
        second = '这段说明包含完整句子，' * 13 + '应该从头到尾保留。'
        summary, body = reading_copy(first + '\n\n' + second)
        self.assertEqual(summary, first)
        self.assertEqual(body, [first, second])
        self.assertIn(second, article_rows([{'id': 'a', 'title': '模型发布', 'summary': second, 'unverified': False}]))

    def test_translation_preserves_edition_and_enforces_markers_in_body(self):
        class Translator:
            def translate(self, fields):
                self.fields = fields
                return ['可在 [NAME_0] 使用 [NAME_1]。']

        translator = Translator()
        title, body = translate_article(translator, 'Introducing Gemini 4 Neon',
                                        'Use Gemini 4 Neon in GitHub Copilot. Learn more about th')
        self.assertEqual(title, 'Gemini 4 Neon 发布')
        self.assertEqual(body, '可在 Gemini 4 Neon 使用 GitHub Copilot。')
        self.assertEqual(translator.fields, ['Use [NAME_0] in [NAME_1].'])

        class DroppingTranslator:
            def translate(self, fields):
                return ['可用。' for _ in fields]

        with self.assertRaises(ValueError):
            translate_article(DroppingTranslator(), 'Introducing Gemini 4 Neon', 'Use Gemini 4 Neon.')

    def test_article_material_adds_detail_and_keeps_feed_summary(self):
        now = datetime.now(timezone.utc)
        feed = '这次发布提供了开发者测试版本。'
        first = '符合条件的开发者可以在现有控制台申请使用，申请通过后能够从团队的测试环境中调用接口，用户需要保留现有的项目配置和访问权限。'
        second = '公开说明也给出了使用限制，测试版本开放期间会按请求量计算，管理员可以在账户的用量页面查看详细记录，并对不同项目单独设置限额。'
        with tempfile.TemporaryDirectory() as tmp:
            news = News(tmp)
            entries = [{'title': '新模型开放测试', 'url': 'https://openai.com/index/test',
                        'raw_time': now.isoformat(), 'summary': feed},
                       {'title': '旧模型公布停用计划', 'url': 'https://openai.com/index/blocked',
                        'raw_time': now.isoformat(), 'summary': feed}]
            news.collect(force=True, fetch=lambda source, _: (entries if source['id'] == 'openai-news' else [], {}))
            calls = []

            def fetch(url, _):
                calls.append(url)
                if url.endswith('blocked'):
                    raise HTTPError(url, 403, 'Forbidden', {}, None)
                return '\n\n'.join((feed, first, second))

            self.assertEqual(news.enrich_articles(fetch=fetch), 1)
            self.assertEqual(news.enrich_articles(fetch=fetch), 0)
            self.assertEqual(len(calls), 2)
            items, _ = news.articles(query='新模型')
            self.assertEqual(items[0]['summary'], feed)
            result = news.article(items[0]['id'])
            self.assertEqual(result['reading_intro'], feed)
            self.assertEqual(result['body'], [first, second])


if __name__ == '__main__':
    unittest.main()

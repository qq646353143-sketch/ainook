"""Read-only restoration of the old AI news records and current editorial reviews."""
from contextlib import closing
from datetime import timedelta
import json
import re
import sqlite3

from easel.intelligence.model import digest
from easel.intelligence.reader import EDITORIAL_VERSION, article_paragraphs

from .news import record, text
from .news_copy import evidence_copy
from .quota import utcnow


def import_archive(news, path):
    now = utcnow()
    lower = (now - timedelta(days=news.config['initial_days'])).date().isoformat()
    old_uri = path.resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(old_uri, uri=True)) as old:
        old.row_factory = sqlite3.Row
        sources = {row['id']: json.loads(row['config']) for row in old.execute('SELECT id, config FROM sources')}
        reviews = {row['event_id']: row for row in old.execute('SELECT * FROM reviews')}
        signatures = {}
        for row in old.execute('SELECT event_id, id, revision_hash FROM articles'):
            signatures.setdefault(row['event_id'], []).append(row['id'] + row['revision_hash'])
        articles = old.execute('''
            SELECT a.*, e.verification, json_extract(s.config,'$.tier') AS tier
            FROM articles a JOIN events e ON e.id=a.event_id JOIN sources s ON s.id=a.source_id
            WHERE e.category='ai' AND coalesce(a.published_at,json_extract(a.payload,'$.time.date'))>=?
            ORDER BY a.event_id,tier,a.published_at DESC
        ''', (lower,)).fetchall()

    imported = reviewed = 0
    seen = set()
    with closing(news.connect()) as db, db:
        for article in articles:
            event, source_id = article['event_id'], article['source_id']
            config = sources.get(source_id, {})
            tier = config.get('tier')
            verification = json.loads(article['verification'])
            if event in seen or tier not in (1, 2) or config.get('person') or config.get('kind') == 'manual':
                continue
            if verification.get('state') == '未经证实' or not re.fullmatch(r'[a-f0-9]{24}', event):
                continue
            review = reviews.get(event)
            review_data = {}
            if review and review['evidence_signature'] == digest('|'.join(sorted(signatures[event]))):
                review_data = json.loads(review['payload'])
                cited = review_data.get('reader_article_id') or next(
                    (fact['article_id'] for fact in review_data.get('facts', []) if fact.get('article_id')), None)
                if cited != article['id'] or review_data.get('reader_voice_kind'):
                    review_data = {}
            payload = json.loads(article['payload'])
            raw_time = payload.get('raw_time') or article['published_at'] or payload.get('time', {}).get('date')
            source = {
                'id': source_id, 'name': config.get('label', source_id),
                'kind': 'platform' if config.get('role') == 'platform' else 'official' if tier == 1 else 'media',
                'method': 'changelog' if config.get('kind') == 'changelog' else 'rss',
            }
            row = record(source, {'title': article['title'], 'url': article['canonical_url'],
                                  'summary': payload.get('summary'), 'raw_time': raw_time}, now,
                         archived=True, legacy_id=event)
            if not row:
                continue
            seen.add(event)
            if news.save_article(db, row):
                stored = {'id': row[0], 'content_key': row[-1]}
                imported += 1
            else:
                stored = db.execute('SELECT id, content_key FROM articles WHERE identity=?', (row[1],)).fetchone()
                if stored is None:
                    duplicate = news.duplicate_title(db, row)
                    if duplicate:
                        stored = db.execute('SELECT id, content_key FROM articles WHERE id=?', (duplicate['id'],)).fetchone()
                if stored is None:
                    continue
                db.execute('INSERT OR IGNORE INTO article_aliases VALUES (?,?)', (event, stored['id']))
            if review_data:
                headline = text(review_data.get('headline_zh'), 250)
                brief = evidence_copy(review_data.get('reader_summary') or review_data.get('one_sentence') or '', 650)
                body = article_paragraphs(brief, review_data.get('reader_body'),
                                          standalone=review_data.get('reader_editorial_version') == EDITORIAL_VERSION)
                if headline and any(body):
                    reviewed += db.execute('INSERT OR IGNORE INTO translations VALUES (?,?,?,?,?)',
                                           (stored['content_key'], headline, '\n\n'.join(body), 'reviewed', review['reviewed_at'])).rowcount
    return {'archived': imported, 'existing_chinese_reviews': reviewed}

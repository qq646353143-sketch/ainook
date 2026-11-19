"""Read-only news projection; collection and existing evidence remain intact."""
from __future__ import annotations
import json
import re
from datetime import datetime, timedelta, timezone
from .model import UTC, canonical_url, digest

CATEGORIES = {'ai', 'politics', 'economy'}
DISPLAY_ZONE=timezone(timedelta(hours=8))
EDITORIAL_VERSION=2

def calendar_entry(source, article, check):
    time=article.get('time',{})
    return (source.get('tier')==1 and source.get('kind')=='changelog'
            and time.get('precision')=='day' and re.fullmatch(r'\d{4}-\d{2}-\d{2}',time.get('date',''))
            and check.get('reasons')==[time.get('issue')])

def publication_key(item):
    stamp=item['published_at']
    if len(stamp)==10:return (stamp,'',item['id'])
    local=datetime.fromisoformat(stamp).astimezone(DISPLAY_ZONE)
    return (local.date().isoformat(),local.isoformat(),item['id'])

def chinese(text, minimum=8):
    return isinstance(text, str) and len(re.findall(r'[\u4e00-\u9fff]', text)) >= minimum

def sentences(text):
    return [s.strip() for s in re.findall(r'[^。！？]+[。！？]?', text or '') if s.strip()]

def article_paragraphs(brief, body, *, standalone=False):
    """Complete reading copy, with a safe introduction for older extra-only reviews."""
    paragraphs=[]
    values=body if isinstance(body,list) else []
    if not standalone:values=[brief,*values]
    for text in values:
        if chinese(text) and text.strip() not in paragraphs:paragraphs.append(text.strip())
    return paragraphs[:5] or [brief]

def formal_confirmation(article,source,summary,check):
    """An explicit, current review citing the actual formal first-party document."""
    proof=summary.get('reader_formal_confirmation')
    if not isinstance(proof,dict) or proof.get('article_id')!=article['id']:return False
    if source.get('tier')!=1 or source.get('kind')=='manual' or source.get('role') in ('research','platform','status'):return False
    if summary.get('reader_category')=='politics' and source.get('category')!='politics':return False
    if proof.get('type') not in ('formal_announcement','effective_rule','official_result'):return False
    quote=proof.get('quote','');payload=article['payload']
    if isinstance(payload,str):payload=json.loads(payload)
    hay=' '.join([article['title'],payload.get('summary',''),payload.get('raw_time','')])
    if not isinstance(quote,str) or len(quote)<12 or ' '.join(quote.split()) not in ' '.join(hay.split()):return False
    allowed={'高风险或传闻表述，需逐项核验正式信息','媒体报道，尚未完成独立来源交叉核验',payload.get('time',{}).get('issue')}
    return all(r in allowed for r in check.get('reasons',[]))

def news_rows(pipeline, category=None, *, now=None):
    """Fresh publication dates only. Changed evidence invalidates its Chinese review."""
    if category not in (None, '', *CATEGORIES): raise ValueError('无效新闻分类')
    now = now or datetime.now(UTC)
    lower = now - timedelta(hours=48)
    first_day=(now.astimezone(DISPLAY_ZONE).date()-timedelta(days=1)).isoformat()
    today=now.astimezone(DISPLAY_ZONE).date().isoformat()
    with pipeline.store.connect() as db:
        rows = db.execute('''SELECT a.*, e.category, e.verification FROM articles a
            JOIN events e ON a.event_id=e.id
            WHERE datetime(a.published_at) BETWEEN datetime(?) AND datetime(?)
               OR (a.published_at IS NULL AND json_extract(a.payload,'$.time.precision')='day'
                   AND json_extract(a.payload,'$.time.date') BETWEEN ? AND ?)
            ORDER BY datetime(a.published_at) DESC, a.id''', (lower.isoformat(), now.isoformat(),first_day,today)).fetchall()
        reviews = {r['event_id']: dict(r) for r in db.execute('SELECT * FROM reviews')}
        signatures = {}
        for a in db.execute('SELECT event_id,id,revision_hash FROM articles'):
            signatures.setdefault(a['event_id'], []).append(a['id'] + a['revision_hash'])
    sources = {s['id']: s for s in pipeline.sources}
    candidates = {}
    for row in rows:
        a = dict(row); eid = a['event_id']; source = sources.get(a['source_id'])
        payload = json.loads(a['payload']); check = json.loads(a['verification'])
        if not source or source.get('tier', 4) == 4 or not canonical_url(a['canonical_url']): continue
        dated=bool(calendar_entry(source,payload,check) and first_day<=payload['time']['date']<=today)
        try:
            if dated:published=payload['time']['date']
            else:
                instant=datetime.fromisoformat(a['published_at'])
                if instant.tzinfo is None or not lower<=instant<=now:continue
                published=instant.isoformat()
        except (ValueError, TypeError): continue
        review = reviews.get(eid)
        current_review = bool(review and review['evidence_signature'] == digest('|'.join(sorted(signatures.get(eid, [])))))
        # Reviewed media summaries may report what the named source said. This
        # never changes the underlying verification record or confirms its claims.
        attributed = bool(current_review and json.loads(review['payload']).get('reader_attributed_report'))
        formal=bool(current_review and formal_confirmation(a,source,json.loads(review['payload']),check))
        media_only = source.get('tier') == 2 and check.get('reasons') == ['媒体报道，尚未完成独立来源交叉核验']
        if check.get('state') == '未经证实' or (check.get('verification') == '待核实' and not (attributed and media_only) and not dated and not formal): continue
        if current_review:
            summary = json.loads(review['payload'])
            if summary.get('reader_voice_kind'):continue
            cited = summary.get('reader_article_id') or next((f.get('article_id') for f in summary.get('facts', []) if f.get('article_id')), None)
            if cited and a['id'] != cited: continue
            title = summary.get('headline_zh', '')
            brief = summary.get('reader_summary')
            if not brief:
                parts = sentences(summary.get('one_sentence', '').replace('；', '。'))
                for fact in summary.get('facts', []):
                    if len(parts) >= 2: break
                    text = fact.get('text', '')
                    if text and text not in ''.join(parts): parts += sentences(text)
                brief = ''.join(parts[:3])
            body = summary.get('reader_body', [f['text'] for f in summary.get('facts', []) if f.get('text')])
            group = summary.get('story_key') or eid
            kind = summary.get('reader_category', a['category'])
        else:
            if review: continue
            if source.get('tier', 4) not in (1, 2): continue
            title = a['title']; parts = sentences(payload.get('summary', ''))
            brief = ''.join(parts[:3]); body = parts[3:7]
            group, kind = eid, a['category']
        if not chinese(title,2) or not chinese(brief,20) or not 2<=len(sentences(brief))<=3:continue
        if kind not in CATEGORIES: continue
        body = article_paragraphs(brief,body,standalone=bool(current_review and summary.get('reader_editorial_version')==EDITORIAL_VERSION))
        item = {'id': eid, 'title': title, 'published_at': published,
                'source': source['label'], 'url': a['canonical_url'], 'category': kind,
                'summary': brief, 'body': body, 'original_title': a['title']}
        existing = candidates.get(group)
        if not existing or publication_key(item)>publication_key(existing): candidates[group] = item
    # Deduplicate before filtering; an older duplicate cannot reappear in another tab.
    items = [i for i in candidates.values() if not category or i['category'] == category]
    items.sort(key=publication_key, reverse=True)
    return {'items': items, 'total': len(items), 'window_hours': 48}

def news_detail(pipeline, eid):
    for item in news_rows(pipeline)['items']:
        if item['id'] == eid: return item
    raise KeyError('这条新闻暂不在最新阅读列表中')

"""Read a verified public reset snapshot without treating check time as event time."""

import json
from datetime import timedelta
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .quota import BEIJING, instant, json_file, utcnow, write_snapshot

PUBLISHED_URL = ('https://raw.githubusercontent.com/qq646353143-sketch/ainook/'
                 'main/AINOOK-Review/published/reset-watch-hourly.json')
INTERVAL = 60 * 60
PLATFORMS = {'codex', 'claude', 'grok'}
FORMS = {'banked_reset': 'banked', 'general_reset': 'reset'}
SOURCE_HOSTS = {'x.com', 'twitter.com', 'help.openai.com', 'openai.com',
                'support.claude.com', 'claude.com', 'anthropic.com', 'docs.x.ai', 'x.ai'}
X_STATUS = re.compile(r'/([A-Za-z0-9_]+)/status/([0-9]{1,19})/?')


def event_key(url):
    link = urlsplit(url)
    if link.hostname in ('x.com', 'twitter.com') and (match := X_STATUS.fullmatch(link.path)):
        return 'x:' + match[2]
    return url


def fetch_json(url):
    request = Request(url, headers={'Accept': 'application/json', 'User-Agent': 'AINOOK/1.0 reset monitor'})
    with urlopen(request, timeout=15) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError('Reset snapshot is too large')
    return json.loads(raw)


def validate(snapshot, now=None):
    now = now or utcnow()
    if not isinstance(snapshot, dict) or snapshot.get('timezone') != 'Asia/Shanghai':
        raise ValueError('Reset snapshot timezone is invalid')
    if not isinstance(snapshot.get('events'), list) or len(snapshot['events']) > 500:
        raise ValueError('Reset snapshot event list is invalid')
    event_ids = set()
    event_urls = set()
    for event in snapshot['events']:
        if not isinstance(event, dict):
            raise ValueError('Reset event is invalid')
        platform, kind = event.get('platform'), event.get('kind')
        if not isinstance(platform, str) or not isinstance(kind, str) or platform not in PLATFORMS or kind not in FORMS:
            raise ValueError('Reset event platform or kind is invalid')
        identity = event.get('id')
        if not isinstance(identity, str) or not identity.strip() or identity in event_ids:
            raise ValueError('Reset event ID is missing or duplicated')
        event_ids.add(identity)
        title = event.get('text')
        url = event.get('url')
        if not isinstance(title, str) or not title.strip() or len(title) > 600 or not isinstance(url, str):
            raise ValueError('Reset event text or URL is invalid')
        link = urlsplit(url)
        if (link.scheme != 'https' or link.hostname not in SOURCE_HOSTS or link.username or link.password
                or link.port not in (None, 443) or any(ord(char) < 33 for char in url)):
            raise ValueError('Reset source must be a recognized public URL')
        key = (event['platform'], event_key(url))
        if key in event_urls:
            raise ValueError('Reset event source is duplicated')
        event_urls.add(key)
        for field in ('expires_at', 'scheduled_at'):
            if event.get(field) is not None and not instant(event[field]):
                raise ValueError('Reset event optional timestamp is invalid')
        if event.get('person') is not None and not isinstance(event['person'], str):
            raise ValueError('Reset event source name is invalid')
        stamp = instant(event.get('announced_at'))
        confirmed = instant(event.get('confirmed_at'))
        if not stamp or stamp > now or event.get('state') not in ('pending', 'confirmed'):
            raise ValueError('Reset event time or status is invalid')
        if event['state'] == 'confirmed' and (not confirmed or not stamp <= confirmed <= now):
            raise ValueError('Confirmed reset requires a non-future confirmation time')
    return snapshot


def records(snapshot, now):
    for event in validate(snapshot, now)['events']:
        announced = instant(event['announced_at'])
        row = {'id': event['id'], 'platform': event['platform'], 'type': FORMS[event['kind']],
               'title': event['text'], 'summary': event['text'], 'audience': '适用账户以原公告为准。',
               'published_at': announced.isoformat(), 'source': event.get('person') or '公开重置公告',
               'url': event['url'], 'verified_at': announced.isoformat(), 'status': 'verified'}
        if expiry := instant(event.get('expires_at')):
            row['expires_at'] = expiry.isoformat()
        if event['state'] == 'confirmed':
            stamp = instant(event['confirmed_at'])
            row['confirmed_issued'] = True
            row['issued_on'] = stamp.astimezone(BEIJING).date().isoformat()
            row['verified_at'] = stamp.isoformat()
            if row['issued_on'] != now.astimezone(BEIJING).date().isoformat() and expiry and expiry <= now:
                row['status'] = 'expired'
        else:
            deadline = expiry or announced + timedelta(days=2)
            if when := instant(event.get('scheduled_at')):
                if when > now and deadline > now:
                    row['scheduled_at'] = when.isoformat()
            row['signal_until'] = deadline.isoformat()
        yield row


def update_cache(path, url, *, fetch=fetch_json, now=None):
    snapshot = validate(fetch(url), now)
    if snapshot != json_file(path, {}):
        write_snapshot(path, snapshot)

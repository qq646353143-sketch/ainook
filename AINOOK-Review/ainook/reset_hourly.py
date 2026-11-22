"""Publish verified reset announcements from public and editorial sources."""

from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .quota import fetch_text, instant, json_file, utcnow, write_snapshot
from .quota_watch import ACCOUNT_PLATFORMS, SIGNAL_WINDOW, classify
from .reset_feed import X_STATUS, event_key, fetch_json, validate

CODEX_FEED = 'https://codexresets.com/api/resets'
BLUESKY_FEED = 'https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed'
MIRRORS = {'anthropicai.xmirror.bot': 'claude', 'xai.xmirror.bot': 'grok'}
LOOKBACK = timedelta(days=30)
X_EPOCH_MS = 1288834974657
TITLES = {
    ('banked', True): '已发放重置卡',
    ('banked', False): '重置卡发放预告',
    ('reset', True): '已执行通用重置',
    ('reset', False): '通用重置预告',
}


def key(event):
    return event['platform'], event_key(event['url'])


def post_time(post_id):
    return datetime.fromtimestamp(((int(post_id) >> 22) + X_EPOCH_MS) / 1000, timezone.utc)


def codex_candidates(payload, now):
    if not isinstance(payload, dict) or not isinstance(payload.get('events'), list):
        raise ValueError('Codex feed event list is invalid')
    for row in payload['events']:
        if not isinstance(row, dict):
            continue
        stamp = instant(row.get('announced_at'))
        if not stamp or not now - LOOKBACK <= stamp <= now:
            continue
        if not isinstance(row.get('tweet_url'), str) or not isinstance(row.get('text'), str):
            continue
        link = urlsplit(row['tweet_url'])
        match = X_STATUS.fullmatch(link.path)
        if (link.scheme != 'https' or link.netloc.lower() not in ('x.com', 'twitter.com')
                or not match or match[2] != row.get('tweet_id')
                or ACCOUNT_PLATFORMS.get(match[1].casefold()) != 'codex'):
            continue
        post_stamp = post_time(match[2])
        if abs(post_stamp - stamp) > timedelta(seconds=2):
            continue
        result = classify(match[1], row['text'])
        if result:
            yield match[1], match[2], post_stamp, result[0]


def mirrored_candidates(payload, mirror, now):
    if not isinstance(payload, dict) or not isinstance(payload.get('feed'), list):
        raise ValueError('Social mirror entries are invalid')
    platform = MIRRORS[mirror]
    for entry in payload['feed']:
        post = entry.get('post') or {}
        record = post.get('record') or {}
        if (post.get('author', {}).get('handle') != mirror or entry.get('reason')
                or record.get('reply') or 'reset' not in record.get('text', '').casefold()):
            continue
        links = [feature.get('uri') for facet in record.get('facets', [])
                 for feature in facet.get('features', [])]
        links.append((record.get('embed') or {}).get('external', {}).get('uri'))
        for url in links:
            if not isinstance(url, str):
                continue
            link = urlsplit(url)
            match = X_STATUS.fullmatch(link.path)
            if (link.scheme != 'https' or link.netloc.lower() not in ('x.com', 'twitter.com')
                    or not match or ACCOUNT_PLATFORMS.get(match[1].casefold()) != platform):
                continue
            stamp = post_time(match[2])
            if now - LOOKBACK <= stamp <= now:
                yield match[1], match[2], stamp, platform


def collect(owner_path, output_path, *, now=None, fetch_feed=fetch_json, fetch_post=fetch_text):
    now = now or utcnow()
    owner = validate(json_file(owner_path, {}), now)
    previous = validate(json_file(output_path, {'timezone': 'Asia/Shanghai', 'events': []}), now)
    # The editorial file owns its corrections. Preserve independently verified events during outages.
    merged = {key(event): event for event in previous['events']
              if event.get('source') in ('codex-public-feed', 'public-x-original')}
    merged.update((key(event), event) for event in owner['events'])
    issues = []
    try:
        candidates = list(codex_candidates(fetch_feed(CODEX_FEED), now))
    except (OSError, ValueError) as error:
        candidates = []
        issues.append(f'Codex public index: {type(error).__name__}')
    for mirror in MIRRORS:
        try:
            params = urlencode({'actor': mirror, 'filter': 'posts_no_replies', 'limit': 25})
            candidates.extend(mirrored_candidates(fetch_feed(BLUESKY_FEED + '?' + params), mirror, now))
        except (OSError, ValueError, TypeError, AttributeError) as error:
            issues.append(f'{mirror}: {type(error).__name__}')
    for handle, post_id, stamp, platform in sorted(set(candidates), key=lambda candidate: candidate[2], reverse=True)[:12]:
        if (platform, 'x:' + post_id) in merged:
            continue
        url = f'https://x.com/{handle}/status/{post_id}'
        try:
            original = fetch_post({'url': url, 'format': 'x_embed'})
        except (OSError, ValueError) as error:
            issues.append(f'X post {post_id}: {type(error).__name__}')
            continue
        result = classify(handle, original)
        if not result or result[0] != platform:
            continue
        _, kind, confirmed = result
        event = {
            'id': 'rw-auto-x-' + post_id,
            'platform': platform,
            'kind': 'banked_reset' if kind == 'banked' else 'general_reset',
            'state': 'confirmed' if confirmed else 'pending',
            'announced_at': stamp.isoformat(),
            'confirmed_at': stamp.isoformat() if confirmed else None,
            'expires_at': None if confirmed else (stamp + SIGNAL_WINDOW).isoformat(),
            'text': TITLES[kind, confirmed],
            'url': url,
            'person': '@' + handle,
            'source': 'public-x-original',
        }
        merged[key(event)] = event
    events = [event for event in merged.values() if instant(event['announced_at']) >= now - LOOKBACK]
    events.sort(key=lambda event: (instant(event['announced_at']), event['id']), reverse=True)
    snapshot = validate({'timezone': 'Asia/Shanghai', 'events': events}, now)
    if snapshot != previous or not output_path.exists():
        write_snapshot(output_path, snapshot)
    return len(events), len(candidates), issues


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--owner', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    records, candidates, issues = collect(args.owner, args.output)
    print(f'{records} reset events; {candidates} candidates from public sources')
    for issue in issues:
        print(f'::warning::{issue}')


if __name__ == '__main__':
    main()

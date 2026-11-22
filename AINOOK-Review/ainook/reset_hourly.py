"""Publish verified reset announcements from public and editorial sources."""

from argparse import ArgumentParser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .quota import fetch_text, instant, json_file, utcnow, write_snapshot
from .quota_watch import ACCOUNT_PLATFORMS, SIGNAL_WINDOW, classify
from .reset_feed import X_STATUS, event_key, fetch_json, validate

CODEX_FEED = 'https://codexresets.com/api/resets'
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
        post_stamp = datetime.fromtimestamp(((int(match[2]) >> 22) + X_EPOCH_MS) / 1000, timezone.utc)
        if abs(post_stamp - stamp) > timedelta(seconds=2):
            continue
        result = classify(match[1], row['text'])
        if result:
            yield match[1], match[2], post_stamp, result


def collect(owner_path, output_path, *, now=None, fetch_feed=fetch_json, fetch_post=fetch_text):
    now = now or utcnow()
    owner = validate(json_file(owner_path, {}), now)
    previous = validate(json_file(output_path, {'timezone': 'Asia/Shanghai', 'events': []}), now)
    # The editorial file owns its corrections. Preserve independently verified events during outages.
    merged = {key(event): event for event in previous['events'] if event.get('source') == 'codex-public-feed'}
    merged.update((key(event), event) for event in owner['events'])
    issues = []
    try:
        candidates = list(codex_candidates(fetch_feed(CODEX_FEED), now))
    except (OSError, ValueError) as error:
        candidates = []
        issues.append(f'Codex public index: {type(error).__name__}')
    for handle, post_id, stamp, result in candidates:
        if ('codex', 'x:' + post_id) in merged:
            continue
        url = f'https://x.com/{handle}/status/{post_id}'
        try:
            original = fetch_post({'url': url, 'format': 'x_embed'})
        except (OSError, ValueError) as error:
            issues.append(f'X post {post_id}: {type(error).__name__}')
            continue
        if classify(handle, original) != result:
            continue
        _, kind, confirmed = result
        event = {
            'id': 'rw-auto-x-' + post_id,
            'platform': 'codex',
            'kind': 'banked_reset' if kind == 'banked' else 'general_reset',
            'state': 'confirmed' if confirmed else 'pending',
            'announced_at': stamp.isoformat(),
            'confirmed_at': stamp.isoformat() if confirmed else None,
            'expires_at': None if confirmed else (stamp + SIGNAL_WINDOW).isoformat(),
            'text': TITLES[kind, confirmed],
            'url': url,
            'person': '@' + handle,
            'source': 'codex-public-feed',
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
    print(f'{records} reset events; {candidates} actionable Codex candidates')
    for issue in issues:
        print(f'::warning::{issue}')


if __name__ == '__main__':
    main()

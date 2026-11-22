"""Poll official X accounts and project explicit quota announcements."""
from datetime import timedelta, timezone
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .quota import BEIJING, VendorRedirect, http_retry_at, instant, json_file, normalize, utcnow, write_snapshot

X_SEARCH = 'https://api.x.com/2/tweets/search/recent'
X_ACCOUNTS = {
    'OpenAI': 'codex', 'thsottiaux': 'codex',
    'ClaudeDevs': 'claude', 'claudeai': 'claude', 'AnthropicAI': 'claude',
    'bot': 'grok', 'Grok': 'grok', 'xAI': 'grok',
}
X_QUERY = ('(' + ' OR '.join('from:' + handle for handle in X_ACCOUNTS)
           + ') (reset OR resets) -is:retweet -is:quote -is:reply')
ACCOUNT_PLATFORMS = {handle.casefold(): platform for handle, platform in X_ACCOUNTS.items()}
PLATFORM_TERMS = {
    'codex': re.compile(r'\b(?:codex|chatgpt work)\b'),
    'claude': re.compile(r'\b(?:claude|pro|ultra|max|team)\b'),
    'grok': re.compile(r'\bgrok\b'),
}
LIMIT = r'(?:usage(?: limits?)?|(?:rate|weekly|quota) limits?|weekly quota|quota)\b'
CARD = r'(?:banked (?:usage |rate.limit )?resets?|reset cards?)\b'
CARD_ACTION = (r'(?:issued|sent|granted|added|given|distributed|provided)\s+'
               r'(?:(?:all eligible (?:users|accounts)|users|accounts|a|one|two|the|free|new|another|\d+)\s+){0,6}'
               + CARD)
RESET_ACTION = r'reset\s+(?:(?:the|all|eligible|your|their)\s+){0,3}' + LIMIT
PAST = r"\bwe(?:'ve just| have just| just)\s+"
FUTURE = r"\bwe(?:'ll| will| plan to| are going to)\s+"
FUTURE_CARD = CARD_ACTION.replace('issued|sent|granted|added|given|distributed|provided',
                                 'issue|send|grant|add|give|distribute|provide')
EXCLUDED = re.compile(r"\b(?:paid|purchase[ds]?|referrals?|yesterday|last (?:week|month)|every (?:day|week|month))\b")
ANNOUNCEMENTS = tuple(
    (kind, completed, re.compile(prefix + action))
    for kind, completed, prefix, action in (
        ('banked', True, PAST, CARD_ACTION),
        ('reset', True, PAST, RESET_ACTION),
        ('banked', False, FUTURE, FUTURE_CARD),
        ('reset', False, FUTURE, RESET_ACTION),
    )
)
PAGE_LIMIT = 5
OVERLAP = timedelta(minutes=15)
FIRST_WINDOW = timedelta(days=1)
MAX_LOOKBACK = timedelta(days=6, hours=23)
SIGNAL_WINDOW = timedelta(hours=48)


def fetch_x_page(params, token):
    request = Request(X_SEARCH + '?' + urlencode(params), headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/json',
        'User-Agent': 'AINOOK quota monitor',
    })
    with build_opener(VendorRedirect({'api.x.com'})).open(request, timeout=12) as response:
        raw = response.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('X response too large')
    return json.loads(raw)


def classify(handle, text):
    platform = ACCOUNT_PLATFORMS.get(handle.casefold())
    if not platform:
        return None
    text = normalize(text)
    if not PLATFORM_TERMS[platform].search(text) or EXCLUDED.search(text):
        return None
    matches = {(kind, completed) for kind, completed, pattern in ANNOUNCEMENTS if pattern.search(text)}
    return (platform, *matches.pop()) if len(matches) == 1 else None


def x_time(stamp):
    return stamp.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def project(post, authors, now):
    handle = authors[post['author_id']]
    post_id = post['id']
    stamp = instant(post['created_at'].replace('Z', '+00:00'))
    if not re.fullmatch(r'[0-9]{1,19}', post_id) or not stamp or stamp > now:
        raise ValueError('Invalid X post metadata')
    result = classify(handle, post['text'])
    if not result:
        return post_id, None
    platform, kind, completed = result
    title = {
        ('banked', True): '已发放重置卡', ('banked', False): '重置卡发放预告',
        ('reset', True): '已执行通用重置', ('reset', False): '通用重置预告',
    }[(kind, completed)]
    record = {
        'id': 'auto-x-' + post_id,
        'platform': platform,
        'type': kind,
        'title': title,
        'summary': '官方账号公布相关安排。覆盖的账户、限额和具体规则以原帖为准。',
        'audience': '以原帖说明为准',
        'published_at': stamp.isoformat(),
        'source': '@' + handle + ' · X 原帖',
        'url': f'https://x.com/{handle}/status/{post_id}',
        'verified_at': now.isoformat(),
        'checked_at': now.isoformat(),
        'status': 'verified',
    }
    if completed:
        record.update(confirmed_issued=True, issued_on=stamp.astimezone(BEIJING).date().isoformat())
    else:
        record['signal_until'] = (stamp + SIGNAL_WINDOW).isoformat()
    return post_id, record


def discover(path, token, *, now=None, fetch=fetch_x_page):
    if not token:
        return {'status': 'disabled'}
    now = now or utcnow()
    previous = json_file(path, {})
    retry_at = instant(previous.get('retry_at'))
    if retry_at and retry_at > now:
        return {'status': 'waiting', 'retry_at': retry_at.isoformat()}

    watermark = instant(previous.get('through')) or now - FIRST_WINDOW
    end = (now - timedelta(seconds=15)).replace(microsecond=0)
    start = max(now - MAX_LOOKBACK, min(end - OVERLAP, watermark - OVERLAP))
    params = {
        'query': X_QUERY, 'start_time': x_time(start), 'end_time': x_time(end), 'max_results': 100,
        'tweet.fields': 'created_at,author_id', 'expansions': 'author_id', 'user.fields': 'username',
    }
    records = dict(previous.get('records', {}))
    scanned = set()
    accepted = set()
    try:
        for _ in range(PAGE_LIMIT):
            page = fetch(params, token)
            if page.get('errors') or not isinstance(page.get('meta'), dict):
                raise ValueError('Incomplete X response')
            authors = {row['id']: row['username'] for row in page.get('includes', {}).get('users', [])}
            posts = page.get('data', [])
            if page['meta'].get('result_count') != len(posts):
                raise ValueError('Incomplete X page')
            for post in posts:
                post_id, record = project(post, authors, now)
                scanned.add(post_id)
                if record:
                    records[post_id] = record
                    accepted.add(post_id)
                else:
                    records.pop(post_id, None)
            if not (next_token := page['meta'].get('next_token')):
                break
            params['next_token'] = next_token
        else:
            raise ValueError('X pagination limit reached')
    except (OSError, KeyError, TypeError, AttributeError, ValueError) as error:
        state = {**previous, 'error': getattr(error, 'code', None) or type(error).__name__,
                 'checked_at': now.isoformat()}
        if retry := http_retry_at(error, now):
            state['retry_at'] = retry.isoformat()
        write_snapshot(path, state)
        return {'status': 'error', 'reason': state['error']}

    write_snapshot(path, {'through': end.isoformat(), 'checked_at': now.isoformat(), 'records': records})
    return {'status': 'ok', 'checked': len(scanned), 'accepted': len(accepted)}

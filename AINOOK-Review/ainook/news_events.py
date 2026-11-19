"""Conservative event matching and representative selection for recent news."""
from datetime import date, datetime, timedelta
import re
import unicodedata
from typing import NamedTuple
from urllib.parse import urlsplit

MODEL_NAME = re.compile(
    r'\b(?:gpt|gemini|llama|qwen|grok|deepseek|mistral|minimax|kimi|glm|ernie|claude)'
    r'[- ]*(?:(?:opus|sonnet|haiku|v|r|k)[- ]*)?\d+(?:\.\d+)*'
    r'(?:[- ]+(?:mini|nano|flash|pro|turbo|neon|carbon|argon|hydrogen|astra|sol))?\b', re.I)
LAUNCH = re.compile(r'\b(?:releas(?:es?|ed|ing)|launch(?:es|ed)?|introduc(?:es|ing|ed)|unveil(?:s|ed)?|announc(?:es|ed|ing)|debuts?)\b|发布|推出|亮相', re.I)
CHANGE = re.compile(r'\b(?:upgrad\w*|deprecat\w*|retir\w*|discontinu\w*|open weights|open.sourc\w*|now available|roll(?:ing|s)? out|model update|supports? the model)\b|升级|下线|停用|开放|上线|版本更新|模型更新|模型开放', re.I)
OFF_TOPIC = re.compile(r'\b(?:funding|fundrais\w*|acqui[rs]\w*|lawsuit|partnership|guides?|tutorial|benchmarks? shows?)\b|融资|收购|诉讼|签订|教程|横评', re.I)
WORDS = re.compile(r'[a-z][a-z0-9.-]+|\d+(?:\.\d+)*|[\u3400-\u9fff]{2,}')
STOP = frozenset('the and for from its this that with about says said how what new model models after now more their into'.split())
VARIANT = r'mini|nano|flash|pro|turbo|neon|carbon|argon|hydrogen|astra|sol'
FOLLOW_UP = re.compile(r'\b(?:hands.on|review(?:s|ed)?|benchmarks?|react(?:s|ion)?|respond(?:s|ed)?|fix(?:es|ed)?|restor(?:es|ed)|revers(?:es|ed)|roll(?:ing|s)? back)\b|实测|评测|回应|更正|恢复|回滚', re.I)
ROUNDUP = re.compile(r'\b(?:roundup|weekly recap|top \d+)\b|汇总|盘点|周报', re.I)


class StoryKey(NamedTuple):
    words: frozenset
    names: frozenset
    numbers: frozenset
    launch: bool
    changed: bool
    follow_up: bool
    roundup: bool
    headline: frozenset
    lead: frozenset


def normalized(value):
    return unicodedata.normalize('NFKC', value).lower().translate(str.maketrans('‐‑–—', '----'))


def is_model_update(title, summary):
    headline = normalized(title)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}|[a-z]+ \d{1,2}, \d{4}', headline):
        headline = normalized(re.split(r'(?<=[.!?。！？])\s+', summary, maxsplit=1)[0])
    if OFF_TOPIC.search(headline):
        return False
    subject = MODEL_NAME.search(headline) or re.search(r'\bmodels?\b|模型', headline)
    return bool(subject and (LAUNCH.search(headline) or CHANGE.search(headline)))


def bigrams(value):
    # Port of AIHOT events/relate.ts lexicalSimilarity. See AIHOT-LICENSE.txt.
    chars = ''.join(value.split())
    return frozenset(chars[index:index + 2] for index in range(len(chars) - 1))


def lexical_similarity(left, right):
    return len(left & right) / min(len(left), len(right)) if left and right else 0


def story_key(title, summary=''):
    cleaned = normalized(title)
    words = frozenset(WORDS.findall(cleaned)) - STOP
    names = set()
    for match in MODEL_NAME.finditer(cleaned):
        name = match.group()
        names.add(re.sub(r'[- ]+', '', name))
        adjacent = re.match(r'\s*(?:and|/|&)\s+(' + VARIANT + r')\b', cleaned[match.end():])
        if adjacent:
            base = re.sub(r'[- ]+(?:' + VARIANT + r')$', '', name)
            names.add(re.sub(r'[- ]+', '', base) + adjacent[1])
    numbers = frozenset(re.findall(r'\d+(?:\.\d+)*', cleaned))
    launch = bool(LAUNCH.search(cleaned) or re.search(r'\bnow available\b|现已上线', cleaned))
    return StoryKey(words, frozenset(names), numbers, launch, bool(CHANGE.search(cleaned)),
                    bool(FOLLOW_UP.search(cleaned)), bool(ROUNDUP.search(cleaned)),
                    bigrams(cleaned), bigrams(normalized(summary[:300])))


def same_event(first, second):
    if first.roundup or second.roundup or first.follow_up != second.follow_up:
        return False
    if first.names and second.names and first.names != second.names:
        return False
    if first.numbers and second.numbers and first.numbers != second.numbers:
        return False
    if first.names and first.names == second.names and first.launch and second.launch and not first.follow_up:
        return True
    if (first.launch, first.changed) != (second.launch, second.changed):
        return False
    shared = first.words & second.words
    if len(shared) >= 4 and len(shared) / len(first.words | second.words) >= .68:
        return True
    headline_overlap = lexical_similarity(first.headline, second.headline)
    if len(first.headline & second.headline) >= 14 and headline_overlap >= .84:
        return True
    # A similar introduction is corroboration only when the headlines share a subject or wording.
    return ((headline_overlap >= .52 or bool(first.names & second.names))
            and len(first.lead & second.lead) >= 44
            and lexical_similarity(first.lead, second.lead) >= .82)


def group_events(rows):
    groups = []
    for row in rows:
        key = story_key(row['title'], row['summary'])
        day = date.fromisoformat(row['published'][:10])
        matched = None
        for started, anchor, members in reversed(groups):
            if day - started > timedelta(days=2):
                break
            if row['source'] != members[0]['source'] and same_event(key, anchor):
                matched = members
                break
        if matched is None:
            groups.append((day, key, [row]))
        else:
            matched.append(row)
    return [members for _, _, members in groups if len(members) > 1]


def representative(members):
    comparable = sum(row['points'] is not None for row in members) >= 2
    tier = {'official': 3, 'media': 2, 'platform': 1}
    return max(members, key=lambda row: (
        (-1 if row['points'] is None else row['points']) if comparable else 0,
        tier.get(row['kind'], 0), len(row['summary']), row['published'], row['id'],
    ))


def event_attention(members, owners, now):
    """AIHOT's 48h source-time window with one decaying signal per publisher."""
    newest = {}
    for row in members:
        published = datetime.fromisoformat(row['published'])
        if published.tzinfo is None or not now - timedelta(hours=48) <= published <= now:
            continue
        owner = owners.get(row['source']) or (urlsplit(row['url']).hostname or row['source']).removeprefix('www.')
        if owner not in newest or published > newest[owner]:
            newest[owner] = published
    if len(newest) < 2:
        return len(newest), 0
    return len(newest), sum(0.5 ** ((now - published).total_seconds() / 86400) for published in newest.values())


def evidence_sentences(content):
    for part in re.split(r'(?<=[。！？!?])|(?<=\.)\s+', content):
        phrase = part.strip()
        key = bigrams(normalized(phrase))
        figures = frozenset(re.findall(r'\d+(?:\.\d+)*', phrase))
        if len(key) >= 8:
            yield phrase, key, figures


def additional_excerpt(candidate, seen):
    """Keep distinct source sentences, including differing reported figures."""
    added = []
    for phrase, key, figures in evidence_sentences(candidate):
        duplicates = any(figures == old_figures and lexical_similarity(key, old) >= .87
                         for old, old_figures in seen)
        if duplicates:
            continue
        added.append(phrase)
        seen.append((key, figures))
        if len(added) == 2:
            break
    return ' '.join(added)

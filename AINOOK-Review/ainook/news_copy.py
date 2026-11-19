"""Sentence boundaries shared by the collector, translator, and news reader."""
import re
from difflib import SequenceMatcher


BOUNDARY = re.compile(r'[。！？]+[”’」』）】]*|[.!?]+[”’\"\')]*(?=\s|$)')
ABBREVIATION = re.compile(r'(?:\b(?:e\.g|i\.e|vs|Mr|Ms|Dr|Prof|Inc|Corp)\.|\b(?:[A-Z]\.){2,})$', re.I)
TERMINAL = re.compile(r'[。！？.!?][”’」』）】\"\')]*$')
TRUNCATED = re.compile(r'(?:…+|\.{2,}|\[\s*(?:…|\.\.\.)\s*\])\s*$')
DANGLING_ENGLISH = re.compile(r'\b(?:a|an|the|at|by|for|in|on|of|to|with|and|or|th)\s*$', re.I)
CONCRETE = re.compile(r'\b(?:available|access|roll(?:ing)? out|launch\w*|includ\w*|support\w*|'
                      r'price[ds]?|costs?|tokens?|eligib\w*|limits?|benchmarks?|requires?|developers?|'
                      r'subscribers?|users?|shipping|training)\b|开放|限额|价格|订阅|评测|限制', re.I)
BOILERPLATE = re.compile(r'^(?:read more|learn more|for more information|sign up|subscribe to|'
                         r'share your feedback|see all supported|this content is generated)\b', re.I)


def sentences(value, *, keep_tail=True):
    value = value.strip()
    start = 0
    for match in BOUNDARY.finditer(value):
        end = match.end()
        if end != len(value) and ABBREVIATION.search(value[start:end]):
            continue
        sentence = value[start:end].strip()
        if sentence:
            yield sentence
        start = end
    tail = value[start:].strip()
    if keep_tail and tail:
        yield tail


def paragraphs(value):
    """Keep source paragraph breaks and discard a known truncated trailing fragment."""
    blocks = [part.strip() for part in value.splitlines() if part.strip()]
    for block in blocks:
        truncated = TRUNCATED.search(block)
        if truncated:
            block = block[:truncated.start()].rstrip()
        parts = list(sentences(block, keep_tail=not truncated and not DANGLING_ENGLISH.search(block)))
        if parts:
            yield parts


def evidence_copy(value, limit):
    """Bound collected evidence, without cutting the last sentence in half."""
    output = []
    size = 0
    for block in paragraphs(value):
        selected = []
        for sentence in block:
            if size + len(sentence) > limit and (output or selected):
                if selected:
                    output.append(' '.join(selected))
                return '\n\n'.join(output)
            if len(sentence) > limit * 2:
                continue
            selected.append(sentence)
            size += len(sentence) + 1
        if selected:
            output.append(' '.join(selected))
    return '\n\n'.join(output)


def select_reading_facts(evidence, feed):
    """Choose a small mix of source-backed details beyond the feed introduction."""
    known = [' '.join(words.lower().split()) for block in paragraphs(feed) for words in block]
    candidates = []
    for position, block in enumerate(paragraphs(evidence)):
        best = None
        for sentence in block:
            if not 52 <= len(sentence) <= 370 or BOILERPLATE.search(sentence):
                continue
            key = ' '.join(sentence.lower().split())
            if any(key in old or (len(old) >= 52 and old in key)
                   or SequenceMatcher(None, key, old).ratio() >= 0.72 for old in known):
                continue
            score = len(set(word.casefold() for word in CONCRETE.findall(sentence)))
            score += min(2, len(re.findall(r'\d+(?:\.\d+)?\s*(?:%|million|美元|tokens?)', sentence, re.I)))
            if best is None or score > best[0]:
                best = (score, position, sentence, key)
        if best:
            candidates.append(best)
    selected = []
    for score, position, sentence, key in sorted(candidates, key=lambda item: (-item[0], item[1])):
        if any(SequenceMatcher(None, key, other).ratio() >= 0.72 for _, _, other in selected):
            continue
        if sum(len(part) for _, part, _ in selected) + len(sentence) > 1100:
            continue
        selected.append((position, sentence, key))
        if len(selected) == 5:
            break
    if len(selected) < 2:
        return ''
    return '\n\n'.join(sentence for _, sentence, _ in sorted(selected))


def reading_copy(value):
    """Return the complete lead and the paragraph sequence as separate fields."""
    def join(parts):
        return re.sub(r'([。！？][”’」』）】]*) +', r'\1', ' '.join(parts))

    blocks = list(paragraphs(value))
    has_source_breaks = len(blocks) > 1
    body = []
    lead = []
    lead_length = 0
    for block in blocks:
        pending = []
        size = 0
        for sentence in block:
            if not has_source_breaks and pending and size + len(sentence) > 105:
                body.append(join(pending))
                pending, size = [], 0
            pending.append(sentence)
            size += len(sentence)
            if not lead or (len(lead) == 1 and lead_length < 65 and lead_length + len(sentence) <= 150):
                lead.append(sentence)
                lead_length += len(sentence)
        if pending:
            body.append(join(pending))
    return join(lead), body


def useful_brief(title, summary, body):
    """Prefer a second fact if the default lead closely repeats the headline."""
    key = re.sub(r'[\W_]+', '', title.casefold())
    if not key or not summary:
        return summary
    lead = re.sub(r'[\W_]+', '', summary.casefold())
    if SequenceMatcher(None, key, lead).ratio() < 0.72 and (key not in lead or len(lead) > len(key) + 14):
        return summary
    for block in body:
        for sentence in sentences(block):
            fact = re.sub(r'[\W_]+', '', sentence.casefold())
            if (20 <= len(sentence) <= 145 and TERMINAL.search(sentence)
                    and fact not in lead and key not in fact
                    and SequenceMatcher(None, key, fact).ratio() < 0.55):
                return sentence
    return summary

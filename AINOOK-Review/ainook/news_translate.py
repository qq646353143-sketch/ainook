"""Optional local English-to-Chinese translation with a persistent content cache."""
from argparse import ArgumentParser
from contextlib import closing
from datetime import timedelta
from pathlib import Path
import re
import sys

from .news import TRANSLATION_METHOD
from .news_copy import TERMINAL, evidence_copy, paragraphs
from .quota import utcnow

FAMILIES = (r'Gemini(?: (?:Omni|Robotics))?|Genie|Claude(?: Code)?|Grok|Llama|Qwen|DeepSeek|Mistral|'
            r'GPT|MAI Code|Nano Banana|Gemma|AlphaGenome|AlphaProof Code|Sora|o[134]')
SUFFIXES = (
    r'Neon|Hydrogen|Carbon|Argon|Flash-Lite|Flash|Thinking|Pro|Ultra|Mini|Nano|Opus|Sonnet|Haiku|Astra|Sol|'
    r'Instant|Instruct|Coder|Reasoning|Heavy|Preview|Turbo|Vision|Distill|Max|Lite'
)
MODEL_NAME = re.compile(
    r'(?<![A-Za-z0-9_])(?:' + FAMILIES + r')'
    r'(?:[‐‑– -]?(?:[vVR])?\d+(?:\.\d+)*(?:[A-Za-z]+)?(?:[‐‑– -][\d.]+[A-Za-z]+)?)?'
    r'(?:[‐‑– -](?:' + SUFFIXES + r')(?=[^A-Za-z0-9]|$)){0,3}'
    r'(?:[‐‑– -]\d+(?:\.\d+)*[A-Za-z]*)?(?![A-Za-z0-9_])', re.I,
)
PRODUCTS = re.compile(
    r'(?<![A-Za-z0-9_])(?:Google AI (?:Studio|Ultra|Pro)|Google DeepMind|Project Genie|'
    r'GitHub Copilot(?: (?:CLI|Business|Enterprise|Fusion))?|Claude Code|'
    r'ChatGPT(?: (?:Enterprise|Business|Team|Plus|Pro|Edu|Work|for Sales))?|'
    r'OpenAI|Anthropic|DeepMind|Hugging Face|Codex|Copilot|GitHub|NVIDIA|xAI|Android|'
    r'Antigravity|Cursor|Outlook|Supabase|Calendly|Buildkite|ClickUp|Mixpanel|Webflow|Slack|Figma|Sentry|'
    r'Artificial Analysis Intelligence Index|Agent Arena Index|Vals Index|AR Lenses|'
    r'Simon Willison|Ethan Mollick|Satya Nadella|Jensen Huang|Sam Altman|Elon Musk|Greg Brockman|'
    r'[A-Za-z][A-Za-z0-9]*(?:[-_.][A-Za-z0-9]+)*[-_]\d+(?:\.\d+)*(?:[A-Za-z]+)?(?:[-_][A-Za-z0-9]+)*'
    r')(?![A-Za-z0-9_])', re.I,
)
TERMS = {
    'AI agents': 'AI 智能体',
    'AI agent': 'AI 智能体',
    'agentic coding': '智能体编程',
    'public preview': '公开预览',
    'fine-tuning': '微调',
    'open weights': '开放权重',
    'post-training': '后训练',
    'frontier-level intelligence': '前沿模型能力',
    'end-to-end': '端到端',
    'Pareto frontier': '帕累托前沿',
}
TERMS = {key.casefold(): value for key, value in TERMS.items()}
TECH_TERMS = re.compile(r'\b(?:' + '|'.join(map(re.escape, TERMS)) + r')\b', re.I)
VERSION = re.compile(r'(?<![\w.])(?:[vV])?\d+(?:\.\d+){1,3}(?!\w|\.\d)')
COUNTS = re.compile(r'(?<![\w.])(?:[$€£]\s*)?\d+(?:,\d{3})*(?:\.\d+)?(?:%|[KMB]\b)?(?![\w.]|\s*:)', re.I)
MARKER = re.compile(r'\[NAME_(\d+)\]', re.I)
FALLBACK_MARKER = re.compile(r'https?://\s*ainook\s*\.\s*invalid\s*/\s*n(\d+)(?!\d)', re.I)
LINK = re.compile(r'(?:https?://|www\.|[\w.-]+\.(?:net|com|org|ai)/)\S+', re.I)
RETRY_DELAYS = (timedelta(hours=6), timedelta(hours=24))


def protected_copy(value, models):
    standalone = {part for name in models for part in re.findall(r'\b(?:' + SUFFIXES + r')\b', name)}
    aliases = re.compile(r'\b(?:' + '|'.join(sorted(standalone, key=lambda part: (-len(part), part))) + r')\b') if standalone else None
    spans = [match for pattern in (PRODUCTS, MODEL_NAME, TECH_TERMS, VERSION, COUNTS, aliases)
             if pattern is not None for match in pattern.finditer(value)]
    originals, chunks = [], []
    cursor = 0
    for match in sorted(spans, key=lambda part: (part.start(), -(part.end() - part.start()))):
        if match.start() < cursor:
            continue
        token = match.group()
        chunks.extend((value[cursor:match.start()], f'[NAME_{len(originals)}]'))
        originals.append(TERMS.get(token.casefold(), token))
        cursor = match.end()
    chunks.append(value[cursor:])
    return ''.join(chunks), originals


def restore_copy(translated, originals, marker=MARKER):
    indexes = [int(match) for match in marker.findall(translated)]
    if sorted(indexes) != list(range(len(originals))):
        raise ValueError('译文遗漏或重复专名、数字或术语')
    translated = marker.sub(lambda match: originals[int(match[1])], translated)
    if any(part in translated for part in ('⁇', 'ainook.', 'NAME_')) or not re.search(r'[\u3400-\u9fff]', translated):
        raise ValueError('翻译无法使用')
    translated = translated.replace('▁', ' ').strip()
    translated = re.sub(r'\s+([，。？！：、])', r'\1', translated)
    translated = re.sub(r'\s*([,:;])\s*(?=[\u3400-\u9fff])', lambda match: {',': '，', ':': '：', ';': '；'}[match[1]], translated)
    translated = re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])', '', translated)
    translated = re.sub(r'(?<=[A-Za-z0-9])(?=[\u3400-\u9fff])|(?<=[\u3400-\u9fff])(?=[A-Za-z0-9])', ' ', translated)
    return translated


def translated_sentence(translator, value, prepared):
    original, names = prepared
    try:
        result = restore_copy(value, names)
    except ValueError:
        fallback = MARKER.sub(lambda match: f'https://ainook.invalid/n{match[1]}', original)
        result = restore_copy(translator.translate([fallback])[0], names, FALLBACK_MARKER)
    if len(original) >= 65 and len(result) < len(original) * 0.13:
        raise ValueError('译文长度异常')
    return result


def release_headline(title, evidence):
    value = re.sub(r'(?i)^introducing\s+|\s+is now (?:generally )?available[.!]?$', '', title)
    if value != title and MODEL_NAME.fullmatch(value):
        return f'{value} 发布' if title.lower().startswith('introducing ') else f'{value} 现已上线'
    model, separator, platform = title.rpartition(' in ')
    if separator and MODEL_NAME.fullmatch(model) and PRODUCTS.fullmatch(platform):
        availability = re.escape(model) + r' is (?:now )?(?:generally )?available in ' + re.escape(platform)
        if re.search(availability, evidence, re.I):
            return f'{model} 登陆 {platform}'
    return ''


def finish_sentence(sentence):
    sentence = sentence.rstrip('，,、;；:： ')
    if not TERMINAL.search(sentence):
        return sentence + '。'
    if sentence[-1] in '.!?':
        return sentence[:-1] + {'.': '。', '!': '！', '?': '？'}[sentence[-1]]
    return sentence


def translate_article(translator, title, evidence):
    title = LINK.sub('', title).strip().rstrip('…').strip()
    evidence = evidence_copy(LINK.sub('', evidence), 1450)
    blocks = list(paragraphs(evidence))
    fields = [title, *(part for block in blocks for part in block)]
    if not title:
        raise ValueError('缺少可译标题')
    if not blocks:
        raise ValueError('缺少完整的正文资料')
    models = MODEL_NAME.findall(title + ' ' + evidence)
    prepared = [protected_copy(field, models) for field in fields]
    headline = release_headline(title, evidence)
    start = int(bool(headline))
    work = prepared[start:]
    values = translator.translate([value for value, _ in work]) if work else []
    if len(values) != len(work):
        raise ValueError('翻译没有返回完整字段')
    result = [headline] if headline else []
    result.extend(translated_sentence(translator, value, field) for value, field in zip(values, work))
    headline = result[0].rstrip('。.,，:：;； ')
    if not headline.endswith(('？', '?')) and re.search(r'\bwhy\b|\bhow\b', title, re.I) and title.endswith('?'):
        headline += '？'
    body = []
    cursor = 1
    for block in blocks:
        body.append(''.join(finish_sentence(sentence) for sentence in result[cursor:cursor + len(block)]))
        cursor += len(block)
    return headline, '\n\n'.join(body)


def translate_reading(translator, title, evidence):
    """Translate a few verified details independently, so one bad sentence can be skipped."""
    material = LINK.sub('', evidence)
    models = MODEL_NAME.findall(title + ' ' + material)
    prepared = [protected_copy(line, models) for line in material.splitlines() if line.strip()]
    values = translator.translate([value for value, _ in prepared])
    if len(values) != len(prepared):
        raise ValueError('正文译文段落不全')
    result = []
    for value, field in zip(values, prepared):
        try:
            result.append(finish_sentence(translated_sentence(translator, value, field)))
        except (ValueError, RuntimeError, IndexError):
            continue
    if len(result) < 2:
        raise ValueError('可用正文资料不足')
    return '\n\n'.join(result)


class LocalTranslator:
    def __init__(self, root):
        root = Path(root)
        libraries = root / 'runtime'
        package = root / 'translate-en_zh-1_9'
        if not libraries.is_dir() or not (package / 'sentencepiece.model').is_file():
            raise FileNotFoundError('未准备本地英中翻译组件')
        sys.path.insert(0, str(libraries))
        try:
            import ctranslate2
            import sentencepiece
        finally:
            sys.path.remove(str(libraries))
        self.processor = sentencepiece.SentencePieceProcessor(model_file=str(package / 'sentencepiece.model'))
        self.translator = ctranslate2.Translator(str(package / 'model'), device='cpu', compute_type='int8',
                                              inter_threads=1, intra_threads=2)

    def translate(self, values):
        tokens = [self.processor.encode(value, out_type=str) for value in values]
        if any(len(value) > 320 for value in tokens):
            raise ValueError('输入超出本地翻译长度')
        results = self.translator.translate_batch(tokens, beam_size=2, max_input_length=320, max_decoding_length=320)
        if any(len(result.hypotheses[0]) >= 320 for result in results):
            raise ValueError('本地译文可能被截断')
        return [self.processor.decode(result.hypotheses[0]).strip() for result in results]


def translate_pending(news, *, factory=LocalTranslator, limit=None):
    with closing(news.connect()) as db:
        pending = db.execute('''
            SELECT a.content_key,a.title,a.summary,COALESCE(r.attempts,0) AS attempts FROM articles a
            JOIN article_signals s ON s.article_id=a.id
            LEFT JOIN translations t ON t.content_key=a.content_key
            LEFT JOIN translation_retry r ON r.content_key=a.content_key
            LEFT JOIN event_representatives e ON e.article_id=a.id
            WHERE a.language='en' AND a.archived=0 AND s.priority>0 AND length(trim(a.summary))>0
              AND (a.kind='voice' OR s.unverified=0)
              AND (t.content_key IS NULL OR t.method IN ('offline','failed'))
              AND (r.content_key IS NULL OR (r.next_at IS NOT NULL AND r.next_at <= ?))
            GROUP BY a.content_key
            ORDER BY max(CASE WHEN e.winner_id IS NULL OR e.winner_id=a.id THEN 1 ELSE 0 END) DESC,
                     max(a.published) DESC, max(s.priority) DESC LIMIT ?
        ''', (utcnow().isoformat(), limit or news.config['translate_per_cycle'])).fetchall()
        reading = db.execute('''
            SELECT m.article_id,m.evidence,m.attempts,a.title FROM article_reading m
            JOIN articles a ON a.id=m.article_id
            LEFT JOIN translations t ON t.content_key=a.content_key
            WHERE m.body IS NULL AND m.state='ready' AND a.language='en' AND coalesce(t.method,'')<>'reviewed'
            AND (m.attempts=0 OR (m.next_at IS NOT NULL AND m.next_at<=?))
            ORDER BY a.published DESC LIMIT ?
        ''', (utcnow().isoformat(), limit or 8)).fetchall()
    if not pending and not reading:
        return {'translated': 0, 'failed': 0}
    try:
        translator = factory(news.directory / 'translator')
    except (OSError, ImportError, RuntimeError, ValueError) as error:
        return {'translated': 0, 'state': 'offline_unavailable', 'detail': type(error).__name__}

    translated = failed = 0
    for article in pending:
        method = TRANSLATION_METHOD
        try:
            title, summary = translate_article(translator, article['title'], article['summary'])
        except (OSError, RuntimeError, ValueError, IndexError):
            title, summary, method = '', '', 'failed'
        with closing(news.connect()) as db, db:
            key = article['content_key']
            now = utcnow()
            inserted = db.execute('''
                INSERT INTO translations VALUES (?,?,?,?,?) ON CONFLICT(content_key) DO UPDATE SET
                  title=excluded.title, summary=excluded.summary, method=excluded.method, at=excluded.at
                WHERE translations.method IN ('offline','failed')
            ''', (key, title, summary, method, now.isoformat())).rowcount
            if method == TRANSLATION_METHOD:
                db.execute('DELETE FROM translation_retry WHERE content_key=?', (key,))
                translated += inserted
            elif inserted:
                attempts = article['attempts'] + 1
                next_at = (now + RETRY_DELAYS[attempts - 1]).isoformat() if attempts <= len(RETRY_DELAYS) else None
                db.execute('INSERT OR REPLACE INTO translation_retry VALUES (?,?,?)', (key, attempts, next_at))
                failed += 1
    reading_translated = 0
    for article in reading:
        try:
            copy = translate_reading(translator, article['title'], article['evidence'])
        except (OSError, RuntimeError, ValueError, IndexError):
            copy = None
        attempts = article['attempts'] + int(copy is None)
        next_at = (utcnow() + RETRY_DELAYS[attempts - 1]).isoformat() if 0 < attempts <= len(RETRY_DELAYS) and not copy else None
        with closing(news.connect()) as db, db:
            updated = db.execute('''
                UPDATE article_reading SET body=?, attempts=?, next_at=?
                WHERE article_id=? AND body IS NULL AND attempts=?
            ''', (copy, attempts, next_at, article['article_id'], article['attempts'])).rowcount
            if copy:
                reading_translated += updated
    return {'translated': translated, 'failed': failed, 'reading_translated': reading_translated}


if __name__ == '__main__':
    from .news import News
    parser = ArgumentParser(description='为待处理资讯运行一批本地英中翻译')
    parser.add_argument('--data-dir', type=Path, default=Path('outputs/ainook'))
    parser.add_argument('--requeue-paused', action='store_true', help='本地翻译组件修复后，重新排队待处理稿件')
    args = parser.parse_args()
    news = News(args.data_dir)
    if args.requeue_paused:
        with closing(news.connect()) as db, db:
            db.execute('DELETE FROM translation_retry WHERE next_at IS NULL')
    print(translate_pending(news))

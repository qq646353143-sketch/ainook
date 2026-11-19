"""Time, URL, classification, verification and ranking rules; no model knowledge."""
from __future__ import annotations
import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

UTC = timezone.utc
JST = timezone(timedelta(hours=9), 'JST')
CATEGORIES = {'ai':'AI 前沿','politics':'国际政治','economy':'经济影响'}
DEFAULT_WEIGHTS = {'ai':50, 'politics':35, 'economy':15}

def now_iso():
    return datetime.now(UTC).isoformat()

def digest(value):
    return hashlib.sha256(value.encode('utf-8') if isinstance(value,str) else value).hexdigest()

def canonical_url(value):
    try:
        u=urlsplit(value.strip())
        if u.scheme not in ('http','https') or not u.hostname or u.username or u.password:
            return ''
        if any(ord(c)<32 for c in value) or '\\' in value:
            return ''
        query=[(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True)
               if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid','ref_src')]
        return urlunsplit((u.scheme.lower(),u.netloc.lower(),u.path or '/',urlencode(query),u.fragment))
    except (ValueError,AttributeError):
        return ''

def normalize_time(raw, now=None):
    """Never fill in a missing timezone or replace publication with fetch time."""
    raw=(raw or '').strip()
    result={'raw':raw,'utc':None,'jst':None,'original_timezone':None,'precision':'unknown','issue':'缺少发布时间'}
    if not raw:
        return result
    calendar=None
    if re.fullmatch(r'\d{4}[./-]\d{1,2}[./-]\d{1,2}',raw):calendar=re.sub(r'[./]','-',raw)
    else:
        for fmt in ('%B %d, %Y','%b %d, %Y','%b. %d, %Y','%B %d %Y','%Y年%m月%d日'):
            try:calendar=datetime.strptime(raw,fmt).strftime('%Y-%m-%d');break
            except ValueError:pass
    if calendar:
        try:
            day=datetime.strptime(calendar,'%Y-%m-%d').strftime('%Y-%m-%d')
        except ValueError:
            result['issue']='无效日期'; return result
        return {**result,'precision':'day','date':day,'issue':'仅日期，原始时区未知；不计入精确24/48小时窗口'}
    try:
        try: d=datetime.fromisoformat(raw.replace('Z','+00:00'))
        except ValueError: d=parsedate_to_datetime(raw)
        if d.tzinfo is None:
            result['issue']='原始时间未注明时区'; return result
        instant=d.astimezone(UTC)
        if instant>(now or datetime.now(UTC))+timedelta(minutes=5):
            result['issue']='发布时间位于未来，需核对来源或系统时钟'; return result
        zone=re.search(r'(Z|[+-]\d{2}:?\d{2}|GMT|UTC|EST|EDT|PST|PDT)\s*$',raw)
        return {**result,'utc':instant.isoformat(),'jst':instant.astimezone(JST).isoformat(),
                'original_timezone':zone.group(1) if zone else d.tzname(),'precision':'second','issue':None}
    except (TypeError,ValueError,OverflowError):
        result['issue']='无法解析原始时间'; return result

RIGHTS=r'quota|reset|allowance|usage.limit|rate.limit|free.tier|pricing|price.change|credits?|trial|retir|deprecat|地区限制|额度|限额|重置|权益|下线|试用|免费|订阅'
HIGH_RISK=r'resign|oust|impeach|removed.from.office|ceasefire|passed.into.law|takes.effect|辞职|罢免|下台|停火|已生效|正式生效|传闻|rumou?r|unconfirmed|alleged'
ENTITY_PATTERNS={
 'OpenAI':r'openai|chatgpt|codex|gpt[- ]\d', 'Anthropic':r'anthropic|claude',
 'Google':r'google|gemini|deepmind|ai.studio', 'NVIDIA':r'nvidia|英伟达',
 'Microsoft':r'microsoft|copilot|微软','DeepSeek':r'deepseek|深度求索',
 'Qwen':r'qwen|通义','Meta':r'\bmeta\b|llama','xAI':r'\bxai\b|\bgrok\b',
 '美国':r'(?-i:\bU\.?S\.?\b)|united.states|white.house|trump|美国|白宫|特朗普',
 '中国':r'china|chinese|中国|中美','俄乌':r'ukrain|russia|乌克兰|俄罗斯',
 '中东':r'iran|israel|gaza|middle.east|伊朗|以色列|加沙',
 '美联储':r'federal.reserve|\bfed\b|fomc|美联储',
}

def classify(item, source):
    text=f"{item.get('title','')} {item.get('summary','')[:4000]}"
    title=item.get('title','')
    entities=[name for name,pat in ENTITY_PATTERNS.items() if re.search(pat,text,re.I)]
    owner=source.get('owner','')
    if owner and owner not in entities and source['tier'] in (1,3) and source.get('role')!='research': entities.insert(0,owner)
    category=source['category']
    if category=='politics' and re.search(r'openai|anthropic|gemini|deepseek|artificial intelligence|人工智能',title,re.I): category='ai'
    subcategory='产业动态' if category=='ai' else '政策与时事' if category=='politics' else '宏观与经营'
    if category=='ai':
        if source.get('role')=='status': subcategory='服务状态'
        elif source.get('role')=='research': subcategory='技术研究'
        elif re.search(RIGHTS,title,re.I) or re.search(r'quota|allowance|usage.limit|free.tier|额度|限额|权益|额度重置',item.get('summary','')[:1200],re.I): subcategory='用户权益'
        elif re.search(r'paper|research|arxiv|论文|研究',title,re.I): subcategory='技术研究'
        elif re.search(r'model|模型|gpt[- ]\d|gemini|claude|deepseek',title,re.I): subcategory='模型更新'
        elif re.search(r'agent|robot|机器人|智能体',title,re.I): subcategory='Agent 与机器人'
        elif re.search(r'update|release|launch|introduc|feature|更新|发布|功能',title,re.I): subcategory='产品更新'
    if source.get('person'): subcategory='人物言论'
    return category,subcategory,list(dict.fromkeys(entities))[:10]

def verification(item,source):
    timed=bool(item['time']['utc'])
    original=source['tier'] in (1,3)
    status='个人声明' if source['tier']==3 else '媒体报道' if source['tier']==2 else '未经证实' if source['tier']==4 else '正式发布'
    title=item['title']
    if source.get('role')!='status':
        if re.search(r'upcoming|will.(?:deprecat|retire|remove)|拟议|征求意见|propos\w*',title,re.I):status='预告' if source['tier']==1 else status
        elif re.search(r'preview|beta|public.test|公开测试|公测',title,re.I): status='公开测试' if source['tier']==1 else status
        elif re.search(r'coming.soon|will.launch|预告|即将',title,re.I):status='预告' if source['tier']==1 else status
    reasons=[]
    if source['id']=='congress' and 'Preservation Metadata' in item.get('summary',''):
        reasons.append('当前仅取得法案文件索引与元数据，未核对全文和完整立法程序状态')
    if not timed: reasons.append(item['time']['issue'])
    if source['tier']==4: reasons.append('社区线索，缺少可核对的一手证据')
    if source.get('role')=='platform':reasons.append('平台托管的作者文章；作者与机构身份尚未逐项核对，平台不能替代原始机构证据')
    if source['tier']==2: reasons.append('媒体报道，尚未完成独立来源交叉核验')
    if re.search(HIGH_RISK,title,re.I): reasons.append('高风险或传闻表述，需逐项核验正式信息')
    if item.get('parse_warning'):reasons.append(item['parse_warning'])
    scope=('可确认原始公告/文件已发表；其中的性能、指控、因果和政策生效需分别核验' if source['tier']==1 else
           '可确认本人博客发表了此文；观点与预测不自动成为事实' if source['tier']==3 else
           '仅确认该来源作出报道，未将报道内容自动判定为事实')
    return {'state':status,'verification':'待核实' if reasons else '原始来源已核对',
            'reasons':reasons,'scope':scope,'independent_fact_check':False,'original_document':original}

def score(item,source,category,subcategory,now=None):
    title=item['title']; now=now or datetime.now(UTC)
    matched=re.findall(r'\b(?:war|sanctions?|tariffs?|export.control|acqui\w*|models?|release|rates?|inflation)\b|战争|制裁|关税|出口管制|利率|通胀|模型',title,re.I)
    impact=min(5,2+bool(matched)+bool(re.search(r'\b(?:war|sanctions?|tariffs?)\b|利率|战争|制裁|关税',title,re.I))*2)
    if source.get('role')=='status': impact=1
    age=(now-datetime.fromisoformat(item['time']['utc'])).total_seconds()/3600 if item['time']['utc'] else None
    novelty=4 if age is not None and 0<=age<=48 else 1 if age is not None else 0
    reliability={1:5,2:4,3:3,4:1}[source['tier']]
    rights=5 if subcategory=='用户权益' else 1
    consequence=4 if matched else 1
    if source.get('role')=='research':
        # A listing on arXiv is not evidence of a major breakthrough.
        impact=1;novelty=min(novelty,2);consequence=1;rights=0
    elif source.get('role')=='status':
        impact=0;novelty=min(novelty,2);consequence=0;rights=0
    elif source['id']=='congress':
        impact=1;novelty=min(novelty,2);consequence=1
    elif source['tier']==1 and re.search(r'introduc|launch|release|正式发布|推出|公告|调整',title,re.I):
        impact=max(impact,4)
    content=title+' '+item.get('summary','')[:1500]
    intrinsic=source['id'] in ('openai-news','openai-codex','openai-help','openai-status','anthropic-news','claude-notes','claude-status','google-ai','deepmind','deepseek','arxiv-ai')
    if category=='ai': relevant=intrinsic or bool(re.search(r'\b(?:AI|LLM|agent|robot|robots|models?|Gemini|Claude|Copilot|GPT|training|inference|GPU)\b|人工智能|模型|智能体|机器人|算力|芯片',content,re.I))
    elif category=='politics':relevant=source.get('role')=='government' or source['id']=='china-mfa' or bool(re.search(r'\b(?:president|Trump|Congress|government|minister|election|policy|war|sanctions?|tariffs?|Russia|Ukraine|China|Chinese|Israel|Iran|military|diploma\w*|aviation|FAA|air.traffic|national.emergency)\b|中国|美国|总统|外交|战争|制裁|关税|政策',content,re.I))
    else:relevant=True
    if re.search(r'\bARTICLES\b',item.get('summary','')[:500]) and 'Most recent' in item.get('summary','')[:500]:relevant=False
    if not relevant:impact=0;novelty=0;consequence=0;rights=0
    components={'实际重要性':impact*5,'时效与新进展':novelty*4,'来源可追溯性':reliability*5,'技术社会经济影响':consequence*3,'普通用户权益':rights*3}
    return {'base':sum(components.values()),'components':components,'rule_version':3,'relevant':relevant,
            'explanation':['来源级别不等于所有主张为真','不使用报道数量或热搜热度',
             '标题触发词：'+('、'.join(dict.fromkeys(matched)) or '无'),
             '权益更新独立加权' if rights==5 else '未检测到明确用户权益变化',
             '在关注范围内' if relevant else '保留原始库，但不进入情报头条：范围外或索引页面',
             '论文收录不等于重大突破，重要性保持保守' if source.get('role')=='research' else '按公告类型和明确影响词启发式排序']}

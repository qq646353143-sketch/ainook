"""Public RSS/HTML collection. Honest UA, verified TLS, no login/anti-bot bypass."""
from __future__ import annotations
import gzip
import html
import json
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET
from easel.trends.rss import parse_feed, ATOM, DC, RSS1
from .model import digest, canonical_url, normalize_time, now_iso

MAX_RESPONSE=8*1024*1024

class CollectionError(Exception):
    def __init__(self,code,message,status=None):
        super().__init__(message); self.code=code; self.status=status

class Document(HTMLParser):
    """Text/heading/link metadata only. Script contents never become evidence."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[]; self.length=0; self.hidden=0; self.links=[]; self.active_link=None
        self.headings=[]; self.active_heading=None; self.active_time=None; self.meta={}; self.page_title=''; self.in_title=False
    def append(self,s): self.parts.append(s); self.length+=len(s)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style','noscript','nav','footer'):self.hidden+=1
        if self.hidden:return
        if tag=='meta':self.meta[a.get('property') or a.get('name','')]=a.get('content','')
        if tag=='title':self.in_title=True
        if tag=='time':self.active_time={'level':2,'start':self.length,'text':'','anchor':a.get('id',''),'datetime':a.get('datetime','')}
        if tag in ('p','div','li','article','section','br') or re.fullmatch('h[1-6]',tag):self.append('\n')
        if re.fullmatch('h[1-6]',tag):self.active_heading={'level':int(tag[1]),'start':self.length,'text':'','anchor':a.get('id','')}
        if tag=='a':self.active_link={'href':a.get('href',''),'text':''}
    def handle_endtag(self,tag):
        if tag in ('script','style','noscript','nav','footer'):
            self.hidden=max(0,self.hidden-1);return
        if self.hidden:return
        if tag=='title':self.in_title=False
        if tag=='time' and self.active_time:
            self.active_time['end']=self.length;self.headings.append(self.active_time);self.active_time=None
        if tag=='a' and self.active_link:self.links.append(self.active_link);self.active_link=None
        if re.fullmatch('h[1-6]',tag) and self.active_heading:
            self.active_heading['end']=self.length
            self.headings.append(self.active_heading);self.active_heading=None
        if tag in ('p','div','li','article','section') or re.fullmatch('h[1-6]',tag):self.append('\n')
    def handle_data(self,data):
        if self.hidden:return
        self.append(data)
        if self.active_link:self.active_link['text']+=data
        if self.active_heading:self.active_heading['text']+=data
        if self.active_time:self.active_time['text']+=data
        if self.in_title:self.page_title+=data
    @property
    def text(self):return ''.join(self.parts)

def clean(value):
    doc=Document()
    try:doc.feed(value or '')
    except (ValueError,RecursionError):return ''
    text=re.sub(r'[ \t\r\f\v]+',' ',doc.text)
    return re.sub(r'\n(?:[ \t]*\n){2,}','\n\n',text).strip()

class PrimaryBody(HTMLParser):
    """Common publisher body containers, without site navigation or audio controls."""
    VOID={'br','hr','img','meta','input','link','source','wbr','area','base','embed','param','track','col'}
    def __init__(self, extra_markers=()):
        super().__init__(convert_charrefs=False);self.depth=0;self.active=0;self.chunks=[]
        default = 'rich-text|article-body|articleBody|entry-content|post-content|field--name-body|article__body|article'
        markers = '|'.join([default, *map(re.escape, extra_markers)])
        self.marker = re.compile(r'(?:^|\s)(?:' + markers + r')(?:\s|$)')
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);marker=' '.join((a.get('class',''),a.get('id',''),a.get('itemprop','')))
        if not self.active and self.marker.search(marker):self.active=self.depth+1
        if self.active:self.chunks.append(self.get_starttag_text())
        if tag not in self.VOID:self.depth+=1
    def handle_endtag(self,tag):
        if tag not in self.VOID:self.depth=max(0,self.depth-1)
        if self.active:
            self.chunks.append('</'+tag+'>')
            if self.depth<self.active:self.active=0
    def handle_data(self,data):
        if self.active:self.chunks.append(data)
    def handle_entityref(self,name):
        if self.active:self.chunks.append('&'+name+';')
    def handle_charref(self,name):
        if self.active:self.chunks.append('&#'+name+';')

def fetch(url,timeout=18):
    if not canonical_url(url):raise CollectionError('invalid_url','来源 URL 不合法')
    for attempt in range(2):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'Easel-Intelligence/1.0 (personal evidence reader)',
                'Accept':'application/rss+xml,application/atom+xml,text/html,application/xml;q=0.9,*/*;q=0.5'})
            started=time.monotonic()
            with urllib.request.urlopen(request,timeout=timeout) as response:
                if urlsplit(response.url).scheme!='https' and urlsplit(url).scheme=='https':
                    raise CollectionError('unsafe_redirect','拒绝 HTTPS 降级')
                chunks=[];size=0
                while True:
                    if time.monotonic()-started>timeout:raise CollectionError('timeout','采集超时')
                    block=response.read1(min(65536,MAX_RESPONSE+1-size))
                    if not block:break
                    chunks.append(block);size+=len(block)
                    if size>MAX_RESPONSE:raise CollectionError('response_too_large','响应超过 8 MiB')
                payload=b''.join(chunks)
                if payload[:2]==b'\x1f\x8b':
                    import io
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as compressed:payload=compressed.read(MAX_RESPONSE+1)
                    if len(payload)>MAX_RESPONSE:raise CollectionError('response_too_large','解压后的响应超过8MiB')
                return {'body':payload,'url':response.url,'status':response.status,
                        'content_type':response.headers.get('Content-Type',''),'fetched_at':now_iso()}
        except urllib.error.HTTPError as e:
            if attempt==0 and e.code in (408,429,500,502,503,504):time.sleep(.5);continue
            raise CollectionError('http_'+str(e.code),'HTTP '+str(e.code)+'；未尝试绕过访问限制',e.code) from None
        except (urllib.error.URLError,TimeoutError,OSError) as e:
            if attempt==0:time.sleep(.3);continue
            raise CollectionError('network_error','连接或证书校验失败：'+type(e).__name__) from None

def save_snapshot(root:Path,source_id,response):
    body=response['body'];sha=digest(body)
    rel=Path('raw')/source_id/(sha+'.gz');path=root/rel
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        with gzip.open(path,'wb') as f:f.write(body)
    return {'id':sha,'path':rel.as_posix(),'fetched_at':response['fetched_at'],
            'url':response['url'],'status':response['status'],'content_type':response['content_type'],'bytes':len(body)}

def rich_feed(raw,url,*,post_titles=False):
    # Reuse Easel's DTD/entity/size/depth checks and the existing URL/date protocol.
    normalized=parse_feed(raw,url)['items']
    root=ET.fromstring(raw)
    generated=set()
    if post_titles:
        # Some native social RSS feeds have a body and permalink but no headline.
        # Validate the original XML first, then use an exact excerpt as its label.
        for entry in root.iter():
            if entry.tag.split('}')[-1] not in ('item','entry'):continue
            if any(c.tag.split('}')[-1]=='title' and ''.join(c.itertext()).strip() for c in entry):continue
            content=next((''.join(c.itertext()).strip() for c in entry if c.tag.split('}')[-1] in ('description','content','summary')),'')
            if content:
                ET.SubElement(entry,'title').text=clean(content)[:160];generated.add(id(entry))
        normalized=parse_feed(ET.tostring(root,encoding='utf-8'),url)['items']
    entries=[x for x in root.iter() if x.tag.split('}')[-1] in ('item','entry')]
    entries=[x for x in entries if any(c.tag.split('}')[-1]=='title' and ''.join(c.itertext()).strip() for c in x)]
    by_id={};by_title={};by_url={}
    base=urljoin(url,root.get('{http://www.w3.org/XML/1998/namespace}base',''))
    channel=root.find('channel')
    if channel is not None:base=urljoin(base,channel.get('{http://www.w3.org/XML/1998/namespace}base',''))
    for entry in entries:
        eb=urljoin(base,entry.get('{http://www.w3.org/XML/1998/namespace}base',''))
        for child in entry:
            name=child.tag.split('}')[-1];text=html.unescape(''.join(child.itertext()).strip())
            if name in ('id','guid') and text:by_id.setdefault(text,entry)
            if name=='title':by_title.setdefault(text,entry)
            if name=='link' and child.get('rel','alternate')=='alternate':
                target=child.get('href') or text
                if target:by_url.setdefault(urljoin(urljoin(eb,child.get('{http://www.w3.org/XML/1998/namespace}base','')),target),entry)
        about=entry.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about')
        if about:by_id.setdefault(about,entry)
    output=[]
    for item in normalized:
        entry=by_id.get(item['id'])
        if entry is None:entry=by_url.get(item['url'])
        if entry is None:entry=by_title.get(item['title'])
        if entry is None:continue
        def val(names):
            for name in names:
                for e in entry:
                    if e.tag.split('}')[-1]==name:
                        value=''.join(e.itertext()).strip()
                        if value:return value
            return ''
        date=val(['pubDate','published','date'])
        output.append({'native_id':item['id'],'title':clean(item['title']),'url':item['url'],
            'raw_time':date,'raw_updated':val(['updated']),
            'summary':clean(val(['encoded','content','description','summary']))[:30000],
            'author':clean(val(['creator','author']))[:300], 'time':normalize_time(date),
            **({'title_origin':'post_excerpt'} if id(entry) in generated else {})})
    return output

MONTHS='January February March April May June July August September October November December'.split()
def heading_date(text):
    m=re.search(r'\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b',text)
    if m:return f'{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}'
    for i,month in enumerate(MONTHS,1):
        m=re.search(r'\b(?:'+month+'|'+month[:3]+r'\.?)\s+(\d{1,2}),?\s+(20\d{2})\b',text,re.I)
        if m:return f'{m[2]}-{i:02d}-{int(m[1]):02d}'
    return None

def changelog(raw,url):
    doc=Document();doc.feed(raw.decode('utf-8','replace'))
    dated=[(h,heading_date(h['text'])) for h in doc.headings if heading_date(h['text'])]
    records=[]
    for i,(h,date) in enumerate(dated):
        end=dated[i+1][0]['start'] if i+1<len(dated) else len(doc.text)
        children=[x for x in doc.headings if h['end']<x['start']<end and x['level']>h['level']]
        sections=children or [h]
        for j,sub in enumerate(sections):
            stop=sections[j+1]['start'] if j+1<len(sections) else end
            body=doc.text[sub['end']:stop].strip()
            title=sub['text'].strip()
            if len(body)<20:continue
            anchor=sub['anchor'] or h['anchor']
            link=url.split('#')[0]+('#'+anchor if anchor else '')
            parents=[x['text'].strip() for x in children if x['level']<sub['level'] and x['start']<sub['start']]
            if parents:title=parents[-1]+' · '+title
            native=f'{date}|{title}'
            raw_date=h['text'].strip().removeprefix('Date:').replace('\u200b','').strip()
            if not normalize_time(raw_date)['precision']=='day':raw_date=date
            records.append({'native_id':native,'section_key':native,'title':title,'url':link,
                'raw_time':h.get('datetime') or raw_date,'raw_updated':'','summary':body[:30000],'author':'',
                'time':normalize_time(h.get('datetime') or raw_date),'parse_warning':None})
    if not records:raise CollectionError('no_dated_entries','页面未提取到带日期的更新；不返回成功空列表')
    return records[:500]

def article_page(raw,url):
    doc=Document();doc.feed(raw.decode('utf-8','replace'))
    # Prefer main/article to global navigation, but never substitute a dateModified for datePublished.
    match=re.search(r'<(?:main|article)\b[^>]*>([\s\S]*?)</(?:main|article)>',raw.decode('utf-8','replace'),re.I)
    content=clean(match[1]) if match else doc.text.strip()
    primary=PrimaryBody();primary.feed(raw.decode('utf-8','replace'))
    selected=clean(''.join(primary.chunks))
    if len(selected)>200:content=selected
    date=doc.meta.get('article:published_time') or doc.meta.get('datePublished') or doc.meta.get('pubdate') or ''
    if not date:
        ld=re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',raw.decode('utf-8','replace'),re.I)
        def find_date(obj):
            if isinstance(obj,dict):
                if isinstance(obj.get('datePublished'),str):return obj['datePublished']
                for v in obj.values():
                    found=find_date(v)
                    if found:return found
            if isinstance(obj,list):
                for v in obj:
                    found=find_date(v)
                    if found:return found
            return ''
        for code in ld:
            try:date=find_date(json.loads(code))
            except (ValueError,RecursionError):continue
            if date:break
    if not date:
        # Only standalone date lines, not a future event date embedded in a headline.
        for line in doc.text[:6000].splitlines():
            candidate=line.strip().replace('\u200b','')
            if candidate and normalize_time(candidate)['precision']=='day':date=candidate;break
    return {'title':doc.meta.get('og:title') or doc.page_title,'raw_time':date,
            'summary':content[:45000],'author':doc.meta.get('author',''),'time':normalize_time(date)}

def news_index(raw,url,source,root):
    doc=Document();doc.feed(raw.decode('utf-8','replace'))
    links=[];seen=set()
    for a in doc.links:
        link=canonical_url(urljoin(url,a['href']))
        if not link or urlsplit(link).hostname!=urlsplit(url).hostname:continue
        if source.get('link_pattern','') not in urlsplit(link).path or link.rstrip('/')==url.rstrip('/'):continue
        if len(a['text'].strip())<12 or link in seen:continue
        # Index navigation/pagination is not an article.
        if re.search(r'/index(?:_|\.)|/page/|[?&]page=',link):continue
        links.append((link,a['text'].strip()));seen.add(link)
    if not links:raise CollectionError('no_article_links','未识别到新闻条目；需要适配页面结构')
    records=[];errors=0
    for link,label in links[:16]:
        try:
            response=fetch(link,timeout=12)
            page=article_page(response['body'],response['url'])
            snap=save_snapshot(root,source['id'],response)
            if re.search(r'\bARTICLES\b',page['summary'][:500]) and 'Most recent' in page['summary'][:500]:
                errors+=1;continue
            records.append({**page,'native_id':link,'url':response['url'],'raw_updated':'','article_snapshot':snap,
                            'link_checked_at':response['fetched_at'],'parse_warning':None if page['raw_time'] else '正文缺少可核验发布时间'})
        except Exception:errors+=1
    if not records:raise CollectionError('articles_unavailable','索引可读，但文章正文无法合规读取')
    return records,{'article_fetch_errors':errors,'index_links':len(links),'article_limit':16,
                    'coverage_note':'新闻索引每轮最多读取前16篇正文；其余保留为覆盖限制' if len(links)>16 else ''}

def collect(source,root):
    response=fetch(source['url'],timeout=45 if source['kind']=='changelog' else 18);snapshot=save_snapshot(root,source['id'],response)
    warnings={}
    try:
        if source['kind']=='rss':items=rich_feed(response['body'],response['url'],post_titles=bool(source.get('social_feed') and source.get('person') and source.get('tier')==3))
        elif source['kind']=='changelog':items=changelog(response['body'],response['url'])
        elif source['kind']=='news_index':items,warnings=news_index(response['body'],response['url'],source,root)
        else:raise CollectionError('manual_source','人工来源没有自动采集器')
    except CollectionError as error:
        error.snapshot=snapshot;raise
    except Exception as error:
        wrapped=CollectionError('parse_failed','解析失败：'+type(error).__name__);wrapped.snapshot=snapshot
        raise wrapped from None
    return items,snapshot,warnings

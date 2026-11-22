import routes from './generated/routes.json';

const feed = 'https://raw.githubusercontent.com/qq646353143-sketch/ainook/main/AINOOK-Review/published/reset-watch-hourly.json';
const platforms = ['codex', 'claude', 'grok'];
const forms = {banked_reset: ['重置卡', '发放重置卡'], general_reset: ['临时重置', '通用重置']};
const sources = new Set(['x.com', 'twitter.com', 'help.openai.com', 'openai.com',
  'support.claude.com', 'claude.com', 'anthropic.com', 'docs.x.ai', 'x.ai']);
const HOUR = 3600000;
const DAY = 24 * HOUR;
const DAYS = ['all', '7', '30', '90'];
const fileHeaders = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'no-referrer',
  'X-Robots-Tag': 'noindex',
};
const beijing = stamp => new Date(stamp + 8 * HOUR).toISOString();
const escapeHTML = value => String(value).replace(/[&<>"']/g,
  character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
const json = (data, status = 200, headers = {}) => Response.json(data, {
  status, headers: {...fileHeaders, 'Cache-Control': 'no-store', ...headers},
});

function asset(env, url, filename) {
  return env.ASSETS.fetch(new URL('/_ainook/' + filename, url));
}

async function rendered(env, url, name, status = 200) {
  const filename = name + '.html';
  const result = await asset(env, url, filename);
  if (!result.ok) return result;
  const headers = new Headers(result.headers);
  for (const [key, value] of Object.entries(fileHeaders)) headers.set(key, value);
  headers.set('Cache-Control', 'no-cache');
  headers.set('Content-Type', 'text/html; charset=utf-8');
  headers.set('Content-Security-Policy', routes.policies['/_ainook/' + filename] ||
    "default-src 'none'; frame-ancestors 'none'");
  return new Response(result.body, {status, headers});
}

function validateSnapshot(value, now) {
  if (value?.timezone !== 'Asia/Shanghai' || !Array.isArray(value.events) || value.events.length > 500) {
    throw new Error('Invalid reset snapshot');
  }
  const ids = new Set();
  const knownSources = new Set();
  for (const row of value.events) {
    if (!row || typeof row.id !== 'string' || !row.id.trim() || ids.has(row.id) ||
        !platforms.includes(row.platform) || !Object.hasOwn(forms, row.kind) ||
        !['confirmed', 'pending'].includes(row.state) || typeof row.text !== 'string' ||
        !row.text.trim() || row.text.length > 600 || typeof row.url !== 'string') {
      throw new Error('Invalid reset event');
    }
    const original = new URL(row.url);
    const published = time(row.announced_at);
    const confirmed = time(row.confirmed_at);
    const key = row.platform + ':' + (original.pathname.match(/\/status\/(\d+)\/?$/)?.[1] || row.url);
    if (original.protocol !== 'https:' || original.username || original.password || original.port ||
        !sources.has(original.hostname) || knownSources.has(key) || !Number.isFinite(published) || published > now ||
        (row.state === 'confirmed' && (!Number.isFinite(confirmed) || confirmed < published || confirmed > now)) ||
        [row.expires_at, row.scheduled_at].some(stamp => stamp != null && !Number.isFinite(time(stamp)))) {
      throw new Error('Invalid reset event date or source');
    }
    ids.add(row.id);
    knownSources.add(key);
  }
  return value;
}

function time(value) {
  return typeof value === 'string' && /(?:Z|[+-]\d\d:\d\d)$/.test(value) ? Date.parse(value) : NaN;
}

async function refreshResetSnapshot(env) {
  const response = await fetch(feed, {signal: AbortSignal.timeout(15000), cache: 'no-store'});
  if (!response.ok) throw new Error('GitHub reset snapshot returned ' + response.status);
  const body = await boundedText(response, 2_000_000);
  validateSnapshot(JSON.parse(body), Date.now());
  await env.DB.prepare(
    'INSERT INTO reset_snapshot(id, body) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET body=excluded.body WHERE body<>excluded.body',
  ).bind(body).run();
}

function projectReset(fallback, events, now) {
  if (!events.length) return fallback;
  const today = beijing(now).slice(0, 10);
  const recent = events.map(event => ({...event, stamp: time(event.announced_at)}))
    .filter(event => event.stamp <= now).sort((a, b) => b.stamp - a.stamp);
  if (!recent.length) return fallback;
  const latest = recent[0];
  const stamp = beijing(latest.stamp);
  const [type, form] = forms[latest.kind];
  const confirmedByKind = {};
  let issued = null;
  for (const event of recent) {
    if (event.state !== 'confirmed') continue;
    const day = beijing(time(event.confirmed_at)).slice(0, 10);
    if (day !== today && time(event.expires_at) <= now) continue;
    confirmedByKind[event.kind] ??= event.stamp;
    if (!issued || day > issued) issued = day;
  }
  let signal = 0;
  let nextEvent = null;
  for (const event of recent) {
    if (event.state !== 'pending' || event.stamp < (confirmedByKind[event.kind] || 0)) continue;
    const expiry = time(event.expires_at) || event.stamp + 2 * DAY;
    if (expiry <= now) continue;
    signal = Math.max(signal, expiry);
    const scheduled = time(event.scheduled_at);
    if (scheduled > now && (!nextEvent || scheduled < time(nextEvent.at))) {
      nextEvent = {at: event.scheduled_at, id: event.id, url: event.url};
    }
  }
  const points = [...new Set(recent.filter(event => event.kind === latest.kind).map(event => event.stamp))]
    .slice(0, 5).reverse();
  const intervals = points.slice(1).map((point, index) => point - points[index]);
  const estimate = intervals.length >= 2 ? {type, samples: points.length,
    from: beijing(latest.stamp + Math.min(...intervals)).slice(0, 10),
    to: beijing(latest.stamp + Math.max(...intervals)).slice(0, 10),
  } : null;
  return {...fallback, issued_day: issued, next_event: nextEvent,
    signal_until: signal ? new Date(signal).toISOString() : null, estimate,
    latest: {id: latest.id, date: stamp.slice(0, 10), time: stamp.slice(11, 16), published_at: latest.announced_at,
      type, form, title: latest.text, status: time(latest.expires_at) <= now ? '已到期 · 历史记录' : ''}};
}

const totalsQuery = env => env.DB.prepare('SELECT platform, total FROM wish_totals');
const totalsObject = result => Object.fromEntries(result.results.map(row => [row.platform, row.total]));

async function cards(env, url) {
  const [initial, data] = await Promise.all([
    asset(env, url, 'initial-cards.json').then(response => response.json()),
    env.DB.batch([totalsQuery(env), env.DB.prepare('SELECT body FROM reset_snapshot WHERE id=1')]),
  ]);
  const now = Date.now();
  if (!data[1].results.length) return {...initial, totals: totalsObject(data[0])};
  const snapshot = validateSnapshot(JSON.parse(data[1].results[0].body), now);
  return {totals: totalsObject(data[0]), items: initial.items.map(item =>
    projectReset(item, snapshot.events.filter(row => row.platform === item.id), now))};
}

async function boundedText(message, maximum) {
  if (Number(message.headers.get('Content-Length')) > maximum) throw new RangeError('Body exceeds limit');
  const reader = message.body?.getReader();
  if (!reader) return '';
  const decoder = new TextDecoder();
  let bytes = 0;
  let text = '';
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > maximum) throw new RangeError('Body exceeds limit');
      text += decoder.decode(value, {stream: true});
    }
    return text + decoder.decode();
  } finally {
    await reader.cancel();
  }
}

async function wish(request, env, url) {
  if (request.headers.get('Origin') !== url.origin) return json({error: '拒绝跨站写入'}, 403);
  if (env.WISH_LIMIT) {
    const {success} = await env.WISH_LIMIT.limit({key: request.headers.get('CF-Connecting-IP') || 'local'});
    if (!success) return json({error: '请求过于频繁，请稍后重试'}, 429, {'Retry-After': '60'});
  }
  if (request.headers.get('Content-Type')?.split(';')[0].trim() !== 'application/json') {
    return json({error: '请求参数无效'}, 400);
  }
  let data;
  try {
    data = JSON.parse(await boundedText(request, 2048));
  } catch {
    return json({error: '请求参数无效'}, 400);
  }
  const {platform, count, batch_id: batch} = data || {};
  if (!platforms.includes(platform) || !Number.isSafeInteger(count) || count < 1 || count > 200 ||
      typeof batch !== 'string' || !/^[a-zA-Z0-9_-]{16,100}$/.test(batch)) {
    return json({error: '点击批次无效'}, 400);
  }
  const [added, result] = await env.DB.batch([
    env.DB.prepare('INSERT OR IGNORE INTO wish_batches(platform, batch_id, amount) VALUES (?, ?, ?)').bind(platform, batch, count),
    env.DB.prepare(
      'SELECT t.total, b.amount FROM wish_totals t JOIN wish_batches b USING (platform) WHERE b.platform=? AND b.batch_id=?',
    ).bind(platform, batch),
  ]);
  const row = result.results[0];
  if (row.amount !== count) return json({error: '同一批次不能更改点击数'}, 400);
  return json({platform, total: row.total, accepted: count, duplicate: !added.meta.changes});
}

function authorView(url) {
  const {searchParams: params} = url;
  const room = params.get('room');
  const friend = params.get('friend') ?? (room === 'duo' ? 'acan' : null);
  const theme = params.get('theme-preview');
  let view = 'directory';
  if (routes.friends.includes(friend)) {
    view = 'friend-' + friend;
    if (friend === 'acan' && params.get('scene') === 'original') view += '-original';
  } else if (!friend && routes.rooms.includes(room) && params.get('wing') !== 'friends') {
    view = 'room-' + room;
  }
  return 'author/' + view + (['day', 'night'].includes(theme) ? '-' + theme : '');
}

function pagination(path, filters, total) {
  const links = [];
  const {query, source, days, offset} = filters;
  for (const [label, position] of [['← 上一页', offset - 20], ['下一页 →', offset + 20]]) {
    if (position >= 0 && position < total) {
      const search = new URLSearchParams({q: query, source, days, offset: position});
      links.push('<a href="' + path + '?' + escapeHTML(search) + '">' + label + '</a>');
    }
  }
  if (!links.length) return '';
  return '<nav class="editorial-pages" aria-label="分页"><span>第 ' + (Math.floor(offset / 20) + 1) +
    ' / ' + Math.ceil(total / 20) + ' 页</span><div>' + links.join('') + '</div></nav>';
}

function filteredPage(response, path, filters, results, total) {
  const {source, query, days} = filters;
  const active = Boolean(query || source || days !== 'all');
  const clear = active ? '<a class="editorial-clear" href="' + path + '">清除筛选</a>' : '';
  const rows = results.map(result => result.row).join('') ||
    '<p class="editorial-empty">当前没有符合条件的资讯。</p>';
  const feed = '<section class="editorial-feed" aria-labelledby="feed-heading">' +
    '<header class="editorial-feed-head"><h2 id="feed-heading">' + (active ? '搜索结果' : '本期资讯') +
    '</h2><div><span>' + total + ' 条资讯</span>' + clear + '</div></header>' + rows + '</section>' +
    pagination(path, filters, total);
  const replaceOptions = value => ({element(option) {
    if (option.getAttribute('value') === value) option.setAttribute('selected', '');
    else option.removeAttribute('selected');
  }});
  return new HTMLRewriter()
    .on('input[name=q]', {element(input) { input.setAttribute('value', query); }})
    .on('select[name=source] option', replaceOptions(source))
    .on('select[name=days] option', replaceOptions(days))
    .on('.editorial-spotlight', {element(element) { element.remove(); }})
    .on('.editorial-pages', {element(element) { element.remove(); }})
    .on('.editorial-feed', {element(element) { element.replace(feed, {html: true}); }})
    .transform(response);
}

async function readNews(env, url, path, api) {
  if (Object.hasOwn(routes.legacy, path)) {
    if (!api) return Response.redirect(new URL(routes.legacy[path] + url.search, url), 302);
    path = routes.legacy[path];
  }
  if (path === '/models') return api ? json({status: 'not_configured', items: []})
    : Response.redirect(new URL('/news/model', url), 302);
  if (!api && (!url.search || path === '/news/sources')) return rendered(env, url, path.slice(1));
  const index = await asset(env, url, 'news-index.json').then(response => response.json());
  if (path === '/news/sources') return json({mode: 'edition', updated: index.updated, sources: index.sources});
  const params = url.searchParams;
  const wantedSource = params.get('source') || '';
  const source = index.sources.some(row => row.id === wantedSource) ? wantedSource : '';
  const days = DAYS.includes(params.get('days')) ? params.get('days') : 'all';
  const query = (params.get('q') || '').trim().slice(0, 140);
  const rawOffset = params.get('offset') ?? '0';
  if (!/^[+-]?\d+$/.test(rawOffset)) return json({error: '请求参数无效'}, 400);
  const offset = Math.max(0, Math.min(10000, Number(rawOffset)));
  if (!api && !offset && !query && !source && days === 'all') return rendered(env, url, path.slice(1));
  const cutoff = days === 'all' ? 0 : time(index.updated) - Number(days) * DAY;
  const keyword = query.toLowerCase().replaceAll('ß', 'ss').replaceAll('ς', 'σ');
  const filtered = index.items.filter(item => (path === '/news' || '/' + item.section === path) &&
    (!source || item.source === source) && (!cutoff || time(item.published_at) >= cutoff) &&
    item.search.includes(keyword));
  const results = filtered.slice(offset, offset + 20);
  if (api) {
    const items = await Promise.all(results.map(item => asset(env, url, 'article/' + item.id + '.json')
      .then(response => response.json())));
    return json({items, total: filtered.length, offset, limit: 20});
  }
  const page = await rendered(env, url, path.slice(1));
  return filteredPage(page, path, {query, source, days, offset}, results, filtered.length);
}

async function article(env, url, path, api) {
  const item = path.slice('/article/'.length);
  if (!/^[0-9a-f]{24}$/.test(item) || !routes.policies['/_ainook/article/' + item + '.html']) {
    return json({error: '资讯不存在'}, 404);
  }
  if (api) return json(await asset(env, url, 'article/' + item + '.json').then(response => response.json()));
  if (url.search === '?inline=1') return rendered(env, url, 'article/' + item + '-inline');
  return rendered(env, url, 'article/' + item);
}

async function handle(request, env) {
  const url = new URL(request.url);
  const {pathname: path, searchParams: params} = url;
  if (request.method === 'POST' && path === '/api/site/wishes') return wish(request, env, url);
  if (!['GET', 'HEAD'].includes(request.method)) return json({error: '请求方法不支持'}, 405);
  if (path.startsWith('/assets/')) return env.ASSETS.fetch(request);
  if (path === '/api/site/status') return json({service: 'ainook-quota'});
  if (path === '/api/site/wishes') return json({totals: totalsObject(await totalsQuery(env).all())});
  if (path === '/api/site/cards') return json(await cards(env, url));
  if (path === '/') {
    const [page, data] = await Promise.all([rendered(env, url, 'home'), cards(env, url)]);
    return new HTMLRewriter().on('#initial-cards', {element(template) {
      template.setInnerContent(JSON.stringify(data));
    }}).transform(page);
  }
  if (path === '/author') return rendered(env, url, authorView(url));
  if (path === '/privacy') return rendered(env, url, 'privacy');
  if (path === '/quota') {
    const days = ['7', '30', '90', 'all'].includes(params.get('days')) ? params.get('days') : '30';
    const platform = platforms.includes(params.get('platform')) ? params.get('platform') : 'all';
    return rendered(env, url, 'quota/' + days + '-' + platform);
  }
  if (['/abc/focus.html', '/quota/', '/privacy/'].includes(path)) {
    return Response.redirect(new URL(path === '/abc/focus.html' ? '/' : path.slice(0, -1), url), 301);
  }
  const api = path.startsWith('/api/site/');
  const route = api ? path.slice('/api/site'.length) : path;
  if (route.startsWith('/article/')) return article(env, url, route, api);
  if (routes.news.includes(route) || Object.hasOwn(routes.legacy, route) ||
      ['/news/sources', '/models'].includes(route)) return readNews(env, url, route, api);
  if (path === '/robots.txt') return new Response('User-agent: *\nDisallow: /\n', {
    headers: {'Content-Type': 'text/plain; charset=utf-8'},
  });
  if (path === '/favicon.ico') return new Response(null, {status: 204});
  return json({error: '页面不存在'}, 404);
}

export default {
  async fetch(request, env) {
    try {
      const response = await handle(request, env);
      return request.method === 'HEAD' ? new Response(null, {status: response.status, headers: response.headers}) : response;
    } catch (error) {
      console.error(error);
      return json({error: '服务暂时不可用，请稍后重试'}, 503);
    }
  },
  async scheduled(_event, env) {
    await refreshResetSnapshot(env);
  },
};

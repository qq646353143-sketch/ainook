'use strict';
(() => {
  const $=id=>document.getElementById(id);
  const more=$('more'), reload=$('reload');
  const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=new Intl.NumberFormat('zh-CN').format;
  const beijingDay=now=>new Date(now+8*3600000).toISOString().slice(0,10);
  const initial=$('initial-cards');
  const initialData=JSON.parse(initial.content.textContent);
  initial.remove();
  const platforms=initialData.items.map(({id,name,owner,logo})=>({id,name,owner,logo}));
  let cards=platforms.map(p=>({...p})),loadError=false,loading=false;
  let clockTimer;
  let owner;try{owner=sessionStorage.getItem('easel-preview-client')||crypto.randomUUID();sessionStorage.setItem('easel-preview-client',owner);}catch{owner=crypto.randomUUID();}
  // Preserve unsent click batches when the existing site changes direction.
  const prefix='easel.preview.wishes.'+owner+'.';
  const wishes=Object.fromEntries(platforms.map(p=>[p.id,{base:null,unsent:0,queue:[],busy:false,timer:null,error:false,persisted:true}]));
  try{for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i);if(!key?.startsWith(prefix))continue;try{const b=JSON.parse(localStorage.getItem(key));if(wishes[b.platform]&&Number.isSafeInteger(b.count)&&b.count>0&&typeof b.batch_id==='string')wishes[b.platform].queue.push(b);}catch{}}}catch{}
  const pending=s=>s.unsent+s.queue.reduce((n,b)=>n+b.count,0);
  async function api(path,options={}){const r=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers},signal:AbortSignal.timeout(15000)});if(!r.ok)throw new Error('request failed');return r.json();}
  function elapsed(event,now){
    const stamp=Date.parse(event?.published_at);
    if(!Number.isFinite(stamp)||stamp>now)return null;
    const hours=Math.floor((now-stamp)/3600000);
    return {days:Math.floor(hours/24),hours:hours%24};
  }
  function latestRecord(c){
    const event=c.latest;
    if(!event)return '<span class="time-label">距上次重置公告</span><div class="elapsed unknown">暂无收录</div>';
    const age=elapsed(event,Date.now());
    const stamp=event.published_at||event.date;
    const clock=age
      ?`<div class="elapsed"><b data-days>${age.days}</b><span class="unit">天</span><b data-hours>${age.hours}</b><span class="unit">小时</span></div>`
      :'<div class="elapsed unknown">暂无确切时刻</div>';
    return `<span class="time-label">距上次重置公告</span>${clock}<div class="record-date"><time datetime="${esc(stamp)}">${esc(event.date.replaceAll('-','.'))}${event.time?' '+esc(event.time):''}</time></div><p class="record-headline">${esc(event.form)}</p>`;
  }
  function upcoming(c,now){
    if(c.issued_day===beijingDay(now))return {state:'issued',label:'已经重置'};
    if(Date.parse(c.next_event?.at)>now||Date.parse(c.signal_until)>now)return {state:'signal',label:'已有信号'};
    return {state:'unknown',label:'尚未公布'};
  }
  function drawUpcoming(element,c,now){
    const next=upcoming(c,now);
    if(element.dataset.status===next.state&&element.textContent===next.label)return;
    element.dataset.status=next.state;
    element.textContent=next.label;
  }
  function showEstimates(now){
    $('estimates').innerHTML=cards.map(c=>{
      const e=c.estimate;
      if(!e)return `<article class="estimate-card"><h3>${esc(c.name)}</h3><strong>暂无可用预估</strong><small>同类公告样本不足</small></article>`;
      const format=d=>(d.slice(0,4)===beijingDay(now).slice(0,4)?d.slice(5):d).replaceAll('-','/');
      const range=e.from===e.to?format(e.from):format(e.from)+' 至 '+format(e.to);
      const note=e.to<beijingDay(now)?'参考窗口已过':e.samples+' 条'+e.type+'公告 · 非官方';
      return `<article class="estimate-card"><h3>${esc(c.name)}</h3><strong>${esc(range)}</strong><small>${esc(note)}</small></article>`;
    }).join('');
  }
  function updateClock(){
    const now=Date.now();
    const midnight=Date.parse(beijingDay(now)+'T00:00:00+08:00')+86400000;
    cards.forEach(c=>{
      const card=$('card-'+c.id);
      if(!card)return;
      const age=elapsed(c.latest,now),days=card.querySelector('[data-days]');
      if(age&&days){
        days.textContent=age.days;
        card.querySelector('[data-hours]').textContent=age.hours;
      }
      drawUpcoming(card.querySelector('.next-reset-value'),c,now);
    });
    if(more?.open)showEstimates(now);
    clearTimeout(clockTimer);
    clockTimer=setTimeout(updateClock,Math.min(30000,midnight-now));
  }
  const refresh='<svg class="reset-icon" viewBox="0 0 24 24" aria-hidden="true" width="18" height="18"><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M13 6.7h4.3V2.4"/></svg>';
  function render(){
    $('platforms').innerHTML=cards.map(c=>{
      return `<article class="quota-card ${c.id}" id="card-${c.id}" aria-labelledby="name-${c.id}">
        <span class="edge-light" aria-hidden="true"></span>
        <span class="card-light" aria-hidden="true"><i class="card-spotlight"></i></span>
        <header class="identity"><div class="emblem"><img src="/assets/${esc(c.logo)}" alt="" width="57" height="57"></div><h2 id="name-${c.id}">${esc(c.name)}</h2><p>${esc(c.owner)}</p></header>
        <div class="reset-time">${latestRecord(c)}</div>
        <div class="next-reset"><span>下次重置</span><strong class="next-reset-value"></strong></div>
        <div class="wish-meta"><span>累计求重置</span><span><span class="wish-count" id="count-${c.id}">—</span><small>次</small></span></div>
        <button class="wish-control" data-wish="${c.id}" disabled aria-label="为 ${esc(c.name)} 求重置" aria-describedby="wish-note" title="表达愿望，不会影响官方额度">${refresh}<span>求重置</span><span class="click-plus" aria-hidden="true">+1</span></button>
        <p class="wish-error" id="wish-error-${c.id}" role="status"></p>
      </article>`;
    }).join('');
    platforms.forEach(p=>paintCount(p.id));
    updateClock();
  }
  function paintCount(id){
    const s=wishes[id],el=$('count-'+id),value=s.base===null?'—':number(s.base+pending(s));
    if(el&&el.textContent!==value)el.textContent=value;
    const b=document.querySelector(`[data-wish="${id}"]`);if(b)b.disabled=s.base===null;
    const slot=$('wish-error-'+id);if(!slot)return;slot.replaceChildren();
    if(s.error||(loadError&&s.base===null)){slot.append(document.createTextNode(s.base===null?'暂时未连上记录。':s.persisted?'点击已暂存，恢复连接后保存。':'保存暂不可用，请保留页面重试。'));const retry=document.createElement('button');retry.textContent='重试';retry.dataset.retryWish=id;slot.append(retry);}
  }
  function stash(id){const s=wishes[id];if(!s.unsent)return;const b={platform:id,count:s.unsent,batch_id:crypto.randomUUID()};s.unsent=0;s.queue.push(b);try{localStorage.setItem(prefix+b.batch_id,JSON.stringify(b));s.persisted=true;}catch{s.persisted=false;}}
  async function drain(id){
    const s=wishes[id];clearTimeout(s.timer);stash(id);if(s.busy)return;s.busy=true;
    try{while(s.queue.length){const b=s.queue[0],r=await api('/api/site/wishes',{method:'POST',body:JSON.stringify(b)});s.base=r.total;s.queue.shift();s.error=false;try{localStorage.removeItem(prefix+b.batch_id);}catch{}paintCount(id);$('sr-feedback').textContent='心愿已保存，累计 '+number(r.total)+' 次。';}}
    catch{s.error=true;paintCount(id);}finally{s.busy=false;if(s.unsent)s.timer=setTimeout(()=>drain(id),650);}
  }
  function wish(id,button){const s=wishes[id];if(!s||s.base===null)return;s.unsent++;paintCount(id);window.AinookPress(button);clearTimeout(s.timer);s.timer=setTimeout(()=>drain(id),650);if(s.unsent>=30)drain(id);}
  function applyCards(data){
    cards=platforms.map(p=>({...data.items.find(c=>c.id===p.id),...p}));
    for(const [id,total]of Object.entries(data.totals))if(wishes[id]&&!wishes[id].busy)wishes[id].base=total;
    loadError=false;
  }
  async function refreshCards(){
    if(document.hidden||loading)return;
    try{
      const data=await api('/api/site/cards');
      if(loading)return;
      const previous=cards;
      applyCards(data);
      cards.forEach((c,index)=>{
        if(JSON.stringify(c.latest)!==JSON.stringify(previous[index].latest)){
          $('card-'+c.id).querySelector('.reset-time').innerHTML=latestRecord(c);
        }
        paintCount(c.id);
        if(wishes[c.id].error)drain(c.id);
      });
      updateClock();
    }catch{}
  }
  function restorePending(){platforms.forEach(p=>{if(wishes[p.id].queue.length)drain(p.id);});}
  async function load(){
    if(loading)return;
    loading=true;
    if(reload){reload.disabled=true;reload.setAttribute('aria-busy','true');}
    try{applyCards(await api('/api/site/cards'));}
    catch{loadError=true;}
    render();
    if(reload){reload.disabled=false;reload.setAttribute('aria-busy','false');}
    loading=false;
    restorePending();
  }
  document.addEventListener('click',e=>{const b=e.target.closest('[data-wish]');if(b){wish(b.dataset.wish,b);return;}const r=e.target.closest('[data-retry-wish]');if(r){if(wishes[r.dataset.retryWish].base===null)load();else drain(r.dataset.retryWish);}});
  reload?.addEventListener('click',load);
  more?.addEventListener('toggle',()=>{if(more.open)showEstimates(Date.now());});
  if(more)document.addEventListener('keydown',e=>{if(e.key==='Escape'&&more.open){more.open=false;more.querySelector('summary').focus();}});
  window.addEventListener('online',()=>{if(loadError)load();else platforms.forEach(p=>drain(p.id));});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)platforms.forEach(p=>stash(p.id));else{updateClock();restorePending();}});
  window.addEventListener('pagehide',()=>{platforms.forEach(p=>{stash(p.id);for(const b of wishes[p.id].queue)fetch('/api/site/wishes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b),keepalive:true}).catch(()=>{});});});
  setInterval(refreshCards,30000);
  applyCards(initialData);
  render();
  restorePending();
})();

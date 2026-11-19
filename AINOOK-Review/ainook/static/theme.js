'use strict';
(() => {
  const root=document.documentElement;
  const preview=new URLSearchParams(location.search).get('theme-preview');
  let forced=preview==='day'||preview==='night'?preview:null;
  const key='ainook.theme';
  const labels={auto:'自动',day:'白天',night:'夜晚'};
  let preference='auto';
  try {
    const saved=localStorage.getItem(key);
    if(saved==='day'||saved==='night')preference=saved;
  } catch {}
  let control;
  let timer;
  const timeTheme=hour=>hour>=7&&hour<19?'day':'night';
  function nextMode(mode, automatic){
    if(mode==='auto')return automatic==='day'?'night':'day';
    return mode===automatic?'auto':automatic;
  }
  function sync(){
    clearTimeout(timer);
    const now=new Date(),hour=now.getHours();
    const automatic=timeTheme(hour);
    const mode=forced||preference;
    const theme=mode==='auto'?automatic:mode;
    root.dataset.theme=theme;
    root.dataset.themeMode=forced?'preview':preference;
    if(control){
      control.textContent=labels[mode];
      control.setAttribute('aria-label',`主题${labels[mode]}，切换为${labels[nextMode(mode,automatic)]}`);
      control.title=`切换为${labels[nextMode(mode,automatic)]}`;
    }
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta)meta.content=theme==='day'?'#e2eaf4':'#090b10';
    if(mode!=='auto')return;
    const boundary=new Date(now);
    if(hour<7)boundary.setHours(7,0,0,0);
    else if(hour<19)boundary.setHours(19,0,0,0);
    else{boundary.setDate(boundary.getDate()+1);boundary.setHours(7,0,0,0);}
    // Reach each boundary promptly and recover from device clock/timezone changes.
    timer=setTimeout(sync,Math.min(60000,Math.max(100,boundary.getTime()-now.getTime()+30)));
  }
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)sync();});
  window.addEventListener('focus',sync);
  window.addEventListener('pageshow',sync);
  document.addEventListener('DOMContentLoaded',()=>{
    control=document.getElementById('theme-switch');
    if(!control)return;
    control.disabled=false;
    control.addEventListener('click',()=>{
      preference=nextMode(forced||preference,timeTheme(new Date().getHours()));
      if(forced){
        const url=new URL(location.href);
        url.searchParams.delete('theme-preview');
        history.replaceState(history.state,'',url);
        forced=null;
      }
      try {localStorage.setItem(key,preference);} catch {}
      sync();
    });
    sync();
  });
  sync();
})();

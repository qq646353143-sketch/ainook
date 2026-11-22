'use strict';
(() => {
  const root=document.documentElement;
  const preview=new URLSearchParams(location.search).get('theme-preview');
  let forced=preview==='day'||preview==='night'?preview:null;
  const key='ainook.theme';
  const labels={day:'白天',night:'晚上'};
  let preference='day';
  let control;
  const nextTheme=theme=>theme==='day'?'night':'day';

  function readPreference(){
    try {
      const saved=localStorage.getItem(key);
      if(saved==='day'||saved==='night')preference=saved;
    } catch {}
  }

  function sync(){
    const theme=forced||preference;
    root.dataset.theme=theme;
    root.dataset.themeMode=forced?'preview':preference;
    if(control){
      const target=labels[nextTheme(theme)];
      control.textContent=labels[theme];
      control.setAttribute('aria-label',`主题${labels[theme]}，切换为${target}`);
      control.title=`切换为${target}`;
    }
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta)meta.content=theme==='day'?'#e2eaf4':'#090b10';
  }
  window.addEventListener('pageshow',()=>{
    readPreference();
    sync();
  });
  window.addEventListener('storage',event=>{
    if(event.key===key){
      readPreference();
      sync();
    }
  });
  document.addEventListener('DOMContentLoaded',()=>{
    control=document.getElementById('theme-switch');
    if(!control)return;
    control.disabled=false;
    control.addEventListener('click',()=>{
      preference=nextTheme(forced||preference);
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
  readPreference();
  sync();
})();

/* Focus homepage: one larger, higher flying element per click. Motion model informed by the user's React Bits
   ClickSpark reference; native canvas implementation, no runtime dependency. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.EaselBurst = api;
})(typeof window === 'undefined' ? globalThis : window, function () {
  'use strict';
  const groups = [
    {name:'宇航员',items:['🧑‍🚀','🚀','🛸','🌙','🪐','⭐']},
    {name:'小工匠',items:['👷','🧑‍🔧','🔧','🔨','⚙️','🪛']},
    {name:'小画家',items:['🧑‍🎨','🎨','🖌️','🖍️','🖼️','✏️']},
    {name:'小园丁',items:['🧑‍🌾','🌱','🌿','🌻','🥕','🌷']},
    {name:'小厨师',items:['🧑‍🍳','🍳','🥐','🥖','🍅','🥣']},
    {name:'小科学家',items:['🧑‍🔬','🔬','🧪','🧬','⚗️','💡']},
    {name:'小魔法师',items:['🧙','🪄','🔮','✨','🦉','📜']},
    {name:'小消防员',items:['🧑‍🚒','🚒','🧯','⛑️','💧','🪜']},
    {name:'小乐队',items:['🧑‍🎤','🎸','🎺','🎷','🥁','🎵']},
    {name:'小程序员',items:['🧑‍💻','💻','⌨️','🖱️','💾','🤖']},
    {name:'花园',items:['🌸','🌷','🌻','🌼','🌺','🪻']},
    {name:'森林',items:['🌲','🌳','🌿','🍄','🪵','🍃']},
    {name:'小草',items:['🌱','🌿','☘️','🍀','🌾','🌵']},
    {name:'秋天',items:['🍁','🍂','🌰','🍄','🎃','🍎']},
    {name:'春天',items:['🌷','🦋','🐝','🌸','🌱','🐣']},
    {name:'小天气',items:['☀️','🌤️','☁️','🌈','❄️','💧']},
    {name:'海边',items:['🐚','🪸','🌊','🦀','⭐','🐠']},
    {name:'夜空',items:['🌙','⭐','🌟','☄️','🪐','🌌']},
    {name:'小猫咪',items:['🐱','🐈','🐈‍⬛','🐾','🧶','🐟']},
    {name:'小狗狗',items:['🐶','🐕','🦮','🐩','🐾','🦴']},
    {name:'小兔子',items:['🐰','🐇','🥕','🍀','🌼','🌱']},
    {name:'小熊',items:['🐻','🐼','🐨','🧸','🍯','🎋']},
    {name:'小鸟',items:['🐦','🐤','🐥','🦜','🦉','🪶']},
    {name:'小农场',items:['🐮','🐷','🐑','🐔','🐴','🌾']},
    {name:'小昆虫',items:['🐝','🐞','🦋','🐛','🐌','🌼']},
    {name:'小海洋',items:['🐳','🐬','🐙','🦭','🐢','🐠']},
    {name:'小恐龙',items:['🦕','🦖','🥚','🌴','🪨','🌿']},
    {name:'小狐狸',items:['🦊','🦝','🦔','🐿️','🌰','🍁']},
    {name:'小汽车',items:['🚗','🚙','🚕','🚓','🏎️','🛞']},
    {name:'城市通勤',items:['🚌','🚎','🚋','🚇','🚲','🛴']},
    {name:'小工程车',items:['🚜','🚚','🚛','🏗️','🦺','🚧']},
    {name:'小火车',items:['🚂','🚃','🚆','🚊','🛤️','🎫']},
    {name:'小飞机',items:['✈️','🛩️','🚁','🪂','☁️','🧳']},
    {name:'小船',items:['⛵','🚤','🛶','🚢','⚓','🌊']},
    {name:'工具箱',items:['🔧','🔨','🪛','🛠️','🧰','🔩']},
    {name:'小木工',items:['🪚','🔨','🪵','📏','🪛','🔩']},
    {name:'小修理铺',items:['⚙️','🔧','🔌','🔋','🪛','💡']},
    {name:'文具盒',items:['✏️','🖍️','📐','📏','📎','✂️']},
    {name:'小书桌',items:['📚','📖','📓','🖊️','📌','☕']},
    {name:'小相机',items:['📷','📸','🎞️','🎥','🎬','🖼️']},
    {name:'小邮局',items:['✉️','📮','📬','📦','💌','🏷️']},
    {name:'小缝纫',items:['🧵','🪡','🧶','✂️','🧣','🧤']},
    {name:'水果篮',items:['🍎','🍊','🍋','🍓','🍒','🍇']},
    {name:'热带水果',items:['🍍','🥭','🥝','🍌','🥥','🍉']},
    {name:'小面包店',items:['🥐','🥖','🥨','🥯','🍞','🧈']},
    {name:'小甜品',items:['🧁','🍰','🍩','🍪','🍮','🍨']},
    {name:'糖果铺',items:['🍬','🍭','🍫','🍡','🍯','🍒']},
    {name:'小饮料',items:['☕','🍵','🧋','🥤','🧃','🥛']},
    {name:'小早餐',items:['🍳','🥞','🧇','🥐','🥓','☕']},
    {name:'小饭馆',items:['🍙','🍜','🍣','🥟','🍱','🍚']},
    {name:'小运动',items:['⚽','🏀','🏐','🎾','🏸','🏓']},
    {name:'小玩具',items:['🧸','🪀','🪁','🧩','🎲','🚂']},
    {name:'小露营',items:['🏕️','⛺','🧭','🔦','🎒','🌲']},
    {name:'小岛',items:['🏝️','🌴','🥥','🐚','⛱️','🌊']},
    {name:'小房子',items:['🏠','🏡','🏘️','🪴','🛋️','🪟']},
    {name:'小机器人',items:['🤖','⚙️','💡','🔋','🛰️','💻']},
    {name:'小音乐盒',items:['🎹','🎻','🎼','🎶','🪗','🎧']},
    {name:'小心愿',items:['💌','🍀','🌟','🎁','🎐','🕊️']}
  ];
  let previous = -1;
  function sample(random = Math.random) {
    const index = previous < 0 ? Math.floor(random()*groups.length) : (previous+1+Math.floor(random()*(groups.length-1)))%groups.length;
    previous = index;
    const items = groups[index].items;
    return {name:groups[index].name,items:[items[Math.floor(random()*items.length)]]};
  }
  function trajectory(rect, random = Math.random) {
    return {x:rect.left+rect.width/2,y:rect.top+rect.height/2,vx:(random()-.5)*60,vy:-680-random()*60,gravity:465,life:1730+random()*130};
  }
  let canvas, ctx, particles=[], raf=0, dirty=null;
  const sprites = new Map();
  function resize(){
    if(!canvas||!ctx)return;
    const pixelBudget=1600000;
    const dpr=Math.min(window.devicePixelRatio||1,2,Math.sqrt(pixelBudget/(innerWidth*innerHeight)));
    canvas.width=Math.ceil(innerWidth*dpr);
    canvas.height=Math.ceil(innerHeight*dpr);
    ctx.setTransform(dpr,0,0,dpr,0,0);
    dirty=null;
  }
  function erase(){
    if(!dirty)return;
    ctx.clearRect(dirty.left,dirty.top,dirty.right-dirty.left,dirty.bottom-dirty.top);
    dirty=null;
  }
  function clear(){particles=[];if(raf)cancelAnimationFrame(raf);raf=0;erase();if(canvas)canvas.dataset.active='0';}
  function init(){
    if(canvas)return;
    canvas=document.createElement('canvas');canvas.id='wish-confetti';canvas.setAttribute('aria-hidden','true');canvas.dataset.groups=String(groups.length);document.body.append(canvas);ctx=canvas.getContext('2d');resize();
    window.addEventListener('resize',resize,{passive:true});document.addEventListener('visibilitychange',()=>{if(document.hidden)clear();});window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change',clear);
  }
  function sprite(text){
    if(sprites.has(text))return sprites.get(text);
    const image=document.createElement('canvas');image.width=96;image.height=96;
    const c=image.getContext('2d');c.font='58px "Segoe UI Emoji","Apple Color Emoji","Noto Color Emoji",sans-serif';c.textAlign='center';c.textBaseline='middle';c.fillText(text,48,50);sprites.set(text,image);
    if(sprites.size>64)sprites.delete(sprites.keys().next().value);
    return image;
  }
  function tick(now){
    erase();particles=particles.filter(p=>now-p.start<p.life);
    for(const p of particles){
      const elapsed=(now-p.start)/1000,t=(now-p.start)/p.life;
      const x=p.x+p.vx*elapsed,y=p.y+p.vy*elapsed+p.gravity*elapsed*elapsed;
      const fade=t>.78?Math.max(0,(1-t)/.22):1,scale=Math.min(1,t*12)*(1-.08*t);
      const size=p.size*scale,radius=size*Math.SQRT1_2+2;
      const left=Math.floor(x-radius),top=Math.floor(y-radius),right=Math.ceil(x+radius),bottom=Math.ceil(y+radius);
      if(dirty){
        dirty.left=Math.min(dirty.left,left);dirty.top=Math.min(dirty.top,top);
        dirty.right=Math.max(dirty.right,right);dirty.bottom=Math.max(dirty.bottom,bottom);
      }else dirty={left,top,right,bottom};
      ctx.save();ctx.translate(x,y);ctx.rotate(p.spin*elapsed);ctx.globalAlpha=fade;ctx.drawImage(p.image,-size/2,-size/2,size,size);ctx.restore();
    }
    const active=String(particles.length);
    if(canvas.dataset.active!==active)canvas.dataset.active=active;
    raf=particles.length?requestAnimationFrame(tick):0;
  }
  function burst(button){
    if(typeof window==='undefined'||window.matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    init();if(!ctx)return;
    const flight=trajectory(button.getBoundingClientRect());
    const set=sample();canvas.dataset.lastGroup=set.name;canvas.dataset.lastCount=String(set.items.length);
    const now=performance.now();
    canvas.dataset.originX=String(flight.x);canvas.dataset.originY=String(flight.y);
    particles.push({...flight,spin:(Math.random()-.5)*2,start:now,size:43+Math.random()*8,image:sprite(set.items[0])});
    if(particles.length>32)particles.splice(0,particles.length-32);
    if(!raf)raf=requestAnimationFrame(tick);
  }
  return {burst,groups,sample,trajectory};
});

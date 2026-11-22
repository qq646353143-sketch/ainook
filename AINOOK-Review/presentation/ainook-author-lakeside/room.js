(() => {
  const root = document.documentElement;
  const art = document.querySelector('.lakeside-art');
  const image = art.querySelector('.lakeside-illustration');
  const controls = art.querySelector('.lakeside-objects');
  const reaction = document.querySelector('.lakeside-reaction p');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const actions = {
    breeze: {
      duration: 2200,
      day: '帘角一掀，卷进几片叶子。',
      night: '几粒微光在帘边停住。',
    },
    letter: {
      day: '休息不该成为奢侈品。',
      close: '沿旧折痕把信叠好。',
    },
    guest: {
      day: '毯子底下露出两只耳朵。',
      night: '它从毯子里探头看夜色。',
      close: '毯子又鼓起一小块。',
    },
    water: {
      duration: 1560,
      day: '近处的倒影碎成几圈。',
      night: '灯影被水纹拉成细线。',
    },
  };
  let lastReaction;

  function syncTheme() {
    const night = root.dataset.theme === 'night';
    image.alt = night
      ? '湖边小屋入夜，屋檐下留着一盏灯，远处的光落在深蓝色的湖水上。'
      : '湖边小屋敞着门，木桌上放着纸笔，露台外是夏日积云、湖水和远山。';
    if (lastReaction) {
      const { action, closed } = lastReaction;
      const copy = actions[action];
      reaction.textContent = closed ? copy.close : (night && copy.night) || copy.day;
    }
  }

  function positionRipple(event, button, effect) {
    const scene = art.getBoundingClientRect();
    const hit = button.getBoundingClientRect();
    const x = event.detail ? event.clientX : hit.left + hit.width / 2;
    const y = event.detail ? event.clientY : hit.top + hit.height / 2;
    const water = getComputedStyle(button);
    const coordinates = [
      ['--x', '--w', (x - scene.left) * 100 / scene.width],
      ['--y', '--h', (y - scene.top) * 100 / scene.height],
    ];
    for (const [axis, span, point] of coordinates) {
      const center = parseFloat(water.getPropertyValue(axis));
      const radius = parseFloat(water.getPropertyValue(span)) * .36;
      // The touch target may extend past the painted water on narrow screens.
      effect.style.setProperty(axis, `${Math.max(center - radius, Math.min(center + radius, point))}%`);
    }
  }

  for (const button of controls.querySelectorAll('button')) {
    const action = button.dataset.action;
    const { duration } = actions[action];
    const effect = art.querySelector(`.lakeside-${action}`);
    let timer;
    button.addEventListener('click', (event) => {
      let closed = false;
      if (duration) {
        if (action === 'water') positionRipple(event, button, effect);
        clearTimeout(timer);
        // Reinsert the effect in the layout so it can play again immediately.
        effect.hidden = true;
        effect.getBoundingClientRect();
        effect.hidden = false;
        timer = setTimeout(() => { effect.hidden = true; }, reducedMotion.matches ? 800 : duration);
      } else {
        effect.hidden = !effect.hidden;
        closed = effect.hidden;
        button.setAttribute('aria-pressed', String(!closed));
      }
      lastReaction = { action, closed };
      syncTheme();
    });
  }

  controls.hidden = false;
  syncTheme();
  const observer = new MutationObserver(syncTheme);
  observer.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
})();

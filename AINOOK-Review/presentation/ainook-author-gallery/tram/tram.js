(() => {
  const root = document.documentElement;
  const art = document.querySelector('.tram-art');
  const image = art.querySelector('.tram-illustration');
  const controls = art.querySelector('.tram-controls');
  const reaction = document.querySelector('.tram-reaction p');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const copy = {
    ticket: ['车票上多了一枚太阳章。', '晚班票盖着一颗星。', '车票放回桌沿。'],
    strap: ['吊环晃了几下，车还停着。', '灯下的吊环慢慢晃停。'],
    window: ['小团云从远山上游过去。', '山谷灯火上掠过一颗星。'],
    dial: ['亮了三盏灯，还有一站。', '灯亮了，这站叫山坡。', '最后一盏小灯灭了。'],
  };
  let lastAction;

  function syncTheme() {
    const night = root.dataset.theme === 'night';
    image.alt = night
      ? '山坡上的电车亮起车顶暖灯，观景窗外的山谷有零星灯火。'
      : '一节改成书房的青绿色观景电车停在山坡上，窗外有高云和远山。';
    if (lastAction) {
      const [action, closed] = lastAction;
      reaction.textContent = copy[action][closed ? 2 : Number(night)];
    }
  }

  const durations = { strap: 1800, window: 2400 };
  for (const button of controls.querySelectorAll('button')) {
    const name = button.dataset.action;
    const effect = art.querySelector(`.tram-${name}`);
    let timer;
    button.addEventListener('click', () => {
      let closed = false;
      if (name === 'strap' || name === 'window') {
        clearTimeout(timer);
        if (name === 'strap') effect.removeAttribute('data-sway');
        else effect.hidden = true;
        effect.getBoundingClientRect();
        if (name === 'strap') effect.setAttribute('data-sway', '');
        else effect.hidden = false;
        timer = setTimeout(() => {
          if (name === 'strap') effect.removeAttribute('data-sway');
          else effect.hidden = true;
        }, reducedMotion.matches ? 850 : durations[name]);
      } else {
        effect.hidden = !effect.hidden;
        closed = effect.hidden;
        button.setAttribute('aria-pressed', String(!closed));
      }
      lastAction = [name, closed];
      syncTheme();
    });
  }

  controls.hidden = false;
  syncTheme();
  new MutationObserver(syncTheme).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
})();

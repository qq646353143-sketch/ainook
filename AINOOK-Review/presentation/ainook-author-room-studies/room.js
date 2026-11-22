(() => {
  const root = document.documentElement;
  const data = document.getElementById('room-studies-data');
  const rooms = JSON.parse(data.content.textContent);
  const choices = document.querySelector('.room-studies-choices');
  const art = document.querySelector('.room-studies-art');
  const image = document.querySelector('.room-studies-illustration');
  const effects = document.querySelector('.room-studies-effects');
  const objects = document.querySelector('.room-studies-objects');
  const reaction = document.querySelector('.room-studies-reaction');
  const title = reaction.querySelector('span');
  const message = reaction.querySelector('p');
  let selected;

  function position(element, [x, y, width, height]) {
    element.style.setProperty('--x', `${x}%`);
    element.style.setProperty('--y', `${y}%`);
    element.style.setProperty('--w', `${width}%`);
    element.style.setProperty('--h', `${height}%`);
  }

  function syncTheme() {
    image.alt = selected.alt[root.dataset.theme === 'night' ? 'night' : 'day'];
  }

  function makeObject(config) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'room-studies-object';
    button.setAttribute('aria-label', config.name);
    button.dataset.object = config.effect;
    if (config.off) button.setAttribute('aria-pressed', 'false');
    position(button, config.hit);

    const effect = document.createElement('span');
    effect.className = 'room-studies-effect';
    effect.dataset.effect = config.effect;
    effect.hidden = true;
    position(effect, config.light);
    if (['water', 'steam', 'speaker'].includes(config.effect)) {
      effect.append(...Array.from({ length: 3 }, () => document.createElement('i')));
    }
    effects.append(effect);

    let timer;
    button.addEventListener('click', () => {
      const active = effect.hidden;
      if (config.off) {
        effect.hidden = !active;
        button.setAttribute('aria-pressed', String(active));
      } else {
        clearTimeout(timer);
        effect.hidden = true;
        effect.getBoundingClientRect();
        effect.hidden = false;
        timer = setTimeout(() => { effect.hidden = true; }, 920);
      }
      title.textContent = config.name;
      message.textContent = active || !config.off ? config.on : config.off;
    });
    return button;
  }

  // 作者介绍下方的文字标签（云窗书房、绿植窗台、暖陶客厅）可就地切换方案。
  // 这排标签留在多方案预览中，暂缓调整。
  const links = choices ? rooms.map((room) => {
    const link = document.createElement('a');
    link.textContent = room.name;
    link.addEventListener('click', (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      if (room === selected) return;
      history.pushState(null, '', link.href);
      render();
    });
    return link;
  }) : [];

  function syncChoices() {
    for (const [index, link] of links.entries()) {
      const url = new URL(location.href);
      url.searchParams.set('room', rooms[index].id);
      link.href = url;
      if (rooms[index] === selected) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  }

  function render() {
    const preferred = new URLSearchParams(location.search).get('room');
    selected = rooms.find((room) => room.id === preferred) || rooms[0];
    art.dataset.room = selected.id;
    art.style.setProperty('--room-night-offset', `${selected.nightOffset}%`);
    image.src = selected.image;
    syncTheme();
    title.textContent = '';
    message.textContent = '';
    effects.replaceChildren();
    objects.replaceChildren(...selected.objects.map(makeObject));

    syncChoices();
  }

  if (choices) {
    choices.append(...links);
    choices.hidden = false;
  }
  render();
  window.addEventListener('popstate', render);
  const themeObserver = new MutationObserver(() => {
    syncTheme();
    syncChoices();
  });
  themeObserver.observe(root, { attributes: true, attributeFilter: ['data-theme'] });
})();

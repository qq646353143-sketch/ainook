(() => {
  const art = document.querySelector('.miniature-room-art');
  const controls = art.querySelector('.miniature-room-controls');
  const caption = document.getElementById('miniature-room-object');
  const message = document.getElementById('miniature-room-message');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const objects = {
    lamp: ['台灯', '桌角浮起一圈暖光。', '桌面暗回去了。'],
    note: ['摊开的手记', '满页涂改，角落画着一扇窗。', '书签还夹在这一页。'],
    computer: ['旧电脑', '屏幕只写了一个 hello。', '最后一点绿光熄了。'],
    record: ['唱片机', '唱针落下，钢琴轻轻响起。', '唱针抬起，屋里静了。'],
  };
  let wateringTimer;

  function show(title, description) {
    caption.textContent = title;
    message.textContent = description;
  }

  controls.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-object]');
    if (!button) return;

    const object = button.dataset.object;
    if (object === 'plant') {
      clearTimeout(wateringTimer);
      art.removeAttribute('data-watering');
      // Restart the same drop animation on repeat clicks.
      art.querySelector('.miniature-room-drops').getBoundingClientRect();
      art.setAttribute('data-watering', '');
      wateringTimer = setTimeout(() => art.removeAttribute('data-watering'), reducedMotion.matches ? 480 : 920);
      show('书架边的盆栽', '水滴进土里，洇出深色。');
      return;
    }

    const isOn = button.getAttribute('aria-pressed') === 'false';
    const [title, onMessage, offMessage] = objects[object];
    button.setAttribute('aria-pressed', String(isOn));
    art.toggleAttribute(`data-${object}`, isOn);
    show(title, isOn ? onMessage : offMessage);
  });

  controls.hidden = false;
})();

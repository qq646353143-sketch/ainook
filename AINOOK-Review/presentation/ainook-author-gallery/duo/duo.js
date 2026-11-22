(() => {
  const root = document.documentElement;
  const art = document.querySelector('.duo-art');
  const controls = art.querySelector('.duo-controls');
  const image = art.querySelector('.duo-illustration');
  const feedback = document.querySelector('.duo-room .room-studies-reaction p');
  const lamp = art.querySelector('.duo-lamp');
  const steam = art.querySelector('.duo-cups');
  const team = art.querySelector('.duo-team');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const monitors = {
    left: art.querySelector('.duo-monitor-left'),
    right: art.querySelector('.duo-monitor-right'),
  };
  const towers = {
    left: art.querySelector('.duo-tower-left'),
    right: art.querySelector('.duo-tower-right'),
  };
  let steamTimer;

  function describeTheme() {
    image.alt = root.dataset.theme === 'night'
      ? '夜里，半高墙隔开的双人床和电竞区各留了一点暖光，外面亮着城市灯火。'
      : '半高墙隔开双人床和两台并排的电脑，桌上放着两只杯子。';
  }

  controls.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-piece]');
    if (!button) return;
    const piece = button.dataset.piece;
    if (piece === 'cups') {
      clearTimeout(steamTimer);
      steam.hidden = true;
      steam.getBoundingClientRect();
      steam.hidden = false;
      steamTimer = setTimeout(() => { steam.hidden = true; }, reducedMotion.matches ? 850 : 1650);
      feedback.textContent = '两杯都还热着。';
      return;
    }

    const on = button.getAttribute('aria-pressed') === 'false';
    button.setAttribute('aria-pressed', String(on));
    if (piece === 'lamp') {
      lamp.hidden = !on;
      feedback.textContent = on ? '床头留了一小圈暖光。' : '被角又暗了下来。';
      return;
    }

    monitors[piece].hidden = !on;
    towers[piece].hidden = !on;
    const together = !monitors.left.hidden && !monitors.right.hidden;
    team.hidden = !together;
    if (together) feedback.textContent = '两块屏幕亮了，双排吧。';
    else if (on) feedback.textContent = piece === 'left' ? '左屏醒了，等另一位。' : '右屏醒了，等另一位。';
    else feedback.textContent = '这边的屏幕先休息。';
  });

  describeTheme();
  new MutationObserver(describeTheme).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  controls.hidden = false;
})();

(() => {
  const room = document.querySelector('.doudou-room');
  const scene = room.querySelector('.doudou-set');
  const controls = scene.querySelector('.doudou-controls');
  const feedback = room.querySelector('[role="status"] p');
  const illustration = scene.querySelector('.doudou-artwork img');
  const foregroundPlant = scene.querySelector('.doudou-window-plant img');
  function syncForeground() {
    if (illustration.currentSrc && foregroundPlant.src !== illustration.currentSrc) {
      foregroundPlant.src = illustration.currentSrc;
    }
  }
  illustration.addEventListener('load', syncForeground);
  if (illustration.complete) syncForeground();
  const cushion = scene.querySelector('.doudou-cushion');
  const context = cushion.getContext('2d', { willReadFrequently: true });
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const x = Number(cushion.dataset.x);
  const y = Number(cushion.dataset.y);
  const { width, height } = cushion;
  const panelWidth = Number(illustration.getAttribute('width'));
  const panelHeight = Number(illustration.getAttribute('height')) / 2;
  Object.assign(cushion.style, {
    left: `${x / panelWidth * 100}%`, top: `${y / panelHeight * 100}%`,
    width: `${width / panelWidth * 100}%`, height: `${height / panelHeight * 100}%`,
  });
  const patchedPixels = context?.createImageData(width, height);
  const originalPixels = new Map();
  const across = Array.from({ length: width }, (_, column) => Math.sin(Math.PI * column / (width - 1)) ** 2);
  const down = Array.from({ length: height }, (_, row) => Math.sin(Math.PI * Math.min(row / 94, 1)) ** 2);
  const notes = {
    curtain: ['把窗外留在帘子后面。', '窗外的树又露出来了。'],
    book: ['这一页夹着一片干叶子。', '叶子夹回原来那页。'],
    lamp: ['桌边亮起来了。', '把灯关上，坐一会儿。'],
  };
  let waterTimer;
  let cushionFrame;
  let pressure = 0;

  function renderCushion(pressure) {
    const theme = document.documentElement.dataset.theme;
    const source = `${theme}:${illustration.currentSrc}`;
    if (!originalPixels.has(source)) {
      const panelTop = theme === 'night' ? panelHeight : 0;
      const scale = illustration.naturalWidth / panelWidth;
      context.clearRect(0, 0, width, height);
      context.drawImage(illustration, x * scale, (y + panelTop) * scale,
        width * scale, height * scale, 0, 0, width, height);
      originalPixels.set(source, context.getImageData(0, 0, width, height).data);
    }
    const original = originalPixels.get(source);

    // Sample from the room art so the fabric and shadows match its current lighting.
    // The displacement falls to zero against the backrest and along the seat seam.
    for (let row = 0; row < height; row++) {
      for (let column = 0; column < width; column++) {
        const sourceY = Math.max(0, row - pressure * across[column] * down[row]);
        const above = Math.floor(sourceY);
        const below = Math.min(above + 1, height - 1);
        const mix = sourceY - above;
        const from = (above * width + column) * 4;
        const to = (below * width + column) * 4;
        const target = (row * width + column) * 4;
        for (let channel = 0; channel < 4; channel++) {
          patchedPixels.data[target + channel] = original[from + channel] * (1 - mix) + original[to + channel] * mix;
        }
      }
    }
    context.putImageData(patchedPixels, 0, 0);
  }

  async function pressCushion() {
    feedback.textContent = '靠垫软软地陷下去。';
    if (!context || reducedMotion.matches) return;
    try {
      await illustration.decode();
    } catch {
      return;
    }

    cancelAnimationFrame(cushionFrame);
    const initialPressure = pressure;
    let start;
    const pressTime = 125;
    const releaseTime = 390;
    const depth = 9;
    function animate(time) {
      start ??= time;
      const elapsed = time - start;
      if (elapsed >= pressTime + releaseTime || reducedMotion.matches) {
        pressure = 0;
        cushion.hidden = true;
        return;
      }
      if (elapsed < pressTime) {
        pressure = depth - (depth - initialPressure) * (1 - Math.max(0, elapsed) / pressTime) ** 2;
      } else {
        pressure = depth * (1 - (elapsed - pressTime) / releaseTime) ** 2;
      }
      renderCushion(pressure);
      cushion.hidden = false;
      cushionFrame = requestAnimationFrame(animate);
    }
    cushionFrame = requestAnimationFrame(animate);
  }

  controls.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-object]');
    if (!button) return;
    const object = button.dataset.object;
    if (object === 'cushion') {
      pressCushion();
      return;
    }
    if (object === 'plant') {
      clearTimeout(waterTimer);
      scene.classList.remove('is-watered');
      scene.getBoundingClientRect();
      scene.classList.add('is-watered');
      waterTimer = setTimeout(() => scene.classList.remove('is-watered'), 1050);
      feedback.textContent = '叶尖挂着一颗水珠。';
      return;
    }

    const active = button.getAttribute('aria-pressed') === 'false';
    button.setAttribute('aria-pressed', String(active));
    scene.classList.toggle(`is-${object}`, active);
    feedback.textContent = notes[object][active ? 0 : 1];
  });

  controls.hidden = false;
})();

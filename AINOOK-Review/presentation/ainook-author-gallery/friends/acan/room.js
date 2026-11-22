(() => {
  const root = document.documentElement;
  const art = document.querySelector('.acan-room .duo-art');
  const controls = art.querySelector('.duo-controls');
  const image = art.querySelector('.duo-illustration');
  const feedback = document.querySelector('.acan-room .room-studies-reaction p');
  const clip = controls.querySelector('[data-piece="mic"]');
  const steam = art.querySelector('.duo-cups');
  const micGlow = art.querySelector('.acan-mic-glow');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const details = {
    lamp: { effects: ['.duo-lamp'], open: '今晚也留一盏灯。', close: '灯暗了，窗外还亮着。' },
    frame: { effects: ['.acan-note-frame'], open: '我把菜留好了。', close: '字条夹回相框后面。' },
    left: { effects: ['.duo-monitor-left', '.duo-tower-left'], open: '副歌还差最后一句。', close: '这段先存着。' },
    right: { effects: ['.duo-monitor-right', '.duo-tower-right'], open: '你来啦，位置给你留着。', close: '人散了，下次接着聊。' },
    song: { effects: ['.acan-note-song'], open: '明晚再试着唱一遍。', close: '手记还是夹在那一页。' },
  };
  let audioContext;
  let currentTake;
  let steamTimer;

  function describeTheme() {
    image.alt = root.dataset.theme === 'night'
      ? '城市夜色从卧室窗外透进来，电竞桌边留着暖光，麦克风挨着写歌的电脑。'
      : '矮墙左边是一张双人床，右边是两套并排的电脑，桌上有麦克风和手记。';
  }

  function playNote(context, voice, bus, time, pitch, length, volume) {
    const source = context.createOscillator();
    source.setPeriodicWave(voice);
    source.frequency.value = 440 * 2 ** ((pitch - 69) / 12);
    const envelope = context.createGain();
    envelope.gain.setValueAtTime(0, time);
    envelope.gain.linearRampToValueAtTime(volume, time + .04);
    envelope.gain.exponentialRampToValueAtTime(volume * .28, time + length * .48);
    envelope.gain.exponentialRampToValueAtTime(.00015, time + length);
    source.connect(envelope).connect(bus);
    source.start(time);
    source.stop(time + length + .02);
  }

  function score(context, bus) {
    const start = context.currentTime + .045;
    const beat = .56;
    const voice = context.createPeriodicWave(new Float32Array(5), new Float32Array([0, 1, .28, .11, .05]));
    const melody = [[0, 69, 1.35], [1.5, 72, .7], [2.5, 74, 1.5], [4.25, 72, .9],
      [5.5, 69, .9], [7, 67, 1.5], [9, 69, .75], [10, 72, .9], [11.25, 76, 1.1],
      [12.75, 74, .9], [14, 72, 2.2]];
    const chords = [[53, 57, 60, 64], [48, 55, 59, 64], [57, 60, 64, 67], [55, 59, 62, 64]];
    for (const [position, pitch, beats] of melody) {
      playNote(context, voice, bus, start + position * beat, pitch, beats * beat, .104);
    }
    chords.forEach((chord, bar) => {
      chord.forEach((pitch, offset) => {
        playNote(context, voice, bus, start + (bar * 4 + offset * .59) * beat, pitch, 1.34, offset === 0 ? .069 : .045);
      });
    });
    return (17 * beat + .08) * 1000;
  }

  function stopDemo(message) {
    const take = currentTake;
    if (!take) return;
    currentTake = null;
    clearTimeout(take.timer);
    if (take.bus) {
      if (message) {
        take.bus.gain.setTargetAtTime(0, audioContext.currentTime, .018);
        setTimeout(() => take.bus.disconnect(), 85);
      } else take.bus.disconnect();
    }
    clip.setAttribute('aria-pressed', 'false');
    micGlow.hidden = true;
    art.removeAttribute('data-demo');
    if (message) feedback.textContent = message;
  }

  async function toggleDemo() {
    if (currentTake) return stopDemo('这段旋律先收到这里。');
    const take = {};
    currentTake = take;
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      audioContext ??= new Audio();
      await audioContext.resume();
      if (currentTake !== take) return;
      take.bus = audioContext.createGain();
      take.bus.gain.value = .7;
      take.bus.connect(audioContext.destination);
      take.timer = setTimeout(() => stopDemo('这只是半首歌。'), score(audioContext, take.bus));
      clip.setAttribute('aria-pressed', 'true');
      micGlow.hidden = false;
      art.setAttribute('data-demo', '');
      feedback.textContent = '试听一段还没写完的旋律。';
    } catch {
      if (currentTake === take) stopDemo('这段旋律暂时没响。');
    }
  }

  controls.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-piece]');
    if (!button) return;
    const piece = button.dataset.piece;
    if (piece === 'mic') {
      toggleDemo();
      return;
    }
    if (piece === 'cups') {
      clearTimeout(steamTimer);
      steam.hidden = true;
      steam.getBoundingClientRect();
      steam.hidden = false;
      steamTimer = setTimeout(() => { steam.hidden = true; }, reducedMotion.matches ? 850 : 1650);
      feedback.textContent = '两杯都热着，慢慢聊。';
      return;
    }
    const detail = details[piece];
    const open = button.getAttribute('aria-pressed') !== 'true';
    button.setAttribute('aria-pressed', String(open));
    for (const selector of detail.effects) art.querySelector(selector).hidden = !open;
    feedback.textContent = open ? detail.open : detail.close;
  });

  describeTheme();
  new MutationObserver(describeTheme).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  window.addEventListener('pagehide', () => stopDemo());
  controls.hidden = false;
})();

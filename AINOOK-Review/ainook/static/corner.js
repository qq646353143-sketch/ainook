'use strict';

(() => {
  const button = document.getElementById('corner-button');
  const label = document.getElementById('corner-label');
  const message = document.getElementById('corner-message');
  const symbol = document.getElementById('corner-symbol');
  const dots = symbol.querySelectorAll('i');
  const glint = document.getElementById('corner-glint');
  const constellation = document.getElementById('corner-constellation');
  const edge = button.querySelector('.corner-edge-current rect');
  const mark = symbol.querySelectorAll('.corner-mark-current rect');
  const sky = document.querySelector('.night-sky');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const title = label.textContent;
  const cooldown = 750;
  const notes = {
    ordinary: [
      '这一步已完成。虽然我们也不确定是哪一步。',
      '今天的好奇心余额，够你再点一次。',
      '没有新进展。这个角落对此表示理解。',
      '刚才那一下很轻，服务器决定假装没听见。',
      '这条消息经过了严格筛选，标准是它刚好有空。',
      '按键没有 KPI，可以多按几下。',
    ],
    glint: [
      '刚才有光经过。它赶时间。',
      '这里的灯只亮半秒，省着点看。',
    ],
    dots: [
      '今天的四个点都到齐了。',
      '收到了，四个点一起作证。',
    ],
    roam: [
      '四个点出去兜了一圈。',
      '有几个点坐不住了。',
    ],
    author: [
      '作者吐槽：我本来只想做三张卡片。',
      '作者吐槽：这个角落改了两遍，写说明反而只用了一遍。',
      '作者吐槽：每次说「最后再改一点」，我自己都不太信。',
    ],
    hidden: [
      '你敲到了空心的那块墙。里面藏着一颗星。',
    ],
    current: ['这条线想沿着边缘走一圈。', '边框借了点电，马上还。'],
    outline: ['四个点轮流通了电。', '四个点终于想起自己是个标志。'],
    meteors: ['刚有一小群流星经过。', '星星今天走左边进，右边出。'],
  };
  let animations = [];
  let feature = [];
  let readyAt = 0;
  let resetLabel;

  function animate(element, frames, options) {
    animations.push(element.animate(frames, options));
  }

  const dotGlow = {backgroundColor: 'currentColor', boxShadow: '0 0 7px currentColor'};
  const dotHome = {transform: 'translate(0, 0)'};

  function roamDots() {
    const edge = 9;
    const {clientWidth, clientHeight} = button;
    const destinations = [[.07, edge], [.76, edge], [.35, clientHeight - edge], [.88, clientHeight - edge]];
    dots.forEach((dot, index) => {
      const x = symbol.offsetLeft + dot.offsetLeft + dot.offsetWidth / 2;
      const y = symbol.offsetTop + dot.offsetTop + dot.offsetHeight / 2;
      const [column, lane] = destinations[index];
      const targetX = Math.max(edge, Math.min(clientWidth - edge, column * clientWidth));
      const distance = targetX - x;
      const height = lane - y;
      animate(dot, [
        dotHome,
        {...dotGlow, transform: `translate(${distance * .12}px, ${height}px)`, offset: .16},
        {...dotGlow, transform: `translate(${distance}px, ${height}px)`, offset: .51},
        {...dotGlow, transform: `translate(${distance * .19}px, ${height}px)`, offset: .84},
        dotHome,
      ], {duration: 860 + index * 48, delay: index * 24, easing: 'ease-in-out'});
    });
  }

  function playSmallEffect(kind) {
    if (kind === 'glint') {
      animate(glint, [
        {transform: 'translateX(-65%)', opacity: 0},
        {opacity: 1, offset: .22},
        {opacity: 1, offset: .7},
        {transform: 'translateX(65%)', opacity: 0},
      ], {duration: 490, easing: 'ease-out'});
    }
    if (kind === 'dots') {
      dots.forEach((dot, index) => {
        animate(dot, [
          dotHome, {...dotGlow, transform: 'scale(1.25)'}, dotHome,
        ], {duration: 300, delay: index * 33, easing: 'ease-in-out'});
      });
    }
    if (kind === 'roam') roamDots();
    if (kind === 'hidden') {
      animate(constellation, [
        {opacity: 0}, {opacity: .9, offset: .26}, {opacity: .9, offset: .64}, {opacity: 0},
      ], {duration: 1250, easing: 'ease-in-out'});
    }
  }

  function trace(element, duration, delay = 0) {
    return element.animate([
      {opacity: 0, strokeDashoffset: '0'},
      {opacity: .94, offset: .09},
      {opacity: .94, offset: .9},
      {opacity: 0, strokeDashoffset: '-100'},
    ], {duration, delay});
  }

  function playFeature(kind) {
    let stop;
    if (kind === 'current') feature = [trace(edge, 2650)];
    if (kind === 'outline') feature = [...mark].map((part, index) => trace(part, 2000, index * 135));
    if (kind === 'meteors') ({animations: feature, stop} = playMeteorShower());
    Promise.allSettled(feature.map(animation => animation.finished)).then(() => {
      stop?.();
      feature = [];
      readyAt = performance.now() + cooldown;
    });
  }

  function pickEffect(roll, canAnimate) {
    if (!canAnimate || feature.length || performance.now() < readyAt) return roll < .10 ? 'author' : 'ordinary';
    if (roll < .005) return 'hidden';
    if (roll < .10) return 'author';
    if (roll < .27) return 'glint';
    if (roll < .34) return 'dots';
    if (roll < .43) return 'roam';
    if (roll < .55) return 'current';
    if (roll < .67) return 'outline';
    if (roll < .77 && document.documentElement.dataset.theme === 'night') return 'meteors';
    return 'ordinary';
  }

  function respond() {
    const canAnimate = !reduced.matches && typeof label.animate === 'function';
    const kind = pickEffect(Math.random(), canAnimate);
    const options = notes[kind].filter(note => note !== message.textContent);
    const candidates = options.length ? options : notes[kind];
    const note = candidates[Math.floor(Math.random() * candidates.length)];
    label.textContent = note;
    message.textContent = note;
    button.dataset.cornerEffect = kind;
    clearTimeout(resetLabel);
    resetLabel = setTimeout(() => {
      label.textContent = title;
      message.textContent = '';
      delete button.dataset.cornerEffect;
    }, 5500);
    animations.forEach(animation => animation.cancel());
    animations = [];
    if (!canAnimate) return;
    animate(label, [{opacity: .65}, {opacity: 1}], {duration: 160, easing: 'ease-out'});
    if (kind === 'current' || kind === 'outline' || kind === 'meteors') playFeature(kind);
    else playSmallEffect(kind);
  }

  reduced.addEventListener('change', () => {
    if (!reduced.matches) return;
    animations.forEach(animation => animation.cancel());
    feature.forEach(animation => animation.cancel());
  });
  button.addEventListener('click', respond);

  function playMeteorShower() {
    const layer = document.createElement('div');
    layer.className = 'night-meteors';
    const {clientWidth: width, clientHeight: height} = sky;
    const tailScale = Math.max(.73, Math.min(1, width / 580));
    const between = (min, max) => min + Math.random() * (max - min);
    const groups = [
      {at: 0, band: .095, slope: .038, count: 5, near: false},
      {at: 110, band: .84, slope: .066, count: 3, near: true},
      {at: 620, band: .39, slope: -.024, count: 3, near: false},
      {at: 1420, band: .12, slope: .048, count: 4, near: true},
      {at: 1830, band: .69, slope: .022, count: 3, near: false},
      {at: 2500, band: .07, slope: .035, count: 4, near: false},
      {at: 3075, band: .94, slope: -.028, count: 3, near: true},
    ];
    const moving = [];
    for (const {at, band, slope, count, near} of groups) {
      for (let index = 0; index < count; index++) {
        const meteor = document.createElement('i');
        meteor.className = near ? 'meteor-streak meteor-near' : 'meteor-streak';
        const length = (near ? between(32, 54) : between(14, 28)) * tailScale;
        meteor.style.width = `${length.toFixed(1)}px`;
        layer.append(meteor);
        const from = -length - width * between(0, .14);
        const to = width + length;
        const y = height * (band + between(-.044, .044));
        const pitch = slope + between(-.021, .021);
        const angle = Math.atan(pitch) * 180 / Math.PI;
        const transform = (x, y) => `translate(${x.toFixed(1)}px,${y.toFixed(1)}px) rotate(${angle.toFixed(1)}deg)`;
        const opacity = near ? between(.89, 1) : between(.53, .72);
        moving.push(meteor.animate([
          {transform: transform(from, y), opacity: 0},
          {opacity: opacity * .78, offset: .16},
          {opacity, offset: between(.27, .40)},
          {opacity: opacity * .72, offset: .50},
          {opacity: opacity * .93, offset: between(.59, .72)},
          {opacity: opacity * .62, offset: .85},
          {transform: transform(to, y + pitch * (to - from)), opacity: 0},
        ], {delay: at + index * between(37, 82) + between(0, 156),
            duration: near ? between(1770, 2450) : between(2510, 3200)}));
      }
    }
    sky.after(layer);
    moving.push(sky.animate([
      {transform: 'none'},
      {transform: 'scale(1.018) translate(.35%,-.22%)', offset: .54},
      {transform: 'none'},
    ], {duration: 6100, easing: 'ease-in-out'}));
    return {animations: moving, stop: () => layer.remove()};
  }
})();

'use strict';

(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const mouse = matchMedia('(hover: hover) and (pointer: fine)');
  const stage = document.getElementById('platforms');
  const animations = new WeakMap();
  const settle = 'cubic-bezier(.2,.7,.2,1)';

  function play(element, frames, duration) {
    animations.get(element)?.cancel();
    animations.set(element, element.animate(frames, {duration, easing: settle}));
  }

  window.AinookPress = button => {
    if (reduced.matches) return;
    window.EaselBurst?.burst(button);
    if (typeof button.animate !== 'function') return;
    const card = button.closest('.quota-card');
    const icon = button.querySelector('.reset-icon');
    const matrix = new DOMMatrixReadOnly(getComputedStyle(icon).transform);
    const angle = (Math.atan2(matrix.b, matrix.a) * 180 / Math.PI + 360) % 360;
    play(icon, [{transform: `rotate(${angle}deg)`}, {transform: 'rotate(360deg)'}], 370);
    play(button.querySelector('.click-plus'), [
      {opacity: 0, transform: 'translate(-50%,0)'},
      {opacity: .95, transform: 'translate(-50%,-12px)', offset: .24},
      {opacity: 0, transform: 'translate(-50%,-32px)'},
    ], 475);
    play(card.querySelector('.wish-count'), [
      {opacity: .65, transform: 'translateY(4px)'}, {opacity: 1, transform: 'none'},
    ], 210);
  };

  let activeCard, spot, pointerX, pointerY, frame;

  function clearSpot() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    if (!activeCard) return;
    activeCard.removeAttribute('data-spotlight');
    activeCard = null;
  }

  stage.addEventListener('pointermove', event => {
    if (event.pointerType !== 'mouse' || !mouse.matches || reduced.matches) return;
    const card = event.target.closest('.quota-card');
    if (!card) return;
    if (card !== activeCard) {
      clearSpot();
      activeCard = card;
      spot = card.querySelector('.card-spotlight');
    }
    pointerX = event.clientX;
    pointerY = event.clientY;
    if (!frame) frame = requestAnimationFrame(() => {
      frame = 0;
      const {left, top, width, height} = activeCard.getBoundingClientRect();
      const x = pointerX - left - width / 2;
      const y = pointerY - top - height * .44;
      spot.style.transform = `translate(${x}px,${y}px) translate(-50%,-50%)`;
      activeCard.toggleAttribute('data-spotlight', true);
    });
  }, {passive: true});

  stage.addEventListener('pointerout', event => {
    if (activeCard && !activeCard.contains(event.relatedTarget)) clearSpot();
  });
  reduced.addEventListener('change', clearSpot);
})();

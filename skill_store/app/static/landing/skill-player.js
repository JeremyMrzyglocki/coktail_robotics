(() => {
  const root = document.getElementById('skill-player');
  if (!root) return;
  const pause = document.getElementById('skill-pause');
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  const cards = [...root.querySelectorAll('.skill-card')].map(el => ({
    el, video: el.querySelector('video'), add: el.querySelector('.skill-add'),
    cursor: el.querySelector('.skill-cursor'), status: el.querySelector('.skill-card-status'),
    time: 0, added: false, playing: false
  }));
  let visible = false, paused = false, last = 0, frame = 0;
  function reset(c) {
    c.video.pause();
    if (c.video.readyState) c.video.currentTime = 0;
    c.time = 0; c.added = false; c.playing = false;
    c.el.classList.remove('is-added', 'is-clicking');
    c.add.querySelector('span').textContent = 'Add';
    c.add.querySelector('use').setAttribute('href', '#plus');
    c.add.setAttribute('aria-label', 'Preview adding ' + c.el.dataset.skillName);
    c.status.textContent = 'Ready';
    c.cursor.style.opacity = '0';
  }
  function play(c) {
    window.loadVideoSource(c.video);
    c.video.play().catch(() => { if (c.video.paused) c.status.textContent = 'Tap to play'; });
  }
  function paint(c) {
    const t = c.time;
    const approach = Math.min(1, Math.max(0, (t - 1000) / 750));
    c.cursor.style.opacity = t >= 1000 && t < 2300 && !reduce.matches ? '1' : '0';
    c.cursor.style.transform = `translate(${(1-approach)*22}px,${(1-approach)*38}px) scale(${t>=1950&&t<2100?.85:1})`;
    c.el.classList.toggle('is-clicking', t >= 1950 && t < 2200);
    if (t >= 2000 && !c.added) {
      c.added = true; c.el.classList.add('is-added');
      c.add.querySelector('span').textContent = 'Added';
      c.add.querySelector('use').setAttribute('href', '#skill-check');
      c.add.setAttribute('aria-label', 'Replay ' + c.el.dataset.skillName + ' preview');
      c.status.textContent = 'Added';
    }
    if (t >= 2500 && !c.playing && !reduce.matches) {
      c.playing = true; c.status.textContent = 'Running';
      if (visible && !paused && !document.hidden) play(c);
    }
  }
  function tick(now) {
    const dt = last ? Math.min(now-last, 100) : 0;
    last = now;
    // Wait for the clip to finish, even if a slow connection delayed playback.
    cards.forEach(c => { c.time += dt; if (c.playing && c.video.ended) reset(c); paint(c); });
    frame = requestAnimationFrame(tick);
  }
  function sync() {
    cancelAnimationFrame(frame); frame = 0; last = 0;
    const run = visible && !paused && !document.hidden && !reduce.matches;
    pause.hidden = reduce.matches;
    pause.setAttribute('aria-label', paused ? 'Play all skill animations' : 'Pause all skill animations');
    pause.querySelector('use').setAttribute('href', paused ? '#play' : '#pause');
    cards.forEach(c => {
      if (run) window.loadVideoSource(c.video);
      if (c.playing) c.status.textContent = paused ? 'Paused' : 'Running';
      if (run && c.playing) play(c); else c.video.pause();
    });
    if (run) frame = requestAnimationFrame(tick);
  }
  cards.forEach(c => {
    reset(c);
    c.add.addEventListener('click', () => {
      if (c.added) reset(c);
      c.time = 2500; paused = false; paint(c); sync();
    });
    c.video.addEventListener('error', () => { c.status.textContent = 'Unavailable'; });
  });
  pause.addEventListener('click', () => { paused = !paused; sync(); });
  new IntersectionObserver(entries => { visible = entries[0].isIntersecting; sync(); }, {threshold:.15}).observe(root);
  document.addEventListener('visibilitychange', sync);
  reduce.addEventListener('change', () => { cards.forEach(reset); sync(); });
})();

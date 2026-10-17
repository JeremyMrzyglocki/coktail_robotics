(() => {
  const mobile = matchMedia('(max-width:760px)');
  const reducedMotion = matchMedia('(prefers-reduced-motion:reduce)');
  const root = document.querySelector('.learning-layout');
  const tabs = [...root.querySelectorAll('[data-layer]')];
  const rows = [...root.querySelectorAll('.layer-row')];
  let active = 0;
  let visible = false;
  let stoppedByUser = false;
  let timer;
  const cycleDuration = 3000;
  function schedule() {
    clearTimeout(timer);
    root.classList.remove('auto-cycling');
    if (!mobile.matches || !visible || document.hidden || reducedMotion.matches || stoppedByUser) return;
    // Restart the visual countdown together with the next automatic step.
    void root.offsetWidth;
    root.classList.add('auto-cycling');
    timer = setTimeout(() => {
      active = (active + 1) % tabs.length;
      update();
    }, cycleDuration);
  }
  function stopForUser() {
    stoppedByUser = true;
    schedule();
  }
  function update() {
    const list = root.querySelector('.layer-rows');
    if (mobile.matches) list.setAttribute('role', 'presentation');
    else list.removeAttribute('role');
    tabs.forEach(tab => {
      const selected = Number(tab.dataset.layer) === active;
      tab.setAttribute('aria-selected', String(selected));
      tab.tabIndex = selected ? 0 : -1;
    });
    rows.forEach(row => {
      const selected = Number(row.dataset.band) === active;
      row.classList.toggle('is-mobile-active', selected);
      row.hidden = mobile.matches && !selected;
      if (mobile.matches) {
        row.setAttribute('role', 'tabpanel');
        row.setAttribute('aria-labelledby', tabs.find(tab => tab.dataset.layer === row.dataset.band).id);
      } else {
        row.removeAttribute('role');
        row.removeAttribute('aria-labelledby');
      }
      if (row.hidden) row.querySelector('video').pause();
    });
    document.dispatchEvent(new CustomEvent('layerchange', {detail: {band: active, mobile: mobile.matches}}));
    schedule();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => { stopForUser(); active = Number(tab.dataset.layer); update(); });
    tab.addEventListener('keydown', event => {
      let next;
      if (event.key === 'ArrowRight') next = (index + 1) % tabs.length;
      if (event.key === 'ArrowLeft') next = (index + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      stopForUser();
      active = Number(tabs[next].dataset.layer);
      update();
      tabs[next].focus();
    });
  });
  root.addEventListener('focusin', stopForUser);
  root.addEventListener('click', event => {
    if (event.target.closest('[data-video]')) stopForUser();
  });
  new IntersectionObserver(entries => {
    visible = entries[0].isIntersecting && entries[0].intersectionRatio >= .45;
    schedule();
  }, {threshold: [0, .45]}).observe(root);
  document.addEventListener('visibilitychange', schedule);
  reducedMotion.addEventListener('change', schedule);
  mobile.addEventListener('change', update);
  update();
})();

/* Shared, route-scoped autoplay for the artwork showcases. */
window.StorefrontShowcase = (() => {
  const instances = new Map();
  const media = window.matchMedia('(prefers-reduced-motion: reduce)');
  const words = (uz, ru, en) => document.documentElement.lang === 'uz' ? uz : document.documentElement.lang === 'ru' ? ru : en;


  function rotation(root, { count, interval, change, pauseLabel, playLabel }) {
    const remove = [];
    let index = 0, timer = null, alive = true, revision = 0;
    let paused = false, hovered = false, focused = false, visible = true;
    const listen = (target, event, handler) => {
      target.addEventListener(event, handler);
      remove.push(() => target.removeEventListener(event, handler));
    };
    function sync() {
      if (timer !== null) window.clearInterval(timer);
      timer = null;
      const playing = alive && count > 1 && !paused && !hovered && !focused && visible && !document.hidden && !media.matches;
      root.dataset.playing = String(playing);
      if (playing) timer = window.setInterval(() => {
        if (!root.isConnected) { destroy(); return; }
        go(index + 1, false);
      }, interval);
    }
    async function go(next, manual = true) {
      if (!alive || !root.isConnected || !count) return;
      index = (next % count + count) % count;
      const request = ++revision;
      const accepted = await change(index, manual);
      if (!alive || request !== revision || accepted === false) return;
      root.dataset.showcaseIndex = String(index);
      if (manual) sync();
    }
    function destroy() {
      if (!alive) return;
      alive = false;
      revision++;
      if (timer !== null) window.clearInterval(timer);
      timer = null;
      remove.splice(0).forEach(fn => fn());
      observer?.disconnect();
      root.dataset.playing = 'false';
    }
    root.tabIndex = 0;
    root.setAttribute('aria-keyshortcuts', 'ArrowLeft ArrowRight Space');
    root.setAttribute('aria-description', words('Avtomatik slaydlar. Chap-o‘ng tugmalar bilan almashtiring, pauza uchun bo‘sh joyni bosing.', 'Автоматическое слайд-шоу. Стрелки переключают слайды, пробел ставит на паузу.', 'Automatic slideshow. Use Left or Right to browse, Space to pause or resume.'));
    listen(root, 'keydown', event => {
      if (event.target !== root) return;
      if (event.key === ' ') { event.preventDefault(); paused = !paused; sync(); }
      else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); go(index + (event.key === 'ArrowRight' ? 1 : -1)); }
    });
    listen(root, 'pointerenter', () => { hovered = true; sync(); });
    listen(root, 'pointerleave', () => { hovered = false; sync(); });
    listen(root, 'focusin', () => { focused = true; sync(); });
    listen(root, 'focusout', event => { focused = root.contains(event.relatedTarget); sync(); });
    listen(document, 'visibilitychange', sync);
    listen(media, 'change', sync);
    const observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
      visible = entries.some(entry => entry.isIntersecting);
      sync();
    }, { threshold: 0.1 }) : null;
    observer?.observe(root);
    root.dataset.enhanced = 'true';
    root.dataset.showcaseIndex = '0';
    sync();
    return { go, next: () => go(index + 1), previous: () => go(index - 1), listen, destroy };
  }

  function gameCarousel(root) {
    if (instances.has(root)) return;
    const stage = root.querySelector('.game-carousel-stage');
    const cards = stage ? [...stage.querySelectorAll('[data-game-card]')] : [];
    if (!cards.length) return;
    const track = document.createElement('div');
    const group = document.createElement('div');
    track.className = 'game-carousel-track';
    group.className = 'game-carousel-group';
    cards.forEach(card => {
      card.classList.add('game-carousel-item');
      card.removeAttribute('aria-hidden');
      card.tabIndex = 0;
    });
    group.append(...cards);
    const copy = group.cloneNode(true);
    copy.dataset.loopCopy = 'true';
    copy.setAttribute('aria-hidden', 'true');
    copy.querySelectorAll('[data-game-card]').forEach(card => {
      card.removeAttribute('data-game-card');
      card.tabIndex = -1;
    });
    track.append(group, copy);
    stage.replaceChildren(track);
    let paused = false, keyboard = false, visible = true, alive = true;
    const remove = [];
    const listen = (target, event, handler) => {
      target.addEventListener(event, handler);
      remove.push(() => target.removeEventListener(event, handler));
    };
    const sync = () => {
      const playing = alive && visible && !paused && !keyboard && !media.matches && !document.hidden;
      // Native keyboard scrolling must not carry an offset into the moving rail.
      if (playing) stage.scrollLeft = 0;
      root.dataset.playing = String(playing);
      root.dataset.keyboard = String(keyboard);
    };
    root.tabIndex = 0;
    root.dataset.enhanced = 'true';
    root.setAttribute('aria-keyshortcuts', 'Space');
    root.setAttribute('aria-description', words('Doimiy aylanuvchi o‘yinlar. Pauza uchun bo‘sh joyni bosing. Klaviatura bilan barcha o‘yinlarni tanlash mumkin.', 'Непрерывная лента игр. Пробел ставит на паузу. Все игры доступны с клавиатуры.', 'Continuously scrolling games. Space pauses the rail. All games are accessible by keyboard.'));
    listen(root, 'keydown', event => {
      if (event.target === root && event.key === ' ') { event.preventDefault(); paused = !paused; sync(); }
    });
    listen(root, 'focusin', event => {
      if (event.target?.matches?.(':focus-visible')) {
        keyboard = true;
        sync();
        // Switching away from the translated track can move the focused card.
        if (event.target !== root) event.target.scrollIntoView({block:'nearest', inline:'nearest', behavior:'instant'});
      }
    });
    listen(root, 'focusout', event => {
      if (!root.contains(event.relatedTarget)) { keyboard = false; sync(); }
    });
    listen(document, 'visibilitychange', sync);
    listen(media, 'change', sync);
    const observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver(entries => {
      visible = entries.some(entry => entry.isIntersecting); sync();
    }, {threshold:0.1}) : null;
    observer?.observe(root);
    sync();
    instances.set(root, {destroy() {
      if (!alive) return;
      alive = false;
      remove.splice(0).forEach(fn => fn());
      observer?.disconnect();
      root.dataset.playing = 'false';
      delete root.dataset.enhanced;
      delete root.dataset.keyboard;
      stage.replaceChildren(...cards);
    }});
  }

  function banner(container) {
    const root = container.querySelector('.home-intro, .market-banner');
    if (!root || instances.has(root)) return;
    const images = [...root.querySelectorAll('.home-intro-image, .market-banner-image')];
    const dots = [...root.querySelectorAll('[data-market-slide]')];
    if (!images.length) return;
    let request = 0, active = true;
    const pending = new WeakMap();
    function load(image) {
      if (pending.has(image)) return pending.get(image);
      if (!image.dataset.src && image.complete) return Promise.resolve(image.naturalWidth > 0);
      const result = new Promise(resolve => {
        const finish = value => { image.removeEventListener('load', loaded); image.removeEventListener('error', failed); resolve(value); };
        const loaded = () => finish(true), failed = () => finish(false);
        image.addEventListener('load', loaded);
        image.addEventListener('error', failed);
        if (image.dataset.src) { image.src = image.dataset.src; delete image.dataset.src; }
      });
      pending.set(image, result);
      return result;
    }
    const controller = rotation(root, {
      count: images.length, interval: 8000,
      pauseLabel: words('Banner almashishini to‘xtatish', 'Остановить слайд-шоу', 'Pause banner slideshow'),
      playLabel: words('Banner almashishini davom ettirish', 'Запустить слайд-шоу', 'Play banner slideshow'),
      change: async index => {
        const current = ++request;
        if (!await load(images[index]) || !active || !root.isConnected || current !== request) return false;
        images.forEach((image, i) => {
          image.classList.toggle('active', i === index);
          image.style.setProperty('--mobile-slide-offset', String((i - index) * 100) + '%');
        });
        dots.forEach((dot, i) => dot.setAttribute('aria-current', String(i === index)));
        if (!media.matches) load(images[(index + 1) % images.length]);
      },
    });
    dots.forEach(dot => controller.listen(dot, 'click', () => controller.go(Number(dot.dataset.marketSlide))));
    let startX = null;
    controller.listen(root, 'touchstart', event => { startX = event.touches.length === 1 ? event.touches[0].clientX : null; });
    controller.listen(root, 'touchend', event => {
      if (startX === null || !event.changedTouches.length) return;
      const delta = event.changedTouches[0].clientX - startX;
      startX = null;
      if (Math.abs(delta) > 45) delta < 0 ? controller.next() : controller.previous();
    });
    const destroy = controller.destroy;
    controller.destroy = () => { active = false; request++; destroy(); };
    instances.set(root, controller);
    load(images[0]).then(ok => { if (ok && active && root.isConnected && !media.matches) load(images[1 % images.length]); });
  }

  function mount(root) {
    banner(root);
    root.querySelectorAll('[data-game-carousel]').forEach(gameCarousel);
  }
  function stop() {
    instances.forEach(controller => controller.destroy());
    instances.clear();
  }
  return { mount, banner, stop };
})();

/* Desktop sharing: a small animated channel fan; no social SDKs or trackers. */
window.DesktopShare = (() => {
  const desktopQuery = '(min-width:841px)';
  const svg = (body, fill = 'none') => `<svg viewBox="0 0 24 24" fill="${fill}" aria-hidden="true" focusable="false">${body}</svg>`;
  // Bootstrap Icons v1.13.1 (MIT); exact SVG paths, see docs/licenses/bootstrap-icons.txt.
  const solid = body => `<svg class="desktop-share-solid" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true" focusable="false">${body}</svg>`;
  const glyphs = {
    close: svg('<path d="m6 6 12 12M6 18 18 6"/>'),
    check: svg('<path d="m5 12 4 4L19 6"/>'),
    copy: solid('<path d="M4.715 6.542 3.343 7.914a3 3 0 1 0 4.243 4.243l1.828-1.829A3 3 0 0 0 8.586 5.5L8 6.086a1 1 0 0 0-.154.199 2 2 0 0 1 .861 3.337L6.88 11.45a2 2 0 1 1-2.83-2.83l.793-.792a4 4 0 0 1-.128-1.287z"/><path d="M6.586 4.672A3 3 0 0 0 7.414 9.5l.775-.776a2 2 0 0 1-.896-3.346L9.12 3.55a2 2 0 1 1 2.83 2.83l-.793.792c.112.42.155.855.128 1.287l1.372-1.372a3 3 0 1 0-4.243-4.243z"/>'),
    email: solid('<path d="M.05 3.555A2 2 0 0 1 2 2h12a2 2 0 0 1 1.95 1.555L8 8.414zM0 4.697v7.104l5.803-3.558zM6.761 8.83l-6.57 4.027A2 2 0 0 0 2 14h12a2 2 0 0 0 1.808-1.144l-6.57-4.027L8 9.586zm3.436-.586L16 11.801V4.697z"/>'),
    whatsapp: solid('<path d="M13.601 2.326A7.85 7.85 0 0 0 7.994 0C3.627 0 .068 3.558.064 7.926c0 1.399.366 2.76 1.057 3.965L0 16l4.204-1.102a7.9 7.9 0 0 0 3.79.965h.004c4.368 0 7.926-3.558 7.93-7.93A7.9 7.9 0 0 0 13.6 2.326zM7.994 14.521a6.6 6.6 0 0 1-3.356-.92l-.24-.144-2.494.654.666-2.433-.156-.251a6.56 6.56 0 0 1-1.007-3.505c0-3.626 2.957-6.584 6.591-6.584a6.56 6.56 0 0 1 4.66 1.931 6.56 6.56 0 0 1 1.928 4.66c-.004 3.639-2.961 6.592-6.592 6.592m3.615-4.934c-.197-.099-1.17-.578-1.353-.646-.182-.065-.315-.099-.445.099-.133.197-.513.646-.627.775-.114.133-.232.148-.43.05-.197-.1-.836-.308-1.592-.985-.59-.525-.985-1.175-1.103-1.372-.114-.198-.011-.304.088-.403.087-.088.197-.232.296-.346.1-.114.133-.198.198-.33.065-.134.034-.248-.015-.347-.05-.099-.445-1.076-.612-1.47-.16-.389-.323-.335-.445-.34-.114-.007-.247-.007-.38-.007a.73.73 0 0 0-.529.247c-.182.198-.691.677-.691 1.654s.71 1.916.81 2.049c.098.133 1.394 2.132 3.383 2.992.47.205.84.326 1.129.418.475.152.904.129 1.246.08.38-.058 1.171-.48 1.338-.943.164-.464.164-.86.114-.943-.049-.084-.182-.133-.38-.232"/>'),
    linkedin: solid('<path d="M0 1.146C0 .513.526 0 1.175 0h13.65C15.474 0 16 .513 16 1.146v13.708c0 .633-.526 1.146-1.175 1.146H1.175C.526 16 0 15.487 0 14.854zm4.943 12.248V6.169H2.542v7.225zm-1.2-8.212c.837 0 1.358-.554 1.358-1.248-.015-.709-.52-1.248-1.342-1.248S2.4 3.226 2.4 3.934c0 .694.521 1.248 1.327 1.248zm4.908 8.212V9.359c0-.216.016-.432.08-.586.173-.431.568-.878 1.232-.878.869 0 1.216.662 1.216 1.634v3.865h2.401V9.25c0-2.22-1.184-3.252-2.764-3.252-1.274 0-1.845.7-2.165 1.193v.025h-.016l.016-.025V6.169h-2.4c.03.678 0 7.225 0 7.225z"/>'),
    x: solid('<path d="M12.6.75h2.454l-5.36 6.142L16 15.25h-4.937l-3.867-5.07-4.425 5.07H.316l5.733-6.57L0 .75h5.063l3.495 4.633L12.601.75Zm-.86 13.028h1.36L4.323 2.145H2.865z"/>')
  };
  const text = (uz, ru, en) => typeof adminText === 'function' ? adminText(uz, ru, en) : en;
  let active;

  function links(url, title) {
    const address = new URL(url);
    if (!['http:', 'https:'].includes(address.protocol) || address.username || address.password) throw new Error('Invalid share URL');
    const clean = address.href, message = `${title}\n${clean}`;
    return {
      x: 'https://twitter.com/intent/tweet?' + new URLSearchParams({text: title, url: clean}),
      linkedin: 'https://www.linkedin.com/sharing/share-offsite/?' + new URLSearchParams({url: clean}),
      whatsapp: 'https://wa.me/?' + new URLSearchParams({text: message}),
      email: 'mailto:?' + new URLSearchParams({subject: title, body: message}).toString().replaceAll('+', '%20')
    };
  }

  function open({anchor, title = document.title, url = location.href} = {}) {
    const media = matchMedia(desktopQuery);
    if (!media.matches) return false;
    const destinations = links(url, title);
    active?.destroy(false);
    const dialog = document.createElement('dialog');
    dialog.className = 'desktop-share-dialog';
    dialog.setAttribute('aria-labelledby', 'desktop-share-title');
    dialog.setAttribute('aria-describedby', 'desktop-share-product');
    dialog.dataset.phase = 'fan';
    dialog.innerHTML = `<div class="desktop-share-card">
      <header><span class="desktop-share-eyebrow">Sentry<span>Loot</span></span><h2 id="desktop-share-title"></h2><p id="desktop-share-product" data-user-content></p></header>
      <div class="desktop-share-stage">
        <div class="desktop-share-channels"></div>
        <button type="button" class="desktop-share-center" autofocus>${glyphs.close}<span class="desktop-share-feedback-glyph"></span></button>
        <p class="desktop-share-status" role="status" aria-live="polite" aria-atomic="true"></p>
      </div>
      <div class="desktop-share-manual" hidden><label for="desktop-share-url"></label><input id="desktop-share-url" type="text" readonly></div>
    </div>`;
    dialog.querySelector('h2').textContent = text('Ulashish', 'Поделиться', 'Share this offer');
    dialog.querySelector('#desktop-share-product').textContent = title;
    const stage = dialog.querySelector('.desktop-share-channels');
    const center = dialog.querySelector('.desktop-share-center');
    const feedback = dialog.querySelector('.desktop-share-feedback-glyph');
    const status = dialog.querySelector('.desktop-share-status');
    const manual = dialog.querySelector('.desktop-share-manual');
    const closeLabel = text('Ulashishni yopish', 'Закрыть окно', 'Close sharing');
    const pickLabel = text('Qayerga ulashishni tanlang', 'Выберите, где поделиться', 'Pick a channel');
    center.setAttribute('aria-label', closeLabel);
    status.textContent = pickLabel;
    let closing = false, disposed = false;
    const timers = new Set();
    const later = (fn, ms) => {const timer = setTimeout(() => {timers.delete(timer); if (!disposed) fn();}, ms); timers.add(timer);};
    const clearTimers = () => {timers.forEach(clearTimeout);timers.clear();};
    const channels = [
      ['x', 'X', -124, 0], ['linkedin', 'LinkedIn', -88, -88],
      ['whatsapp', 'WhatsApp', 0, -124], ['email', text('Email', 'Почта', 'Email'), 88, -88],
      ['copy', text('Havolani nusxalash', 'Копировать ссылку', 'Copy link'), 124, 0]
    ];
    function reset() {
      clearTimers(); dialog.dataset.phase = 'fan'; delete dialog.dataset.channel;
      stage.removeAttribute('inert'); status.textContent = pickLabel;
      manual.hidden = true; center.setAttribute('aria-label', closeLabel);
    }
    function select(key, message) {
      clearTimers(); dialog.dataset.channel = key; dialog.dataset.phase = 'selected';
      stage.setAttribute('inert', ''); feedback.innerHTML = glyphs[key];
      center.focus({preventScroll: true}); status.textContent = message;
    }
    async function copy() {
      // Start inside the actual user gesture (especially important in Safari).
      let operation;
      try {operation = navigator.clipboard?.writeText(url);}
      catch (_) {operation = Promise.reject(new Error('Clipboard unavailable'));}
      select('copy', text('Havola nusxalanmoqda…', 'Копирование…', 'Copying link…'));
      try {
        if (!operation) throw new Error('Clipboard unavailable');
        await operation;
        if (disposed || closing) return;
        status.textContent = text('Havola nusxalandi', 'Ссылка скопирована', 'Link copied');
        later(() => {dialog.dataset.phase = 'copied'; feedback.innerHTML = glyphs.check;}, 240);
        later(close, 1600);
      } catch (_) {
        if (disposed || closing) return;
        // Never show a false success if clipboard permission is denied.
        dialog.dataset.phase = 'manual';
        status.textContent = text('Havolani qo‘lda nusxalang', 'Скопируйте ссылку вручную', 'Copy the link below');
        manual.hidden = false;
        manual.querySelector('label').textContent = text('Nusxalash uchun Ctrl+C yoki ⌘C bosing', 'Нажмите Ctrl+C или ⌘C', 'Press Ctrl+C or ⌘C to copy');
        const field = manual.querySelector('input'); field.value = url; field.focus(); field.select();
      }
    }
    channels.forEach(([key, label, x, y], index) => {
      const control = document.createElement(key === 'copy' ? 'button' : 'a');
      control.className = 'desktop-share-channel'; control.dataset.channel = key;
      control.style.setProperty('--share-x', `${x}px`);control.style.setProperty('--share-y', `${y}px`);
      control.style.setProperty('--share-delay', `${index * 35}ms`);
      control.setAttribute('aria-label', label); control.innerHTML = `${glyphs[key]}<span class="desktop-share-tooltip"></span>`;
      control.querySelector('span').textContent = label;
      if (key === 'copy') {control.type = 'button';control.addEventListener('click', copy);}
      else {
        control.href = destinations[key];
        if (key !== 'email') {control.target = '_blank';control.rel = 'noopener noreferrer';}
        control.addEventListener('click', () => {
          select(key, text(`${label} ochilmoqda…`, `Открываем ${label}…`, `Opening ${label}…`));
          later(reset, 1700);
        });
      }
      stage.append(control);
    });
    function destroy(restoreFocus = true) {
      if (disposed) return;
      disposed = true; clearTimers();
      window.removeEventListener('hashchange', close);window.removeEventListener('popstate', close);
      media.removeEventListener('change', resize);
      if (dialog.open) dialog.close(); dialog.remove();
      if (active?.dialog === dialog) active = null;
      anchor?.setAttribute('aria-expanded', 'false');
      if (restoreFocus && anchor?.isConnected) anchor.focus({preventScroll: true});
    }
    function close() {
      if (closing || disposed) return;
      closing = true; clearTimers(); dialog.classList.remove('is-open');
      later(destroy, matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 180);
    }
    function resize() {if (!media.matches) destroy();}
    center.addEventListener('click', close);
    dialog.addEventListener('cancel', event => {event.preventDefault();close();});
    dialog.addEventListener('close', () => destroy());
    dialog.addEventListener('click', event => {if (event.target === dialog) close();});
    window.addEventListener('hashchange', close);window.addEventListener('popstate', close);
    media.addEventListener('change', resize);
    document.body.append(dialog);dialog.showModal();
    anchor?.setAttribute('aria-haspopup', 'dialog');anchor?.setAttribute('aria-expanded', 'true');
    active = {dialog, destroy};
    requestAnimationFrame(() => requestAnimationFrame(() => {if (!closing && !disposed) dialog.classList.add('is-open');}));
    return true;
  }
  return {open, links};
})();

/* Mobile navigation reuses the desktop routes and session; no extra API calls. */
window.MobileHeader = (() => {
  let initialized = false;
  const mobile = () => window.matchMedia('(max-width:840px)').matches;
  const t = (uz, ru, en) => adminText(uz, ru, en);
  function syncLabels() {
    const toggle = document.getElementById('mobile-menu-toggle');
    if (!toggle) return;
    toggle.setAttribute('aria-label', t('Menyuni ochish', 'Открыть меню', 'Open menu'));
    const title = document.getElementById('mobile-menu-title');
    const label = t('Menyu', 'Меню', 'Menu');
    if (title.textContent !== label) title.textContent = label;
    document.querySelector('[data-mobile-menu-close]').setAttribute('aria-label', t('Menyuni yopish', 'Закрыть меню', 'Close menu'));
    const search = document.getElementById('mobile-search-toggle');
    search?.setAttribute('aria-label', document.querySelector('.site-header').classList.contains('mobile-search-open') ? t('Qidiruvni yopish', 'Закрыть поиск', 'Close search') : t('Qidirish', 'Поиск', 'Open search'));
  }
  function init() {
    if (initialized) return;
    const toggle = document.getElementById('mobile-menu-toggle');
    const dialog = document.getElementById('mobile-navigation');
    if (!toggle || !dialog) return;
    initialized = true;
    const content = dialog.querySelector('[data-mobile-menu-content]');
    const close = () => { if (dialog.open) dialog.close(); };
    const header = document.querySelector('.site-header');
    const searchToggle = document.getElementById('mobile-search-toggle');
    const searchInput = document.getElementById('global-search');
    function setSearch(open, focus = false) {
      header.classList.toggle('mobile-search-open', open);
      searchToggle.setAttribute('aria-expanded', String(open));
      syncLabels();
      if (focus) (open ? searchInput : searchToggle).focus({preventScroll: true});
    }
    searchToggle.addEventListener('click', () => setSearch(!header.classList.contains('mobile-search-open'), true));
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && mobile() && header.classList.contains('mobile-search-open')) { event.preventDefault(); setSearch(false, true); }
    });
    document.addEventListener('pointerdown', event => {
      if (mobile() && !header.contains(event.target)) setSearch(false);
    });
    function open() {
      if (!mobile() || dialog.open) return;
      closeProfileMenu();
      closeLanguageMenu();
      setSearch(false);
      const filters = location.pathname === '/browse' ? browseFilters(location.search) : {};
      content.innerHTML = `${me ? `<a class="mobile-menu-profile" href="/#account">${marketAvatarMarkup(me.display_name || me.email, me.avatar_url, 'account-avatar', me.id)}<span><b>${esc(me.display_name)}</b><small>${t('Hisob sozlamalari', 'Настройки аккаунта', 'Account settings')}</small></span>${icon('arrow-up-right')}</a>` : ''}` + marketSidebarMarkup(filters, {mobile: true}) + `
        <footer class="mobile-menu-footer">
          <a class="mobile-menu-sell" href="/#seller">${icon('plus')}<span>${t('E’lon joylash', 'Продать товар', 'Sell item')}</span>${icon('arrow-up-right')}</a>
          <div class="mobile-menu-language" role="group" aria-label="${t('Til', 'Язык', 'Language')}">
            <span>${icon('globe')}<span>${t('Til', 'Язык', 'Language')}</span></span>
            <div>${[['en', 'EN', 'English'], ['uz', 'UZ', 'O‘zbekcha'], ['ru', 'RU', 'Русский']].map(([value, label, name]) => `<button type="button" data-mobile-language="${value}" aria-label="${name}" aria-pressed="${locale === value}">${label}</button>`).join('')}</div>
          </div>
          <button type="button" class="mobile-menu-account-action" data-mobile-region>${icon('globe')}<span>${t('Region va valyuta', 'Регион и валюта', 'Region & currency')}</span></button>
          ${me?.is_admin ? `<a class="mobile-menu-admin" href="/#admin">${icon('shield')}<span>${t('Admin paneli', 'Панель администратора', 'Admin panel')}</span>${icon('arrow-up-right')}</a>` : ''}
          ${me?.email_verified ? `<button type="button" class="mobile-menu-account-action" data-mobile-action data-action="link-facebook"><span class="market-nav-icon" aria-hidden="true"><span class="facebook-mark">f</span></span><span>${t('Facebook’ni ulash', 'Подключить Facebook', 'Link Facebook')}</span></button>` : ''}
          <div class="mobile-menu-account-actions"><button type="button" data-open-support-chat><span class="market-nav-icon" aria-hidden="true">${icon('message')}</span><span>${t('Yordam', 'Поддержка', 'Support')}</span></button>${me ? `<button type="button" class="mobile-menu-sign-out" data-mobile-action data-action="logout"><span class="market-nav-icon" aria-hidden="true">${icon('arrow-up-right')}</span><span>${t('Chiqish', 'Выйти', 'Sign out')}</span></button>` : ''}</div>
        </footer>`;
      syncLabels();
      dialog.showModal();
      dialog.scrollTop = 0;
      content.scrollTop = 0;
      toggle.setAttribute('aria-expanded', 'true');
      document.documentElement.classList.add('mobile-menu-open');
      dialog.querySelector('[data-mobile-menu-close]').focus({preventScroll: true});
    }
    toggle.addEventListener('click', open);
    dialog.querySelector('[data-mobile-menu-close]').addEventListener('click', close);
    dialog.addEventListener('close', () => {
      toggle.setAttribute('aria-expanded', 'false');
      document.documentElement.classList.remove('mobile-menu-open');
    });
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('click', event => {
      if (event.target === dialog) {
        const rect = dialog.getBoundingClientRect();
        if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
      }
      if (event.target.closest('a[href]')) close();
      if (event.target.closest('[data-open-support-chat]')) close();
      const action = event.target.closest('[data-mobile-action]');
      if (action) { close(); doAction(action); }
      if (event.target.closest('[data-mobile-region]')) { close(); window.RegionPreferences?.open(); }
      const language = event.target.closest('[data-mobile-language]');
      if (language) { close(); setLanguage(language.dataset.mobileLanguage); }
    });
    window.matchMedia('(max-width:840px)').addEventListener('change', () => { close(); setSearch(false); });
    window.addEventListener('hashchange', () => { close(); setSearch(false); });
    window.addEventListener('popstate', () => { close(); setSearch(false); });
    syncLabels();
  }
  return {init, syncLabels};
})();

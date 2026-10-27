/* The approved phone design uses the existing authenticated routes and forms. */
window.MobileSite = (() => {
  const query = '(max-width:840px)';
  const isMobile = () => matchMedia(query).matches;
  const t = (uz, ru, en) => adminText(uz, ru, en);
  // These paths are the exact icons in the approved phone simulator.
  const designPaths = {
    "gamepad": "<path d=\"M6 7h12c3 0 5 12 2 12-2 0-3-4-5-4H9c-2 0-3 4-5 4-3 0-1-12 2-12ZM6 10v4M4 12h4M15 11h.01M18 13h.01\"/>",
    "close": "<path d=\"m6 6 12 12M6 18 18 6\"/>",
    "clock": "<circle cx=\"12\" cy=\"12\" r=\"9\"/><path d=\"M12 7v5l3 2\"/>",
    "shield": "<path d=\"m12 2 8 3v6c0 5-5 9-8 11-3-2-8-6-8-11V5l8-3Z\"/><path d=\"m8 11 3 3 5-5\"/>",
    "facebook": "<path d=\"M15 22V13h3l1-4h-4V6c0-1 1-2 2-2h2V1h-3c-4 0-5 2-5 5v3H8v4h3v9\"/>",
    "phone": "<rect x=\"6\" y=\"2\" width=\"12\" height=\"20\" rx=\"2\"/><path d=\"M11 18h2\"/>",
    "globe": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"M2 12h20M12 2a20 20 0 0 1 0 20 20 20 0 0 1 0-20Z\"/>",
    "lock": "<rect x=\"4\" y=\"10\" width=\"16\" height=\"12\" rx=\"2\"/><path d=\"M7 10V6a5 5 0 0 1 10 0v4M12 15v3\"/>",
    "mail": "<rect x=\"3\" y=\"5\" width=\"18\" height=\"14\" rx=\"2\"/><path d=\"m3 6 9 7 9-7\"/>",
    "box": "<path d=\"m12 2 9 5v10l-9 5-9-5V7l9-5ZM3 7l9 5 9-5M12 12v10M7 4.5l9 5\"/>",
    "coins": "<ellipse cx=\"15\" cy=\"5\" rx=\"6\" ry=\"3\"/><path d=\"M9 5v8c0 4 12 4 12 0V5M9 9c0 4 12 4 12 0\"/><ellipse cx=\"7\" cy=\"13\" rx=\"5\" ry=\"3\"/><path d=\"M2 13v6c0 4 10 4 10 0v-6\"/>",
    "chat": "<path d=\"M21 15a3 3 0 0 1-3 3H8l-5 4V5a3 3 0 0 1 3-3h12a3 3 0 0 1 3 3v10Z\"/><path d=\"M7 8h10M7 12h7\"/>",
    "user": "<circle cx=\"12\" cy=\"7\" r=\"4\"/><path d=\"M4 22v-3a8 8 0 0 1 16 0v3\"/>",
    "document": "<path d=\"M14 2H4v20h16V8l-6-6ZM14 2v6h6M8 13h8M8 17h6\"/>",
    "heart": "<path d=\"M20 4c-3-2-6-1-8 2-2-3-5-4-8-2-7 5 3 12 8 17 5-5 15-12 8-17Z\"/>",
    "star": "<path d=\"m12 2 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1 3-6Z\"/>",
    "search": "<circle cx=\"10.5\" cy=\"10.5\" r=\"6.5\"/><path d=\"m16 16 5 5\"/>",
    "settings": "<path d=\"m9 2-1 3-3 1-3 3 2 3-2 3 3 3 3 1 1 3h6l1-3 3-1 3-3-2-3 2-3-3-3-3-1-1-3H9Z\"/><circle cx=\"12\" cy=\"12\" r=\"4\"/>",
    "help": "<circle cx=\"12\" cy=\"12\" r=\"10\"/><path d=\"M9 8c0-4 6-4 6 0 0 3-3 2-3 6M12 18h.01\"/>",
    "logout": "<path d=\"M9 3H3v18h6M10 12h12m-5-5 5 5-5 5\"/>",
    "cart": "<path d=\"M2 3h3l3 12h11l2-9H6M9 20h.01M18 20h.01\"/>",
    "bell": "<path d=\"M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4\"/>",
    "right": "<path d=\"m9 5 7 7-7 7\"/>",
    "arrow": "<path d=\"M4 12h16m-6-6 6 6-6 6\"/>",
    "truck": "<path d=\"M1 4h13v13H1V4ZM14 9h5l4 5v3h-9M5 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm14 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z\"/>",
    "wallet": "<path d=\"M3 7V4l15-3v6M3 7h18v15H3V7ZM16 12h5v6h-5v-6Z\"/><path d=\"M18 15h.01\"/>",
    "menu": "<path d=\"M3 6h18M3 12h18M3 18h18\"/>",
    "filter": "<path d=\"M3 6h18M6 12h12M9 18h6\"/>",
    "check": "<path d=\"m5 12 4 4L19 6\"/>",
    "home": "<path d=\"m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1V10Z\"/>"
};
  const designIcon = name => `<svg class="mobile-design-icon" viewBox="0 0 24 24" aria-hidden="true">${designPaths[name] || designPaths.document}</svg>`;
  const key = 'sentryloot-mobile-welcome:v1';
  let initialized = false, currentRoute = '', scheduled = false, observer;
  let sessionResolved = false, introComplete = false, introEligible = false;
  let introTimers = [], initialUrl = '', restoreIntro = () => {};

  function routeFromLocation() {
    if (location.hash && !currentPageAnchor()) return location.hash.slice(1);
    const path = location.pathname.replace(/^\/+|\/+$/g, '');
    return path || 'home';
  }
  function navHidden() {
    // Main navigation now lives in the header menu on mobile.
    return true;
  }
  function navKey(route) {
    if (route === 'home') return 'home';
    if (/^top-up(?:\/|$)/.test(route)) return 'topup';
    if (/^(?:messages|conversation\/)/.test(route)) return 'messages';
    if (/^(?:browse|games\/|store\/|compare)/.test(route)) return 'browse';
    return 'account';
  }
  function syncNavigation(route = routeFromLocation()) {
    const mobile = isMobile();
    document.body.classList.toggle('mobile-site', mobile);
    document.body.dataset.mobileRoute = route;
    const hidden = !mobile || navHidden(route);
    document.body.classList.toggle('mobile-has-dock', !hidden);
    document.body.classList.toggle('mobile-context-auth', /^(?:login|register|check-email|password-reset|verify\/|security-unlock|contact-details|email-change\/)/.test(route));
    document.body.classList.toggle('mobile-context-admin', /^(?:admin|top-up-admin|review-moderation|order-case|catalog-readiness|launch-settings|staff|stripe-test)/.test(route));
    document.querySelector('.ux-mobile-nav')?.remove();
  }

  function accountRow(glyph, label, href) {
    return `<a class="mobile-account-row" href="${href}">${designIcon(glyph)}<span>${esc(label)}</span>${designIcon('right')}</a>`;
  }
  async function account() {
    if (!me) { location.hash = 'login'; return; }
    const name = me.display_name || me.email;
    app.innerHTML = `<section class="page mobile-account-hub">
      <h1>${t('Hisobingiz', 'Ваш аккаунт', 'Your account')}</h1>
      <div class="mobile-account-person">${marketAvatarMarkup(name, me.avatar_url, 'mobile-account-avatar', me.id)}<div><h2>${esc(name)}</h2><p>${esc(me.email)}</p><small class="${me.email_verified ? 'is-verified' : ''}">${me.email_verified ? designIcon('check') : ''}${t(me.email_verified ? 'Email tasdiqlangan' : 'Emailni tasdiqlang', me.email_verified ? 'Email подтверждён' : 'Подтвердите email', me.email_verified ? 'Email verified' : 'Verify your email')}</small></div></div>
      <nav aria-label="${t('Xaridlar va hisob', 'Покупки и аккаунт', 'Purchases and account')}">
        ${accountRow('document', t('Xaridlar', 'Покупки', 'Purchases'), '/#orders')}
        ${accountRow('heart', t('Saqlangan e’lonlar', 'Избранные объявления', 'Saved listings'), '/#favorites')}
        ${accountRow('star', t('Sharhlarim', 'Мои отзывы', 'My reviews'), '/#my-reviews')}
        ${accountRow('search', t('Saqlangan qidiruvlar', 'Сохранённые поиски', 'Saved searches'), '/#saved-searches')}
      </nav>
      <a class="button-primary mobile-account-sell" href="/#seller">${t('E’lon joylash', 'Продать товар', 'Sell item')}${designIcon('arrow')}</a>
      <nav class="mobile-account-secondary" aria-label="${t('Sozlamalar va yordam', 'Настройки и помощь', 'Settings and help')}">
        ${accountRow('settings', t('Hisob sozlamalari', 'Настройки аккаунта', 'Account settings'), '/#account/settings')}
        ${accountRow('help', t('Yordam markazi', 'Центр помощи', 'Help center'), '/support')}
        <button class="mobile-account-row mobile-account-signout" type="button" data-action="logout">${designIcon('logout')}<span>${t('Chiqish', 'Выйти', 'Sign out')}</span>${designIcon('right')}</button>
      </nav>
    </section>`;
  }
  async function menu() {
    if(!me){location.hash='login';return;}
    const name=me.display_name||me.email;
    app.innerHTML=`<section class="page mobile-menu-page"><header class="mobile-menu-profile">${marketAvatarMarkup(name,me.avatar_url,'mobile-menu-avatar',me.id)}<div><h3 title="${esc(name)}">${esc(name)}</h3><p>${esc(maskVerificationEmail(me.email))}</p><a href="/#account/settings">${t('Hisob sozlamalari','Настройки аккаунта','Account settings')} →</a></div></header><nav class="mobile-menu-links" aria-label="${t('Marketplace va hisob','Маркетплейс и аккаунт','Marketplace and account')}">${accountRow('box','Marketplace','/browse')}${accountRow('coins','Top Up','/top-up')}${accountRow('document',t('Xaridlar','Покупки','Purchases'),'/#orders')}${accountRow('heart',t('Saqlangan e’lonlar','Избранное','Saved listings'),'/#favorites')}${accountRow('chat',t('Xabarlar','Сообщения','Messages'),'/#messages')}${accountRow('star',t('Sharhlarim','Мои отзывы','My reviews'),'/#my-reviews')}${accountRow('search',t('Saqlangan qidiruvlar','Сохранённые поиски','Saved searches'),'/#saved-searches')}${accountRow('help',t('So‘rovlar','Запросы','Requests'),'/#requests')}</nav><p class="mobile-menu-group">${t('SOTISH','ПРОДАЖА','SELLING')}</p><a class="mobile-menu-sell" href="/#seller">${t('E’lon joylash','Продать товар','Sell item')}${designIcon('arrow')}</a><p class="mobile-menu-group">${t('HISOB VA YORDAM','АККАУНТ И ПОМОЩЬ','ACCOUNT & HELP')}</p><nav aria-label="${t('Sozlamalar va yordam','Настройки и помощь','Settings and help')}">${accountRow('bell',t('Bildirishnoma sozlamalari','Настройки уведомлений','Notification settings'),'/#notification-settings')}<button class="mobile-account-row" type="button" data-action="link-facebook">${designIcon('facebook')}<span>${t(me.facebook_linked?'Facebook ulangan':'Facebook’ni ulash',me.facebook_linked?'Facebook подключён':'Подключить Facebook',me.facebook_linked?'Facebook linked':'Link Facebook')}</span>${designIcon('right')}</button>${accountRow('help',t('Yordam markazi','Центр помощи','Help center'),'/support')}${me.is_admin?accountRow('shield',t('Admin panel','Панель администратора','Admin console'),'/#admin'):''}</nav><div class="mobile-menu-language"><span>${t('Til','Язык','Language')}</span><div role="group" aria-label="${t('Sayt tili','Язык сайта','Site language')}">${['en','uz','ru'].map(code=>`<button type="button" data-mobile-site-language="${code}" aria-pressed="${locale===code}">${code.toUpperCase()}</button>`).join('')}</div></div><button class="mobile-account-row mobile-menu-signout" type="button" data-action="logout">${designIcon('logout')}<span>${t('Chiqish','Выйти','Sign out')}</span></button></section>`;
  }
  let searchCatalogPromise=null;
  const searchKey=value=>String(value||'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu,' ').trim();
  function matchingSearchGames(games,query='') {
    const words=searchKey(query).split(' ').filter(Boolean),order=['pubg-mobile','mobile-legends','valorant','free-fire'];
    const rank=game=>order.includes(game.slug||game.id)?order.indexOf(game.slug||game.id):order.length;
    return games.filter(game=>words.every(word=>searchKey([game.name,game.slug||game.id,...(game.aliases||[])].join(' ')).includes(word))).sort((a,b)=>rank(a)-rank(b)||a.name.localeCompare(b.name));
  }
  async function search() {
    let games=marketGameLinks.map(row=>({slug:row[0],name:row[1],image_url:row[2],supported_categories:[]}));
    const categoryNames={accounts:()=>t('Akkauntlar','Аккаунты','Accounts'),currency:()=>t('Valyuta','Валюта','Currency'),items:()=>t('Buyumlar','Предметы','Items'),services:()=>t('Xizmatlar','Услуги','Services'),codes:()=>t('Sovg‘a kartalari','Подарочные карты','Gift cards'),'top-ups':()=>t('To‘ldirish','Пополнения','Top-ups'),digital:()=>t('Raqamli mahsulotlar','Цифровые товары','Digital products')};
    const renderRows=rows=>rows.map(game=>{
      const slug=game.slug||game.id,types=Object.keys(categoryNames).filter(type=>(game.supported_categories||[]).includes(type)).slice(0,3).map(type=>categoryNames[type]()).join(' · '),image=game.image_url||marketGameLinks.find(row=>row[0]===slug)?.[2];
      return `<a class="mobile-search-game" href="/browse?game=${encodeURIComponent(slug)}"><span class="market-game-mark mobile-search-art" aria-hidden="true"><span>${esc(game.name.split(/\s+/).map(word=>word[0]).slice(0,2).join(''))}</span>${image?`<img src="${esc(image)}" alt="" width="47" height="47" loading="lazy" decoding="async">`:''}</span><span>${esc(game.name)}${types?`<small>${esc(types)}</small>`:''}</span>${designIcon('right')}</a>`;
    }).join('');
    app.innerHTML=`<section class="page mobile-search-page"><form class="mobile-catalog-search" role="search">${designIcon('search')}<input type="search" name="q" autocomplete="off" placeholder="${t('O‘yin yoki mahsulot qidirish…','Поиск игр и товаров…','Search games or products…')}" aria-label="${t('Qidirish','Поиск','Search')}"><button type="submit" class="sr-only">${t('Qidirish','Поиск','Search')}</button></form><h2>${t('Mashhur qidiruvlar','Популярные запросы','Popular searches')}</h2><nav class="mobile-category-chips">${['PUBG Mobile','Valorant','FC Mobile'].map(name=>`<a href="/browse?q=${encodeURIComponent(name)}">${esc(name)}</a>`).join('')}</nav><section class="mobile-search-results"><h2>${t('O‘yinlar','Игры','Games')}</h2><div data-mobile-search-results>${renderRows(matchingSearchGames(games).slice(0,4))}</div><p class="mobile-search-empty" role="status" hidden>${t('O‘yin topilmadi.','Игры не найдены.','No games found.')}</p></section><section class="mobile-search-results" data-mobile-search-offers hidden><h2>${t('E’lonlar','Предложения','Listings')}</h2><div></div></section><p class="mobile-search-feedback" role="status" hidden></p></section>`;
    const page=app.querySelector('.mobile-search-page'),form=page.querySelector('form'),input=form.querySelector('input'),host=page.querySelector('[data-mobile-search-results]'),empty=page.querySelector('.mobile-search-empty'),offers=page.querySelector('[data-mobile-search-offers]'),feedback=page.querySelector('.mobile-search-feedback');let timer;
    const draw=rows=>{host.innerHTML=renderRows(rows);empty.hidden=rows.length>0;host.querySelectorAll('img').forEach(img=>img.addEventListener('error',()=>img.remove(),{once:true}));};
    if(!searchCatalogPromise)searchCatalogPromise=api('/seller/catalog').catch(()=>{searchCatalogPromise=null;return [];});
    searchCatalogPromise.then(catalog=>{if(!page.isConnected||!Array.isArray(catalog)||!catalog.length)return;games=catalog;draw(matchingSearchGames(games,input.value.trim()).slice(0,input.value.trim()?8:4));});
    form.onsubmit=event=>{event.preventDefault();const value=input.value.trim();history.pushState({},'','/browse'+(value?'?q='+encodeURIComponent(value):''));navigate();};
    input.oninput=()=>{clearTimeout(timer);feedback.hidden=true;offers.hidden=true;const value=input.value.trim();draw(matchingSearchGames(games,value).slice(0,value?8:4));if(value.length<2)return;
      timer=setTimeout(async()=>{
        try{const result=await api('/search/suggestions?q='+encodeURIComponent(value));if(!page.isConnected||input.value.trim()!==value)return;
          const rows=matchingSearchGames(games,value).slice(0,8);for(const game of result.games||[])if(!rows.some(row=>(row.slug||row.id)===game.slug))rows.push(games.find(row=>(row.slug||row.id)===game.slug)||game);draw(rows.slice(0,8));
          const items=result.items||[];offers.hidden=!items.length;offers.querySelector('div').innerHTML=items.map(item=>`<a class="mobile-search-listing" href="/listing/${encodeURIComponent(item.id)}">${designIcon('box')}<span>${esc(item.title)}<small>${esc(fmt(item.price_minor,item.currency))}</small></span>${designIcon('right')}</a>`).join('');
        }catch{if(!page.isConnected||input.value.trim()!==value)return;feedback.textContent=t('Mahsulotlarni yuklab bo‘lmadi. Enter bosib barcha natijalarni qidiring.','Не удалось загрузить товары. Нажмите Enter для поиска всех результатов.','Could not load listings. Press Enter to search all results.');feedback.hidden=false;}
      },180);
    };
  }
  function finishIntroNavigation() {
    if (!introEligible || !introComplete || !sessionResolved) return;
    introEligible = false;
    // Preserve authenticated sessions, email links, payment returns and deep links.
    if (!me && location.href === initialUrl && isMobile()) location.hash = 'login';
  }
  function sessionReady() {
    sessionResolved = true;
    syncNavigation();
    finishIntroNavigation();
  }
  function showIntro() {
    // Never delay normal visits; the animation is available only by explicit preview.
    if (!isMobile() || location.pathname !== '/' || !['', '#home'].includes(location.hash) || new URLSearchParams(location.search).get('intro') !== '1') return;
    try { if (sessionStorage.getItem(key)) return; sessionStorage.setItem(key, '1'); } catch {}
    initialUrl = location.href;
    introEligible = true;
    const overlay = document.createElement('section');
    overlay.className = 'mobile-welcome';
    overlay.setAttribute('role', 'status');
    overlay.setAttribute('aria-label', 'Welcome to SentryLoot');
    overlay.innerHTML = '<div class="mobile-welcome-emblem"><img src="https://images.gamestorehub.com/site-assets/storefront-7c336bd6c7318e89/sentryloot-mark-256.webp?v=1" alt="" width="80" height="80"></div><div class="mobile-welcome-label">Welcome to</div><div class="mobile-welcome-brand">Sentry<span>Loot</span></div><span class="mobile-welcome-rule"></span>';
    document.body.append(overlay);
    const underlying = [...document.body.children].filter(element => element !== overlay).map(element => [element, element.inert]);
    underlying.forEach(([element]) => element.inert = true);
    restoreIntro = () => { underlying.forEach(([element, inert]) => element.inert = inert); restoreIntro = () => {}; };
    const reduced = matchMedia('(prefers-reduced-motion:reduce)').matches;
    const hold = reduced ? 150 : 2800, fade = reduced ? 0 : 600;
    introTimers.push(setTimeout(() => overlay.classList.add('is-exiting'), hold));
    introTimers.push(setTimeout(() => {
      overlay.remove(); restoreIntro(); introComplete = true; finishIntroNavigation();
    }, hold + fade));
  }
  function enhanceHeader() {
    const header = document.querySelector('.site-header');
    if (!header) return;
    if (!header.querySelector('.mobile-context-header')) {
      const context=document.createElement('div'); context.className='mobile-context-header';
      context.innerHTML='<span>Marketplace</span>';
      header.append(context);
    }
    const context=header.querySelector('.mobile-context-header'),route=routeFromLocation();
    const accountRoute=/^account\//.test(route),authRoute=/^(?:(?:login|register|check-email|password-reset)$|verify\/)/.test(route);
    if(context){
      const caption=context.querySelector('span');
      caption.textContent=authRoute?'':route==='cart'||route==='orders'?t('Buyurtma ma’lumotlari','Детали заказа','Order details'):accountRoute||route==='notifications'?t('Hisobingiz','Ваш аккаунт','Your account'):route==='menu'?t('Menyu','Меню','Menu'):/^listing\//.test(route)?(app.querySelector('.listing-breadcrumbs a:nth-of-type(2)')?.textContent||'Marketplace'):'Marketplace';
      if(app.querySelector('.topup-product-page'))caption.textContent='Top Up';
      if(app.querySelector('.listing-redesign:is([data-mobile-panel=delivery],[data-mobile-panel=reviews])'))caption.textContent='Marketplace';
      if(route==='check-email'&&!context.querySelector('.auth-close'))context.insertAdjacentHTML('beforeend',`<a class="auth-close" href="/#home" aria-label="${t('Yopish','Закрыть','Close')}">×</a>`);
      if(route==='password-reset'){const close=context.querySelector('.auth-close');if(close)close.href='/#login';}
      if(!authRoute||app.querySelector('.auth-page .auth-close'))context.querySelector('.auth-close')?.remove();
      context.querySelector('.mobile-panel-close')?.remove();
      const listing=app.querySelector('.listing-redesign'),topup=app.querySelector('.mobile-topup-product');
      const dismiss=route==='menu'?()=>{location.hash='home';}:listing?.dataset.mobilePanel&&listing.dataset.mobilePanel!=='description'?()=>listingPanel():topup?.dataset.mobileReviews==='true'?()=>topupReviews(false):null;
      if(dismiss){
        const close=document.createElement('button');close.type='button';close.className='icon-button mobile-panel-close';
        close.setAttribute('aria-label',t('Yopish','Закрыть','Close'));close.textContent='×';close.onclick=dismiss;context.append(close);
      }
    }
    [['#cart-button','cart'],['#notifications-button','bell'],['#mobile-search-toggle','search'],['#mobile-menu-toggle','menu']].forEach(([selector,glyph]) => {
      const button = header.querySelector(selector);
      if (button && !button.querySelector('.mobile-design-icon')) button.insertAdjacentHTML('beforeend', designIcon(glyph));
    });
  }
  async function settings(route='account/settings') {
    if(!me){location.hash='login';return;}
    if(route!=='account/settings') { await OperationsUX.account(); adaptAccountPage(route); return; }
    const group=label=>`<h2 class="mobile-settings-group">${label}</h2>`;
    app.innerHTML=`<section class="page mobile-settings-page"><h1>${t('Hisob sozlamalari','Настройки аккаунта','Account settings')}</h1>
      <div class="mobile-settings-person">${marketAvatarMarkup(me.display_name,me.avatar_url,'mobile-account-avatar',me.id)}<div><h3>${esc(me.display_name||me.email)}</h3><span>${esc(me.email)}</span><br><a href="/#account/profile">${t('Profilni tahrirlash','Изменить профиль','Edit profile')}</a></div></div>
      ${group(t('PROFIL','ПРОФИЛЬ','PROFILE'))}
      ${accountRow('user',t('Shaxsiy ma’lumotlar','Личная информация','Personal information'),'/#account/profile')}
      ${accountRow('mail',t('Aloqa ma’lumotlari','Контактные данные','Contact details'),'/#account/contact')}
      ${accountRow('lock',t('Parol va xavfsizlik','Пароль и безопасность','Password & security'),'/#account/security')}
      ${accountRow('bell',t('Bildirishnoma sozlamalari','Настройки уведомлений','Notification preferences'),'/#notification-settings')}
      ${accountRow('globe',t('Til va hudud','Язык и регион','Language & region'),'/#account/preferences')}
      ${group(t('BOG‘LANISHLAR','ПОДКЛЮЧЕНИЯ','CONNECTIONS'))}
      <button type="button" class="mobile-account-row" data-action="link-facebook">${designIcon('facebook')}<span>${t('Facebook’ni ulash','Подключить Facebook','Link Facebook')}</span>${designIcon('right')}</button>
      ${accountRow('phone',t('Saqlangan Player ID','Сохранённые Player ID','Saved Player IDs'),'/#topup-saved')}
      ${group(t('MA’LUMOTLARINGIZ','ВАШИ ДАННЫЕ','YOUR DATA'))}
      ${accountRow('document',t('Ma’lumotlaringizni yuklash','Скачать свои данные','Download your data'),'/#account/export')}
      ${accountRow('help',t('Yordam murojaatlari','Обращения в поддержку','Support tickets'),'/#support-tickets')}
      <button class="mobile-account-row mobile-account-signout" type="button" data-action="logout">${designIcon('logout')}<span>${t('Chiqish','Выйти','Sign out')}</span>${designIcon('right')}</button>
      <details class="mobile-settings-more"><summary>${t('Qo‘shimcha imkoniyatlar','Другие возможности','More options')}</summary>
        ${accountRow('document',t('Xarid so‘rovlari','Запросы на покупку','Purchase requests'),'/#requests')}
        ${me.seller?accountRow('coins',t('Sotuvchi hamyoni','Кошелёк продавца','Seller wallet'),'/#wallet'):''}
        ${me.is_admin?accountRow('shield',t('Admin paneli','Панель администратора','Admin panel'),'/#admin'):''}
        ${accountRow('shield',t('Bloklanganlar','Заблокированные','Blocked users'),'/#account/blocks')}
        ${accountRow('star',t('Bonuslar','Бонусы','Benefits'),'/#benefits')}
        ${accountRow('help',t('Qoidalar','Правила','Terms & policies'),'/policies')}
      </details></section>`;
  }
  function adaptAccountPage(route=routeFromLocation()) {
    const original=app.querySelector('.ops-account');if(!original||!/^account\//.test(route)||route==='account/settings')return;
    window.LaunchUX?.enhance();
    const mode=route.split('/')[1],titles={profile:t('Profilni tahrirlash','Изменить профиль','Edit profile'),security:t('Parol va xavfsizlik','Пароль и безопасность','Password & security'),sessions:t('Faol sessiyalar','Активные сеансы','Active sessions'),password:t('Parolni almashtirish','Изменить пароль','Change password'),email:t('Emailni almashtirish','Изменить email','Change email'),preferences:t('Til va hudud','Язык и регион','Language & region'),export:t('Ma’lumotlarni yuklash','Скачать данные','Download your data'),contact:t('Aloqa ma’lumotlari','Контактные данные','Contact details'),blocks:t('Bloklanganlar','Заблокированные','Blocked users')};
    const page=document.createElement('section');page.className='page mobile-account-editor';page.dataset.editor=mode;
    page.innerHTML=`<h1>${titles[mode]||titles.profile}</h1>`;
    const append=selector=>{const node=original.querySelector(selector);if(node)page.append(node);return node;};
    if(mode==='profile'||mode==='preferences'){
      if(mode==='profile')append('.ops-avatar-settings');
      const form=append('#ops-profile-form');
      form.querySelectorAll('.field').forEach(field=>{const name=field.querySelector('input,select')?.name;field.hidden=mode==='profile'?!['display_name','country'].includes(name):name==='display_name'});
      const save=form.querySelector('button[type=submit],button.button-primary'),dock=document.createElement('div');dock.className='mobile-form-dock';save.setAttribute('form',form.id);dock.append(save);page.append(dock);
      if(mode==='profile'){const note=document.createElement('p');note.className='notice mobile-profile-note';note.innerHTML=designIcon('shield')+'<span>'+t('Ismingiz va avataringiz do‘koningizda, xabarlar va sharhlarda ko‘rinadi.','Ваше имя и аватар видны в магазине, сообщениях и отзывах.','Your name and avatar appear on your store, messages and reviews.')+'</span>';form.after(note);}
    }else if(mode==='security'){
      const card=append('.ops-security-card');card.classList.add('mobile-security-card');
      const head=document.createElement('header'),title=card.querySelector('h2'),state=card.querySelector('.ops-status');
      title.textContent=t('Ikki faktorli autentifikatsiya','Двухфакторная аутентификация','Two-factor authentication');
      const enabled=state.classList.contains('is-on');state.textContent=enabled?t('Yoqilgan','Включена','Enabled'):t('Yoqilmagan','Не включена','Not enabled');
      head.append(title,state);card.prepend(head);
      const help=card.querySelector('p.help');if(help&&!enabled)help.textContent=t('Hisobingizni himoyalash uchun ikkinchi bosqichni qo‘shing.','Добавьте второй шаг для защиты аккаунта.','Add a second step to protect your account.');
      const nav=document.createElement('nav');nav.className='mobile-settings-security-links';nav.innerHTML=accountRow('lock',titles.password,'/#account/password')+accountRow('shield',titles.sessions,'/#account/sessions')+accountRow('mail',titles.email,'/#account/email');page.append(nav);
    }else if(mode==='sessions'||mode==='blocks') append('.ops-'+mode+' .ops-disclosure-body');
    else if(mode==='password'||mode==='email')append('#ops-'+mode+'-form');
    else if(mode==='export'){const exportPanel=append('[data-launch-account]');exportPanel?.querySelector('h2')?.remove();}
    else if(mode==='contact'){
      const info=document.createElement('div');info.className='mobile-contact-card';info.innerHTML=`<span>${t('Email','Email','Email')}</span><b>${esc(me.email)}</b><small>${me.email_verified?t('Tasdiqlangan','Подтверждён','Verified'):t('Tasdiqlanmagan','Не подтверждён','Not verified')}</small><a href="/#account/email">${titles.email} →</a>${me.phone_verification_enabled?accountRow('phone',t('Telefon raqami','Номер телефона','Phone number'),'/#contact-details'):''}`;page.append(info);
    }
    original.replaceWith(page);
  }
  function enhanceTables() {
    app.querySelectorAll('table').forEach(table => {
      const headings = [...table.querySelectorAll('thead th')].map(th => th.textContent.trim());
      if (headings.length < 4) return;
      table.classList.add('mobile-table-cards');
      table.setAttribute('role', 'table');
      table.querySelectorAll('tbody tr').forEach(row => {
        row.setAttribute('role', 'row');
        [...row.children].forEach((cell, i) => {
          if (cell.colSpan > 1) return;
          cell.dataset.mobileLabel = headings[i] || '';
          cell.setAttribute('role', 'cell');
        });
      });
    });
  }
  function enhancePurchases() {
    const panel = app.querySelector('.listing-purchase-panel');
    panel?.closest('.listing-redesign')?.classList.add('sim-listing');
    if(panel && !panel.querySelector('.mobile-listing-meta')) {
      const meta=panel.querySelector('.listing-item-meta'),favorite=panel.querySelector('.listing-wishlist'),row=document.createElement('div');row.className='mobile-listing-meta';
      if(meta){meta.before(row);row.append(meta);if(favorite)row.append(favorite);}
      const stock=panel.querySelector('.listing-stock'),delivery=panel.querySelector('.listing-delivery-summary'),status=document.createElement('div');status.className='mobile-listing-status';
      if(stock){stock.before(status);status.append(stock);if(delivery)status.append(delivery);}
      const seller=panel.querySelector('.listing-seller-panel'),message=panel.querySelector('.listing-secondary-actions');if(seller&&message)seller.append(message);
      const share=panel.querySelector('.listing-save-share>button');if(share)app.querySelector('.listing-info-footer')?.append(share);
    }
    const listing=panel?.closest('.listing-redesign');
    if(listing){
      for(const [selector,glyph]of [['.listing-wishlist .icon','heart'],['.listing-delivery-summary .icon','clock'],['.listing-verified .icon','shield'],['.listing-seller-metrics .icon','star'],['.listing-secondary-actions .icon','chat'],['.listing-trust-panel .icon','shield']]){
        const svg=listing.querySelector(selector);if(svg&&!svg.dataset.simGlyph){svg.innerHTML=designPaths[glyph];svg.dataset.simGlyph='1';}
      }
      const store=listing.querySelector('.listing-store-link');if(store&&!store.dataset.simCaption){store.textContent=t('Do‘konni ko‘rish →','Магазин →','View store →');store.dataset.simCaption='1';}
      const watch=listing.querySelector('.ex-price-watch');if(watch&&watch.parentElement!==listing.querySelector('.listing-reference-grid')){listing.querySelector('.listing-reference-grid').append(watch);watch.querySelector('summary').textContent=t('Narx bildirishnomasini olish','Получить уведомление о цене','Get a price alert');}
      if(!me&&!listing.querySelector('.sim-price-alert')){const link=document.createElement('a');link.className='sim-price-alert';link.href='/#login';link.textContent=t('Narx bildirishnomasini olish','Получить уведомление о цене','Get a price alert');listing.querySelector('.listing-reference-grid').append(link);}
      const protection=listing.querySelector('.listing-trust-panel p');if(protection&&!protection.dataset.simCopy){protection.textContent=t('Yetkazishni kuzating va buyurtma sahifangizdan yordam oling.','Следите за доставкой и получайте помощь на странице заказа.','Track delivery and get help from your order page.');protection.dataset.simCopy='1';}
    }
    if (panel && !panel.querySelector('.mobile-purchase-dock')) {
      const price = panel.querySelector('[data-listing-price]');
      const button = panel.querySelector('.listing-buy-button');
      if (price && button) {
        // Move the existing live controls; retain their handlers, state and IDs.
        const dock = document.createElement('div'); dock.className = 'mobile-purchase-dock';
        price.before(dock); dock.append(price, button);
      }
    }
  }
  function enhanceCards() {
    app.querySelectorAll('.product-card.market-product-card').forEach(card=>{
      if(card.dataset.mobileCardLayout)return;card.dataset.mobileCardLayout='1';
      const arrow=card.querySelector('.market-card-view>span:last-child');if(arrow)arrow.innerHTML=designIcon('arrow');
      [['.market-card-delivery>.icon','clock'],['.market-seller-verified>.icon','shield'],['.favorite-card-button>.icon','heart'],['.market-card-rating>.icon','star']].forEach(([selector,glyph])=>{
        const svg=card.querySelector(selector);if(!svg)return;svg.innerHTML=designPaths[glyph];svg.classList.add('mobile-card-glyph');
      });
    });
  }
  function topupReviews(open=true){
    const page=app.querySelector('.mobile-topup-product');if(!page)return;
    if(open){page.dataset.mobileReviews='true';}else delete page.dataset.mobileReviews;
    enhanceHeader();
    window.scrollTo({top:0,behavior:'instant'});
  }
  function enhanceTopupProduct(){
    const page=app.querySelector('.topup-product-page'),purchase=page?.querySelector('.tu-purchase');if(!purchase||page.dataset.mobileCompact)return;
    page.dataset.mobileCompact='1';page.classList.add('mobile-topup-product');
    const layout=page.querySelector('.tu-layout'),heading=document.createElement('header');heading.className='mobile-topup-product-heading';
    const name=purchase.querySelector('h1'),slug=location.pathname.split('/')[2],game=marketGameLinks.find(g=>g[0]===slug);
    heading.innerHTML=(game?marketGameMark(game):designIcon('gamepad'))+'<div></div>';if(name)heading.querySelector('div').append(name);const caption=document.createElement('p');caption.textContent=slug==='pubg-mobile'?'Global · UC':page.dataset.gameCurrency||'';heading.querySelector('div').append(caption);layout.prepend(heading);
    const labels=[...purchase.querySelectorAll('.tu-select-label')];labels.forEach((label,index)=>{if(!index){label.textContent=t('1. Paketni tanlang','1. Выберите пакет','1. Choose amount');return;}const grid=label.nextElementSibling;if(!grid?.classList.contains('tu-packages'))return;const group=document.createElement('details');group.className='mobile-topup-package-group';const summary=document.createElement('summary');summary.textContent=label.textContent;label.before(group);group.append(summary,grid);label.remove();group.open=true;});
    const form=purchase.querySelector('#topup-checkout-form');
    const title=document.createElement('h2');title.className='mobile-topup-step-title';title.textContent=t('2. O‘yinchi ma’lumotlari','2. Данные игрока','2. Player details');form.prepend(title);
    const quantity=purchase.querySelector('.tu-order-line');form.after(quantity);
    const consent=purchase.querySelector('[data-tu-test-consent]')?.closest('label');if(consent)consent.classList.add('mobile-topup-consent');
    const dock=document.createElement('div');dock.className='mobile-topup-checkout-dock';const total=quantity.querySelector('.tu-total');if(total)dock.append(total);
    const review=form.querySelector('.tu-review-button');if(review){review.setAttribute('form',form.id);dock.append(review);}
    const pay=purchase.querySelector('.tu-purchase-actions .button-secondary');if(pay){pay.classList.add('mobile-topup-pay');dock.append(pay);}purchase.append(dock);
    const info=page.querySelector('.tu-information');if(info){const guide=document.createElement('details');guide.className='mobile-topup-guide';guide.id='mobile-topup-guide';const summary=document.createElement('summary');summary.textContent=t('Tavsif va Player ID yordami','Описание и помощь с Player ID','Description & Player ID help');info.before(guide);guide.append(summary,info);guide.open=true;}
    page.querySelectorAll('.tu-seller details').forEach(details=>details.open=true);
    const help=document.createElement('button');help.type='button';help.className='mobile-topup-id-help';help.textContent=t('Player ID qayerda?','Где найти Player ID?','Where can I find my Player ID?');help.onclick=()=>{const guide=page.querySelector('.mobile-topup-guide');if(guide){guide.open=true;guide.scrollIntoView({block:'start',behavior:'smooth'});}};form.append(help);
  }
  function enhanceTopUps() {
    enhanceTopupProduct();
    const hero=app.querySelector('.topup-page:not(.topup-product-page) .topup-hero');
    if (!hero || app.querySelector('.mobile-topup-intro')) return;
    const intro=document.createElement('header'); intro.className='mobile-topup-intro';
    intro.innerHTML=`<h1>Top Up</h1><p>${t('O‘yiningizni tanlang.','Выберите игру.','Choose your game.')}</p><label class="mobile-topup-search">${designIcon('search')}<span class="sr-only">${t('O‘yinlarni qidirish','Поиск игр','Search games')}</span><input type="search" autocomplete="off" placeholder="${t('O‘yinlarni qidirish…','Поиск игр…','Search games…')}"></label><p data-mobile-topup-empty role="status" hidden>${t('O‘yin topilmadi.','Игры не найдены.','No games found.')}</p>`;
    hero.before(intro);
    const cards=[...app.querySelectorAll('.topup-game-card')];
    cards.forEach(card=>{
      const title=card.querySelector('h2'),cover=card.querySelector('.topup-game-cover');
      if (!title || !cover) return;
      const link=document.createElement('a');link.href=cover.getAttribute('href');
      const slug=link.href.split('/').pop(), name=title.textContent;
      link.innerHTML=slug==='mobile-legends'?`<span class="mobile-topup-full-name">${esc(name)}</span><span class="mobile-topup-short-name">Mobile Legends</span>`:esc(name);
      title.replaceChildren(link);

    });
    intro.querySelector('input').addEventListener('input',event=>{
      const search=event.target.value.trim().toLocaleLowerCase();
      cards.forEach(card=>card.hidden=!card.querySelector('h2').textContent.toLocaleLowerCase().includes(search));
      intro.querySelector('[data-mobile-topup-empty]').hidden=cards.some(card=>!card.hidden);
    });
  }
  function listingPanel(key='description') {
    const page=app.querySelector('.listing-redesign');if(!page)return;
    page.dataset.mobilePanel=key;page.querySelectorAll('[data-listing-jump]').forEach(link=>{if(link.dataset.listingJump===key)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');});
    let title=page.querySelector('.mobile-listing-panel-title');
    if(!title){title=document.createElement('h1');title.className='mobile-listing-panel-title';page.querySelector('.listing-info-panel').prepend(title);}
    title.textContent=key==='reviews'?t('Xaridorlar sharhlari','Отзывы покупателей','Buyer reviews'):t('Mahsulot tafsilotlari','Подробности товара','Product details');
    enhanceHeader();window.scrollTo({top:0,behavior:'instant'});
  }
  function gamePage(game,categories,result,category='') {
    const categoryNames={accounts:t('Akkauntlar','Аккаунты','Accounts'),items:t('Buyumlar','Предметы','Items'),currency:t('Valyuta','Валюта','Currency'),services:t('Xizmatlar','Услуги','Services'),'top-ups':'Top Up',codes:t('Sovg‘a kartalari','Подарочные карты','Gift cards'),digital:t('Raqamli mahsulotlar','Цифровые товары','Digital products')};
    const order=['accounts','items','currency','services','top-ups','codes','digital'];categories=[...categories].sort((a,b)=>order.indexOf(a.slug)-order.indexOf(b.slug));
    const mark=marketGameLinks.find(row=>row[0]===game.slug),query=new URLSearchParams(location.search).get('q')||'';
    app.innerHTML=`<section class="page mobile-game-page"><header class="mobile-game-heading">${mark?marketGameMark(mark):designIcon('gamepad')}<div><h1>${esc(game.name)}</h1><p>${t('Mavjud takliflarni ko‘ring','Посмотрите доступные предложения','Explore available offers')}</p></div></header><form class="mobile-catalog-search" role="search">${designIcon('search')}<input type="search" name="q" value="${esc(query)}" aria-label="${esc(t('E’lonlarni qidirish','Поиск предложений','Search offers'))}" placeholder="${esc(t(game.name+' bo‘yicha qidirish…','Поиск '+game.name+'…','Search '+game.name+'…'))}"><button type="submit" class="sr-only">Search</button></form><nav class="mobile-category-chips" aria-label="${t('Mahsulot turi','Тип товара','Product type')}"><a href="/games/${esc(game.slug)}" ${!category?'aria-current="page"':''}>${t('Barchasi','Все','All')}</a>${categories.map(c=>`<a href="/games/${esc(game.slug)}/${esc(c.slug)}" ${category===c.slug?'aria-current="page"':''}>${esc(categoryNames[c.slug]||categoryLabel(c.name))}</a>`).join('')}</nav><div class="product-grid">${result.items.map(marketCard).join('')||empty(t('Hozir mos e’lonlar yo‘q','Подходящих предложений пока нет','No matching listings yet'))}</div></section>`;
    app.querySelector('form').onsubmit=event=>{event.preventDefault();const params=new URLSearchParams({game:game.slug});if(category)params.set('category',category);const value=event.currentTarget.elements.q.value.trim();if(value)params.set('q',value);history.pushState({},'','/browse?'+params);navigate();};
  }
  function enhanceBrowse() {
    const heading=app.querySelector('.market-browse-heading'),root=app.querySelector('#ux-browse-filters');
    if (!heading || !root || root.querySelector('.mobile-browse-toolbar')) return;
    const params=new URLSearchParams(location.search),title=heading.querySelector('h1');
    if (title) title.innerHTML=`<span class="mobile-browse-original">${esc(title.textContent)}</span><span class="mobile-browse-title">${t('Marketplace','Маркетплейс','Marketplace')}</span>`;
    const search=document.createElement('form'); search.className='mobile-catalog-search';search.setAttribute('role','search');
    search.innerHTML=`${designIcon('search')}<input type="search" name="q" value="${esc(params.get('q')||'')}" placeholder="${t('E’lonlarni qidirish…','Поиск объявлений…','Search listings…')}" aria-label="${t('E’lonlarni qidirish','Поиск объявлений','Search listings')}"><button type="submit" class="sr-only">${t('Qidirish','Поиск','Search')}</button>`;
    heading.append(search);
    search.onsubmit=event=>{event.preventDefault();const next=new URLSearchParams(location.search),value=search.elements.q.value.trim();value?next.set('q',value):next.delete('q');next.delete('page');history.pushState({},'','/browse?'+next);navigate()};
    const toolbar=document.createElement('div'); toolbar.className='mobile-browse-toolbar';
    const button=document.createElement('button');button.type='button';button.className='mobile-filter-trigger';
    button.innerHTML=designIcon('filter')+t('Filtrlar','Фильтры','Filters');button.setAttribute('aria-haspopup','dialog');
    toolbar.append(button);const sort=root.querySelector('.mobile-browse-sort');if(sort){toolbar.append(sort);const latest=sort.querySelector('option[value=newest]');if(latest)latest.textContent=t('Yangilar','Новые','Latest');}root.prepend(toolbar);
    const form=root.querySelector('.ux-filter-form');
    if(form){
      const dialog=document.createElement('dialog');dialog.className='mobile-filter-dialog';dialog.setAttribute('aria-label',t('Filtrlar','Фильтры','Filters'));
      dialog.innerHTML=`<header><button type="button" aria-label="${t('Yopish','Закрыть','Close')}">${designIcon('close')}</button><strong>${t('Filtrlar','Фильтры','Filters')}</strong></header><div class="mobile-filter-content"><div class="mobile-filter-handle" aria-hidden="true"></div><h1>${t('Filtrlar','Фильтры','Filters')}</h1></div><footer></footer>`;
      dialog.querySelector('header button').onclick=()=>dialog.close();
      dialog.querySelector('.mobile-filter-content').append(form);root.append(dialog);
      const arrange=()=>arrangeMobileFilters(dialog,form,heading,root,params);
      if(root.dataset.facetsReady)arrange();else root.addEventListener('catalogue-facets-ready',arrange,{once:true});
      button.onclick=()=>dialog.showModal();
    }
    const chips=document.createElement('nav');chips.className='mobile-category-chips';chips.setAttribute('aria-label',t('Mahsulot turi','Тип товара','Product type'));
    chips.innerHTML=[['',t('Barchasi','Все','All')],['accounts',t('Akkauntlar','Аккаунты','Accounts')],['items',t('Buyumlar','Предметы','Items')],['currency',t('Valyuta','Валюта','Currency')],['services',t('Xizmatlar','Услуги','Services')]].map(([value,label])=>{const next=new URLSearchParams(location.search);value?next.set('category',value):next.delete('category');next.delete('page');return `<a href="/browse?${esc(next.toString())}" ${params.get('category')===value||!params.get('category')&&!value?'aria-current="page"':''}>${esc(label)}</a>`}).join('');
    root.append(chips);
  }
  function arrangeMobileFilters(dialog,form,heading,root,params) {
    if(!dialog.isConnected||form.dataset.mobileArranged)return;
    form.dataset.mobileArranged='1';form.id='mobile-catalog-filters';
    const grid=form.querySelector('.ux-filter-grid'),bottom=form.querySelector('.ux-filter-bottom');
    const main=document.createElement('div');main.className='mobile-filter-fields';form.prepend(main);
    const field=(caption,name,options,value='')=>{const label=document.createElement('label');label.append(document.createTextNode(caption));const select=document.createElement('select');select.name=name;select.innerHTML=options;select.value=value;label.append(select);return label;};
    const categories=heading.querySelector('[data-mobile-market-category]');
    if(categories){const label=field(t('Mahsulot turi','Тип товара','Product type'),'category',categories.innerHTML,params.get('category')||'');label.querySelector('option').textContent=t('Barcha turlar','Все типы','All types');main.append(label);}
    const game=field(t('O‘yin','Игра','Game'),'game',`<option value="">${t('Barcha o‘yinlar','Все игры','All games')}</option>`+(typeof marketGameLinks!=='undefined'?marketGameLinks:[]).map(([slug,name])=>`<option value="${esc(slug)}">${esc(name)}</option>`).join(''),params.get('game')||'');main.append(game);
    if(!searchCatalogPromise)searchCatalogPromise=api('/seller/catalog').catch(()=>{searchCatalogPromise=null;return [];});
    searchCatalogPromise.then(games=>{if(!game.isConnected||!Array.isArray(games))return;const select=game.querySelector('select'),selected=select.value||params.get('game')||'';select.innerHTML=`<option value="">${t('Barcha o‘yinlar','Все игры','All games')}</option>`+games.map(g=>`<option value="${esc(g.slug)}">${esc(g.name)}</option>`).join('');if(selected&&![...select.options].some(o=>o.value===selected))select.add(new Option(selected,selected));select.value=selected;window.SelectMenus?.refresh?.(game);});
    const region=grid.querySelector('[name=region]')?.closest('label');
    if(region){region.hidden=false;region.querySelector('[name=region]').disabled=false;const select=region.querySelector('select');if(select?.options[0])select.options[0].textContent=t('Barcha hududlar','Любой регион','Any region');main.append(region);}else main.append(field(t('Hudud','Регион','Region'),'region','<option value="">Any region</option><option>Global</option><option>Asia</option><option>Europe</option>',params.get('region')||''));
    const currency=params.get('currency')||((params.has('min')||params.has('max'))?'UZS':'MYR');
    form.querySelector('input[type=hidden][name=currency]')?.remove();
    const currencyInput=document.createElement('input');currencyInput.type='hidden';currencyInput.name='currency';currencyInput.value=currency;form.append(currencyInput);
    const prices=document.createElement('div');prices.className='mobile-filter-prices';
    for(const [key,caption]of [['min',t('Min narx','Мин. цена','Min price')],['max',t('Max narx','Макс. цена','Max price')]]){
      const input=grid.querySelector(`[name="${key}"],[name="${key}_major"]`);if(!input)continue;const label=input.closest('label');label.hidden=false;input.disabled=false;input.name=key+'_major';input.inputMode='decimal';input.step=currency==='MYR'?'0.01':'1';input.value=params.get(key+'_major')||(params.get(key)?String(Number(params.get(key))/(currency==='MYR'?100:1)):'');input.placeholder=key==='min'?'0':'500';label.firstChild.textContent=caption+' ('+(currency==='MYR'?'RM':currency)+')';label.dataset.priceCaption=caption;prices.append(label);
    }

    main.append(prices);
    const delivery=grid.querySelector('[name=delivery]')?.closest('label');if(delivery){delivery.firstChild.textContent=t('Yetkazish vaqti','Время доставки','Delivery time');main.append(delivery);}
    const verified=bottom.querySelector('[name=verified]')?.closest('label');if(verified){verified.classList.add('mobile-filter-check');verified.lastChild.textContent=' '+t('Faqat tasdiqlangan sotuvchilar','Только проверенные продавцы','Verified sellers only');main.append(verified);}
    const reset=document.createElement('button');reset.type='button';reset.className='mobile-filter-reset';reset.textContent=t('Filtrlarni tozalash','Сбросить фильтры','Reset filters');reset.onclick=()=>{history.pushState({},'','/browse');navigate();};main.append(reset);
    for(const key of ['platform','server','rank','item_type','condition','item_variant','float_min','float_max','online','sort','account_level','redemption_region','code_kind','unit']){if(!params.get(key))continue;const input=document.createElement('input');input.type='hidden';input.name=key;input.value=params.get(key);form.append(input);}
    grid.remove();root.querySelector('.trade-search-actions')?.remove();
    const submit=bottom.querySelector('button');submit.setAttribute('form',form.id);submit.textContent=t('Natijalarni ko‘rsatish','Показать результаты','Show results');dialog.querySelector('footer').append(submit);bottom.remove();
    for(const control of form.querySelectorAll('select,input:not([type=checkbox]):not([type=hidden]):not(.site-select-search)')){
      const label=control.closest('label');if(!label||label.querySelector('.mobile-filter-field-icon'))continue;
      const names={category:'box',game:'gamepad',region:'globe',min_major:'coins',max_major:'coins',currency:'coins',delivery:'clock',platform:'phone',rank:'star',sort:'filter'};
      label.classList.add('mobile-filter-field');const mark=document.createElement('span');mark.className='mobile-filter-field-icon';mark.innerHTML=designIcon(names[control.name]||'document');label.append(mark);
    }
    window.SelectMenus?.refresh?.(dialog);
  }
  function cart(data) {
    if(!isMobile())return;
    const original=app.querySelector('.order-process'),form=original?.querySelector('#of-checkout');if(!form||app.querySelector('.mobile-cart-preview'))return;
    original.classList.add('mobile-cart-review');original.hidden=true;
    const preview=document.createElement('section');preview.className='page mobile-cart-preview';preview.dataset.listing=data.items[0].id;
    preview.innerHTML=`<h1>${t('Savat','Ваша корзина','Your cart')}</h1><p class="mobile-cart-intro">${t('Davom etishdan oldin mahsulotingizni tekshiring.','Проверьте товар перед продолжением.','Review your item before continuing.')}</p><div class="mobile-cart-items"></div><section class="mobile-cart-summary">${original.querySelector('[data-of-quote]').innerHTML}</section><p class="notice mobile-cart-test">${designIcon('shield')}<span>${data.payment_mode==='stripe_test'?t('To‘lov Stripe orqali xavfsiz bajariladi.','Платёж безопасно обрабатывается через Stripe.','Payment is securely processed through Stripe.'):t('To‘lov hali sozlanmoqda. Hozir pul yechilmaydi.','Оплата настраивается. Сейчас деньги не списываются.','Payments are being set up. No money is charged right now.')}</span></p><div class="mobile-cart-dock"><div class="mobile-cart-amount"><span>${t('Jami','Итого','Total')}</span><strong>${data.items[0].currency==='MYR'?'<small>RM</small> '+esc(fmt(data.total_minor,'MYR').replace(/^RM\s*/,'')):esc(fmt(data.total_minor,data.items[0].currency))}</strong></div><button type="button">${t('Davom etish','Продолжить','Continue')}${designIcon('arrow')}</button></div>`;
    const summary=preview.querySelector('.mobile-cart-summary');
    const lines=summary.querySelectorAll('.of-totals>div');
    if(lines[0])lines[0].querySelector('dt').textContent=t('Mahsulot narxi','Стоимость товара','Item price');
    const fee=lines[lines.length-2];if(fee)fee.querySelector('dt').textContent=t('Xizmat haqi','Комиссия сервиса','Service fee');
    summary.querySelector('.of-total dt').textContent=t('Jami','Итого','Total');
    const list=preview.querySelector('.mobile-cart-items');
    data.items.forEach(item=>{
      const card=document.createElement('article');card.className='mobile-cart-item';
      card.innerHTML=`<div class="mobile-cart-item-main">${item.image_url?`<img src="${esc(item.image_url)}" alt="" width="47" height="47">`:designIcon('box')}<div><h2>${esc(item.title)}</h2><span>${esc(item.seller_display_name||item.seller_name||item.game_name||'')}${Number(item.identity_verified)===1?`<span class="mobile-cart-verified" aria-label="${t('Shaxsi tasdiqlangan','Личность подтверждена','Identity verified')}">${designIcon('shield')}</span>`:''}</span></div></div><div class="mobile-cart-quantity"><span>${t('Miqdor','Количество','Quantity')}</span><div><button type="button" data-cart-quantity="-1" aria-label="${t('Kamaytirish','Уменьшить количество','Decrease quantity')}" ${Number(item.quantity)<=Number(item.min_quantity||1)?'disabled':''}><svg class="mobile-design-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h16"/></svg></button><b>${Number(item.quantity)}</b><button type="button" data-cart-quantity="1" aria-label="${t('Ko‘paytirish','Увеличить количество','Increase quantity')}" ${Number(item.quantity)>=Number(item.available)?'disabled':''}><svg class="mobile-design-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h16M12 4v16"/></svg></button></div></div><p class="mobile-cart-error" role="alert" hidden></p>`;
      const remove=original.querySelector('[data-of-remove="'+CSS.escape(item.id)+'"]');if(remove){remove.classList.add('mobile-cart-remove');remove.innerHTML=designIcon('close');remove.setAttribute('aria-label',t('Mahsulotni olib tashlash','Удалить товар','Remove item'));card.querySelector('.mobile-cart-item-main').append(remove);}
      card.querySelectorAll('[data-cart-quantity]').forEach(button=>button.onclick=async()=>{
        card.querySelectorAll('button').forEach(control=>control.disabled=true);const error=card.querySelector('.mobile-cart-error');error.hidden=true;
        try{await api('/cart',{method:'POST',body:JSON.stringify({listing_id:item.id,quantity:Number(item.quantity)+Number(button.dataset.cartQuantity),mode:'set'})});if(!preview.isConnected)return;await refreshCart();await window.OrderFlow.cart();}
        catch(problem){if(!preview.isConnected)return;error.textContent=problem.message;error.hidden=false;card.querySelectorAll('button').forEach(control=>control.disabled=false);card.querySelector('[data-cart-quantity="-1"]').disabled=Number(item.quantity)<=Number(item.min_quantity||1);card.querySelector('[data-cart-quantity="1"]').disabled=Number(item.quantity)>=Number(item.available);}
      });list.append(card);
    });
    original.before(preview);
    const heading=document.createElement('header');heading.className='mobile-cart-review-heading';heading.innerHTML=`<span>${t('4 bosqichdan 1','Шаг 1 из 4','Step 1 of 4')} · ${t('Buyurtmani tekshirish','Проверка заказа','Review order')}</span><i></i><h1>${t('Buyurtmani tekshiring','Проверьте заказ','Check your order')}</h1>`;original.prepend(heading);
    const submit=form.querySelector('button[type=submit]'),dock=document.createElement('div');dock.className='mobile-cart-dock mobile-cart-review-dock';submit.setAttribute('form',form.id);dock.append(submit);original.append(dock);
    preview.querySelector('.mobile-cart-dock>button').onclick=()=>{preview.hidden=true;original.hidden=false;window.scrollTo({top:0,behavior:'instant'});};
  }
  function enhanceAuth() {
    const page=app.querySelector('.auth-page');if(!page||page.dataset.mobileAuth)return;
    page.dataset.mobileAuth='1';const register=page.classList.contains('is-register'),brand=page.querySelector('.auth-mobile-brand'),form=page.querySelector('#auth-form');
    if(brand){const mark=brand.querySelector('.brand-mark'),wordmark=document.createElement('span');wordmark.className='mobile-auth-wordmark';wordmark.innerHTML='Sentry<span>Loot</span>';brand.replaceChildren(mark,wordmark);}
    const title=page.querySelector('h1'),subtitle=page.querySelector('.auth-subtitle');
    title.textContent=register?t('Hisob yaratish','Создать аккаунт','Create account'):t('Qaytganingizdan xursandmiz','С возвращением','Welcome back');
    subtitle.textContent=register?t('Bitta hisob bilan xarid qiling va soting.','Покупайте и продавайте с одним аккаунтом.','Start buying and selling with one account.'):t('SentryLoot hisobingizga kiring.','Войдите в свой аккаунт SentryLoot.','Sign in to your SentryLoot account.');
    [['name','user'],['email','mail'],['password','lock']].forEach(([name,glyph])=>{
      const input=form.querySelector('input[name="'+name+'"]');if(!input)return;
      let control=input.closest('.field-control,.auth-password-control');
      if(!control){control=document.createElement('div');control.className='field-control';input.before(control);control.append(input);}
      if(!control.querySelector('.field-control-icon')){control.insertAdjacentHTML('afterbegin',icon(glyph));control.querySelector('.icon').classList.add('field-control-icon');}
      if(name==='email')input.placeholder='you@example.com';if(name==='name')input.placeholder=t('To‘liq ismingiz','Полное имя','Full name');
    });
    const password=page.querySelector('#auth-password')?.closest('.field'),country=page.querySelector('.auth-country-field');if(country&&password)password.after(country);
    const forgot=page.querySelector('.auth-label-row a');if(forgot&&password){forgot.textContent=t('Parolni unutdingizmi?','Забыли пароль?','Forgot password?');const row=document.createElement('div');row.className='mobile-auth-forgot';row.append(forgot);password.after(row);}
    const providers=page.querySelector('.auth-social-section');
    if(providers){
      const terms=providers.querySelector('.auth-oauth-terms');if(register&&terms)form.querySelector('button[type=submit]').before(terms);
      const options=document.createElement('details');options.className='mobile-auth-options';options.innerHTML=`<summary>${t('Boshqa kirish usullari','Другие способы входа','Other sign-in options')}</summary>`;
      providers.before(options);options.append(providers);form.after(options);
      const hint=page.querySelector('.auth-password-hint');if(hint)providers.append(hint);
    }
    page.querySelector('.auth-divider')?.remove();
    {
      // Preserve the real auth controls and handlers in both approved mobile forms.
      (register?[['name','user'],['email','mail'],['password','lock']]:[['email','mail'],['password','lock']]).forEach(([name,glyph])=>{
        const input=form.querySelector('input[name="'+name+'"]');if(!input)return;
        input.dataset.mobileLoginControl='true';
        let control=input.closest('.field-control,.auth-password-control');
        if(!control){control=document.createElement('div');control.className='field-control';input.before(control);control.append(input);}
        control.dataset.mobileLoginControl='true';
        control.querySelectorAll('.field-control-icon').forEach(node=>node.remove());
        control.insertAdjacentHTML('afterbegin',`<svg class="field-control-icon mobile-login-field-icon" viewBox="0 0 24 24" aria-hidden="true"><g transform="translate(3 3) scale(.75)">${designPaths[glyph]}</g></svg>`);
        input.placeholder=name==='name'?t('To‘liq ismingiz','Полное имя','Full name'):name==='email'?'you@example.com':register?t('Kamida '+input.minLength+' belgi','Не менее '+input.minLength+' символов','At least '+input.minLength+' characters'):t('Parolingizni kiriting','Введите пароль','Enter your password');
      });
      const prompt=page.querySelector('.auth-switch');
      if(!register&&prompt?.firstChild?.nodeType===3)prompt.firstChild.textContent=t('SentryLoot’da yangimisiz? ','Впервые в SentryLoot? ','New to SentryLoot? ');
    }
    const context=document.querySelector('.mobile-context-header'),close=page.querySelector('.auth-close');if(context&&close)context.append(close);
  }
  const pendingEmailKey='sentryloot-pending-verification:v1';
  let pendingVerification=null;
  function maskVerificationEmail(email) {
    const [name,domain]=String(email||'').split('@');
    return domain?name.slice(0,2)+'***@'+domain:'';
  }
  function registrationSubmitted(email,response) {
    pendingVerification={email,development:Boolean(response.verification_token),token:response.verification_token||''};
    try{sessionStorage.setItem(pendingEmailKey,JSON.stringify({email,development:pendingVerification.development}));}catch(_){}
    location.hash='check-email';
  }
  function emailCheck() {
    if(!pendingVerification){try{pendingVerification=JSON.parse(sessionStorage.getItem(pendingEmailKey)||'null');}catch(_){}}
    if(!pendingVerification||typeof pendingVerification.email!=='string'||!/^.{1,254}@[^@\s]+$/.test(pendingVerification.email)){location.hash='register';return;}
    const pending=pendingVerification;
    const sent=t('Tasdiqlash havolasini '+maskVerificationEmail(pending.email)+' manziliga yubordik.','Ссылка для подтверждения отправлена на '+maskVerificationEmail(pending.email)+'.','We sent a verification link to '+maskVerificationEmail(pending.email)+'.');
    const development=t('Mahalliy sinov: email yuborilmadi.','Локальная проверка: письмо не отправлено.','Local development: no verification email was sent.');
    app.innerHTML=`<section class="page mobile-email-check"><div class="mobile-reset-brand"><img src="https://images.gamestorehub.com/site-assets/storefront-7c336bd6c7318e89/sentryloot-mark-256.webp?v=1" width="44" height="44" alt=""><span>Sentry<b>Loot</b></span></div><div class="mobile-email-check-intro"><span class="mobile-email-check-clock" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/></svg></span><h1>${t('Emailingizni tekshiring','Проверьте почту','Check your email')}</h1><p>${esc(pending.development?development:sent)}</p></div><div class="mobile-email-check-help"><h2>${t('Davom etish uchun havolani oching','Откройте ссылку, чтобы продолжить','Open the link to continue')}</h2><p>${t('Inbox va Spam papkalarini tekshiring. Havola hisobingizni tasdiqlaydi.','Проверьте папки «Входящие» и «Спам». Ссылка подтвердит ваш аккаунт.','Check Inbox and Spam. The link opens your verified account.')}</p></div><p class="mobile-email-check-feedback" role="status" hidden></p><button type="button" class="mobile-email-check-resend">${t('Tasdiqlash xatini qayta yuborish','Отправить письмо повторно','Resend verification email')}</button><a href="/#register" class="mobile-email-check-change">${t('Boshqa emaildan foydalanish','Использовать другой email','Use a different email')}</a>${pending.development&&pending.token?`<a class="mobile-email-check-development" href="/#verify/${encodeURIComponent(pending.token)}">${t('Mahalliy tasdiqlash havolasini ochish','Открыть локальную ссылку подтверждения','Open local verification link')}</a>`:''}</section>`;
    const clearPending=()=>{pendingVerification=null;try{sessionStorage.removeItem(pendingEmailKey);}catch(_){}};
    app.querySelector('.mobile-email-check-change').addEventListener('click',clearPending);
    const button=app.querySelector('.mobile-email-check-resend'),feedback=app.querySelector('.mobile-email-check-feedback');
    button.addEventListener('click',async()=>{
      if(button.disabled)return;button.disabled=true;feedback.hidden=true;
      try{
        const result=await api('/verification/resend',{method:'POST',body:JSON.stringify({email:pending.email})});
        feedback.classList.remove('is-error');feedback.textContent=result.verification_token?development:t('Agar bu email tasdiqlanmagan hisobga tegishli bo‘lsa, yangi havola yuborildi.','Если email принадлежит неподтверждённому аккаунту, новая ссылка отправлена.','If this address belongs to an unverified account, a new link has been sent.');feedback.hidden=false;
        if(result.verification_token){pending.token=result.verification_token;let link=app.querySelector('.mobile-email-check-development');if(!link){link=document.createElement('a');link.className='mobile-email-check-development';link.textContent=t('Mahalliy tasdiqlash havolasini ochish','Открыть локальную ссылку подтверждения','Open local verification link');app.querySelector('.mobile-email-check').append(link);}link.href='/#verify/'+encodeURIComponent(result.verification_token);}
        const until=Date.now()+60000,label=button.textContent;
        const tick=()=>{if(!button.isConnected)return;const left=Math.max(0,Math.ceil((until-Date.now())/1000));button.textContent=left?label+' ('+left+'s)':label;if(left)setTimeout(tick,1000);else button.disabled=false;};tick();
      }catch(error){feedback.classList.add('is-error');feedback.textContent=error.message;feedback.hidden=false;button.disabled=false;}
    });
  }
  function verificationStatus(status,detail='') {
    const verified=status==='verified',failed=status==='error';
    if(verified){pendingVerification=null;try{sessionStorage.removeItem(pendingEmailKey);}catch(_){}}
    const title=verified?t('Email tasdiqlandi','Email подтверждён','Email verified'):failed?t('Havolani tekshirib bo‘lmadi','Не удалось проверить ссылку','Verification link unavailable'):t('Email tekshirilmoqda','Проверяем email','Verifying your email');
    const description=verified?t('Hisobingiz foydalanishga tayyor.','Ваш аккаунт готов к использованию.','Your account is ready to use.'):failed?detail:t('Biroz kuting…','Подождите…','Please wait…');
    const glyph=verified?designIcon('check'):failed?designIcon('help'):'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 3"/></svg>';
    app.innerHTML=`<section class="page mobile-email-verified ${verified?'is-success':failed?'is-error':'is-loading'}"><div class="mobile-reset-brand"><img src="https://images.gamestorehub.com/site-assets/storefront-7c336bd6c7318e89/sentryloot-mark-256.webp?v=1" width="44" height="44" alt=""><span>Sentry<b>Loot</b></span></div><div class="mobile-email-check-intro" role="status"><span class="mobile-email-check-clock" aria-hidden="true">${glyph}</span><h1>${esc(title)}</h1><p>${esc(description)}</p></div>${verified||failed?`<div class="mobile-email-verified-dock"><a class="mobile-email-verified-continue" href="/#${verified?(detail||'account'):'login'}">${verified?t('Davom etish','Продолжить','Continue'):t('Kirish','Войти','Sign in')}${designIcon('arrow')}</a></div>`:''}</section>`;
  }
  function enhancePasswordReset() {
    if(routeFromLocation()!=='password-reset')return;
    const form=app.querySelector('#reset-request'),page=form?.closest('.page');
    if(!page||page.dataset.mobileReset)return;
    page.dataset.mobileReset='1';page.classList.add('mobile-reset-page');
    const card=page.querySelector('.auth-card');
    card.querySelector('.identity-mark')?.remove();card.querySelector('.eyebrow')?.remove();
    const title=card.querySelector('h1');title.textContent=t('Parolni tiklash','Сброс пароля','Reset password');
    title.insertAdjacentHTML('beforebegin',`<div class="mobile-reset-brand"><img src="https://images.gamestorehub.com/site-assets/storefront-7c336bd6c7318e89/sentryloot-mark-256.webp?v=1" width="44" height="44" alt=""><span>Sentry<b>Loot</b></span></div>`);
    title.insertAdjacentHTML('afterend',`<p class="mobile-reset-subtitle">${t('Tiklash havolasini olish uchun emailingizni kiriting.','Введите email, чтобы получить ссылку для сброса.','Enter your email to receive a reset link.')}</p>`);
    const input=form.querySelector('input[name=email]');input.placeholder='you@example.com';input.dataset.mobileLoginControl='true';
    let control=input.closest('.field-control');
    if(!control){control=document.createElement('div');control.className='field-control';input.before(control);control.append(input);}
    control.querySelectorAll('.field-control-icon').forEach(node=>node.remove());
    control.insertAdjacentHTML('afterbegin',`<svg class="field-control-icon" viewBox="0 0 24 24" aria-hidden="true"><g transform="translate(3 3) scale(.75)">${designPaths.mail}</g></svg>`);
    // Keep native email constraints, but place their message below the field.
    const emailError=document.createElement('p');emailError.id='mobile-reset-email-error';emailError.className='mobile-reset-email-error';emailError.hidden=true;emailError.setAttribute('role','alert');control.after(emailError);
    input.addEventListener('invalid',event=>{
      if(!isMobile())return;
      event.preventDefault();control.querySelectorAll('.ex-native-error').forEach(node=>node.remove());emailError.textContent=input.validationMessage;emailError.hidden=false;
      input.setAttribute('aria-invalid','true');input.setAttribute('aria-describedby',emailError.id);input.focus();
    });
    input.addEventListener('input',()=>{
      if(emailError.hidden)return;
      if(input.validity.valid){emailError.hidden=true;emailError.textContent='';input.removeAttribute('aria-invalid');input.removeAttribute('aria-describedby');}
      else {emailError.textContent=input.validationMessage;input.setAttribute('aria-invalid','true');input.setAttribute('aria-describedby',emailError.id);}
    });
    const submit=form.querySelector('button');submit.innerHTML=`${t('Tiklash havolasini yuborish','Отправить ссылку','Send reset link')}${designIcon('arrow')}`;
    const help=card.querySelector(':scope>.help');if(help)help.hidden=true;
    const context=document.querySelector('.mobile-context-header');
    if(context){if(!context.querySelector('.auth-close'))context.insertAdjacentHTML('beforeend',`<a class="auth-close" href="/#login" aria-label="${t('Yopish','Закрыть','Close')}">×</a>`);}
  }
  function purchaseGroup(order) {
    if(order.status==='completed')return 'completed';
    return ['cancelled','refunded','expired','failed'].includes(order.status)?'cancelled':'active';
  }
  function purchaseDate(value) {
    const date=parseServerDate(value);if(!Number.isFinite(date.getTime()))return '';
    return date.toLocaleDateString(localeTag(),{month:'short',day:'numeric'})+' · '+date.toLocaleTimeString(localeTag(),{hour:'2-digit',minute:'2-digit',hour12:false});
  }
  function orders(data,games=[],active='active') {
    const purchases=data.filter(order=>order.buyer_id===me.id),visible=purchases.filter(order=>purchaseGroup(order)===active);
    const types={account:t('Akkaunt','Аккаунт','Account'),item:t('Buyum','Предмет','Item'),currency:t('O‘yin valyutasi','Игровая валюта','Game currency'),code:t('Sovg‘a kartasi','Подарочная карта','Gift card'),topup:'Top-up',service:t('Xizmat','Услуга','Service'),digital:t('Raqamli mahsulot','Цифровой товар','Digital product')};
    app.innerHTML=`<section class="page mobile-purchases-page"><h1>${t('Xaridlar','Покупки','Purchases')}</h1><div class="mobile-purchase-filters" role="tablist" aria-label="${t('Xarid holati','Статус покупки','Purchase status')}">${[['active',t('Faol','Активные','Active')],['completed',t('Yakunlangan','Завершённые','Completed')],['cancelled',t('Bekor qilingan','Отменённые','Cancelled')]].map(([key,label])=>`<button type="button" role="tab" id="purchase-tab-${key}" aria-controls="mobile-purchase-list" aria-selected="${active===key}" tabindex="${active===key?'0':'-1'}" data-purchase-filter="${key}">${label}</button>`).join('')}</div><div class="mobile-purchase-list" id="mobile-purchase-list" role="tabpanel" aria-labelledby="purchase-tab-${active}">${visible.map(order=>{
      const completed=order.status==='completed',label=order.status==='awaiting_delivery'?t('Yetkazish kutilmoqda','Ожидается доставка','Awaiting delivery'):window.OrderFlow.statusLabel(order.status);
      return `<a class="mobile-purchase-card" href="/#order/${encodeURIComponent(order.id)}"><div class="mobile-purchase-card-top"><span>${esc(order.reference)}</span><span class="mobile-purchase-status ${completed?'is-complete':'is-pending'}">${designIcon(completed?'check':'clock')}${esc(label)}</span></div>${(order.items||[]).map(item=>{
        const snapshot=item.snapshot||{},game=games.find(game=>game.id===(snapshot.game_id||item.game_id)),known=typeof marketGameLinks!=='undefined'?marketGameLinks.find(entry=>entry[0]===(snapshot.game_id||item.game_id)||entry[0]===game?.slug):null;
        const name=snapshot.game_name||game?.name||known?.[1]||'',image=known?.[2]||snapshot.image_url||item.image_url;
        return `<div class="mobile-purchase-product">${image?`<img src="${esc(image)}" alt="" width="43" height="43" loading="lazy">`:designIcon('box')}<div><h2>${esc(item.title||snapshot.title||'')}</h2><p>${esc([name,types[snapshot.product_type||item.product_type]||''].filter(Boolean).join(' · '))} × ${Number(item.quantity)}</p></div></div>`;
      }).join('')}<div class="mobile-purchase-card-bottom"><strong>${esc(fmt(order.total_minor,order.currency))}</strong><time datetime="${esc(order.created_at)}">${esc(purchaseDate(order.created_at))}${designIcon('right')}</time></div></a>`;
    }).join('')||`<p class="mobile-purchases-empty" role="status">${t('Bu bo‘limda xaridlar yo‘q.','В этом разделе нет покупок.','No purchases in this section.')}</p>`}</div></section>`;
    app.querySelectorAll('[data-purchase-filter]').forEach(button=>{
      const choose=key=>{orders(data,games,key);app.querySelector('[data-purchase-filter="'+key+'"]').focus();};
      button.onclick=()=>choose(button.dataset.purchaseFilter);
      button.onkeydown=event=>{const keys=['active','completed','cancelled'],i=keys.indexOf(button.dataset.purchaseFilter);if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();choose(event.key==='Home'?keys[0]:event.key==='End'?keys[2]:keys[(i+(event.key==='ArrowRight'?1:2))%3]);}};
    });
  }
  function notificationGlyph(item) {
    const kind=String(item.kind||'').toLowerCase();
    if(/identity|verification|security|seller/.test(kind))return 'shield';
    if(/listing|offer|moderation/.test(kind))return 'box';
    if(/wallet|payment|payout|balance|fund/.test(kind))return 'wallet';
    if(/delivery|order/.test(kind))return 'truck';
    if(/message|chat/.test(kind))return 'chat';
    if(/review/.test(kind))return 'star';
    return 'bell';
  }
  function notificationAge(value,now=Date.now()) {
    const date=parseServerDate(value),minutes=Math.floor((now-date.getTime())/60000);
    if(!Number.isFinite(minutes))return '';
    if(minutes<1)return t('Hozirgina','Только что','Just now');
    if(minutes<60)return t(minutes+' daqiqa oldin',minutes+' мин назад',minutes+'m ago');
    if(minutes<1440){const hours=Math.floor(minutes/60);return t(hours+' soat oldin',hours+' ч назад',hours+'h ago');}
    if(minutes<10080){const days=Math.floor(minutes/1440);return t(days+' kun oldin',days+' дн назад',days+'d ago');}
    return date.toLocaleDateString(localeTag(),{month:'short',day:'numeric',year:'numeric'});
  }
  function notifications(items,active='all') {
    const visible=active==='unread'?items.filter(item=>!item.read_at):items;
    app.innerHTML=`<section class="page mobile-notifications-page"><h1>${t('Bildirishnomalar','Уведомления','Notifications')}</h1><div class="mobile-notification-tabs" role="tablist" aria-label="${t('Bildirishnomalar filtri','Фильтр уведомлений','Notification filter')}">${[['all',t('Barchasi','Все','All')],['unread',t('O‘qilmagan','Непрочитанные','Unread')]].map(([key,label])=>`<button type="button" id="notification-tab-${key}" role="tab" aria-selected="${key===active}" aria-controls="mobile-notification-list" tabindex="${key===active?'0':'-1'}" data-notification-tab="${key}">${label}</button>`).join('')}</div><div id="mobile-notification-list" class="mobile-notification-list" role="tabpanel" aria-labelledby="notification-tab-${active}">${visible.map(item=>`<a class="mobile-notification-row" href="#${esc(notificationRoute(item.href))}" data-action="open-notification" data-route="${esc(notificationRoute(item.href))}" data-id="${esc(item.id)}">${designIcon(notificationGlyph(item))}<div><h3>${esc(localized(item.title))}</h3><p>${esc(localized(item.body))}</p><time datetime="${esc(item.created_at)}">${esc(notificationAge(item.created_at))}</time></div>${!item.read_at?`<i class="mobile-notification-dot" aria-label="${t('O‘qilmagan','Непрочитанное','Unread')}"></i>`:''}</a>`).join('')||`<p class="mobile-notifications-empty" role="status">${active==='unread'?t('O‘qilmagan bildirishnomalar yo‘q.','Нет непрочитанных уведомлений.','No unread notifications.'):t('Hozircha bildirishnomalar yo‘q.','Пока нет уведомлений.','No notifications yet.')}</p>`}</div></section>`;
    app.querySelectorAll('[data-notification-tab]').forEach(button=>{
      const choose=key=>{notifications(items,key);app.querySelector('[data-notification-tab="'+key+'"]').focus();};
      button.onclick=()=>choose(button.dataset.notificationTab);
      button.onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();choose(event.key==='Home'?'all':event.key==='End'?'unread':button.dataset.notificationTab==='all'?'unread':'all');}};
    });
  }
  function enhanceMessages() {
    const route=routeFromLocation();
    if (!/^(messages|conversation\/)/.test(route)) return;
    const form=app.querySelector('#ex-conversation-search');
    if (form && !form.classList.contains('mobile-conversation-search')) {
      form.classList.add('mobile-conversation-search');
      const input=form.querySelector('input[name=q]');
      input.placeholder=t('Suhbatlarni qidirish…','Поиск чатов…','Search conversations…');
      input.setAttribute('aria-label',t('Suhbatlarni qidirish','Поиск чатов','Search conversations'));
      form.insertAdjacentHTML('afterbegin',designIcon('search'));form.append(input);

    }
    app.querySelectorAll('.conversation-item:not(.mobile-conversation-item)').forEach(row=>{
      const name=row.querySelector('b'),copy=document.createElement('div');copy.className='mobile-message-copy';
      const heading=document.createElement('div');heading.className='mobile-message-heading';heading.append(name);
      const time=row.querySelector('time');if(time)heading.append(time);copy.append(heading);
      [...row.children].filter(node=>!node.classList.contains('status')).forEach(node=>copy.append(node));
      row.insertAdjacentHTML('afterbegin',marketAvatarMarkup(name?.textContent||'',row.dataset.avatar||'', 'mobile-message-avatar'));
      row.append(copy);const unread=row.querySelector('.status');if(unread){unread.setAttribute('aria-label',unread.textContent+' '+t('o‘qilmagan xabar','непрочитанных сообщений','unread messages'));row.append(unread);}
      row.classList.add('mobile-conversation-item');
    });
    if(!route.startsWith('conversation/'))return;
    const header=app.querySelector('.ux-chat-header');if(!header)return;
    const context=document.querySelector('.mobile-context-header');
    if(context){context.querySelector('span').textContent=header.querySelector('b')?.textContent||t('Suhbat','Чат','Conversation');}
    let tools=header.querySelector('.mobile-chat-tools');
    if(!tools){tools=document.createElement('details');tools.className='mobile-chat-tools';tools.innerHTML=`<summary aria-label="${t('Suhbat sozlamalari','Параметры чата','Conversation options')}">⋯</summary><div class="mobile-chat-tools-body"></div>`;header.append(tools);}
    const body=tools.querySelector('div');
    header.querySelectorAll('.ex-chat-controls,.ops-chat-controls,#ux-chat-state').forEach(node=>{if(!body.contains(node))body.append(node);});
    for(const selector of ['.ex-message-search','.ux-chat-quick','.chat>.ex-panel']){const node=app.querySelector(selector);if(node&&!body.contains(node))body.append(node);}
    if(!body.querySelector('[data-mobile-chat-upload]')){const upload=document.createElement('button');upload.type='button';upload.className='ux-text-button';upload.dataset.mobileChatUpload='';upload.textContent=t('Rasm yuborish','Отправить фото','Send photo');upload.onclick=()=>{tools.open=false;app.querySelector('#ux-message-form input[type=file]')?.click();};body.append(upload);}
  }
  function enhanceAdmin() {
    const portal = app.querySelector('.admin-portal');
    if (!portal || portal.querySelector('[data-mobile-admin-toggle]')) return;
    const button = document.createElement('button');
    button.type = 'button'; button.className = 'mobile-admin-toggle';
    button.dataset.mobileAdminToggle = '';
    button.setAttribute('aria-expanded', 'false');
    button.innerHTML = `${icon('layers')}<span>${t('Admin bo‘limlari', 'Разделы админ-панели', 'Admin sections')}</span>${icon('chevron')}`;
    portal.prepend(button);
  }
  function enhance() {
    if (!isMobile()) return;
    enhanceHeader(); enhancePasswordReset(); enhanceAuth(); enhanceCards(); enhanceTables(); enhancePurchases(); enhanceTopUps(); enhanceBrowse(); enhanceMessages(); enhanceAdmin(); adaptAccountPage();
  }
  function sync(route) {
    const next = route || routeFromLocation();
    if (next !== currentRoute) { document.body.classList.remove('mobile-admin-open'); if (isMobile()) window.scrollTo({top:0,behavior:'instant'}); }
    currentRoute = next;
    syncNavigation(next); enhance();
  }
  function init() {
    if (initialized) return;
    initialized = true;
    sync(); showIntro();
    observer = new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => { scheduled = false; sync(); });
    });
    observer.observe(app, {childList: true, subtree: true});
    matchMedia(query).addEventListener('change', () => {
      sync();
      if (!isMobile()) {
        introTimers.forEach(clearTimeout); document.querySelector('.mobile-welcome')?.remove(); restoreIntro();
        introEligible = false;
      }
      if (sessionResolved && /^(?:account(?:\/.*)?|browse|search|notifications|orders|listing\/.*)$/.test(routeFromLocation().split('?')[0])) navigate();
    });
    document.addEventListener('click',event=>{
      if(isMobile() && event.target.closest('#mobile-search-toggle')) {event.preventDefault();event.stopImmediatePropagation();location.hash='search';}
    },true);
    document.addEventListener('click', event => {
      const language = event.target.closest('[data-mobile-site-language]');
      if (language) setLanguage(language.dataset.mobileSiteLanguage);
      const adminToggle = event.target.closest('[data-mobile-admin-toggle]');
      if (adminToggle) {
        const expanded = document.body.classList.toggle('mobile-admin-open');
        adminToggle.setAttribute('aria-expanded', String(expanded));
      }
      if (event.target.closest('[data-admin-view-target]')) {
        document.body.classList.remove('mobile-admin-open');
        document.querySelector('[data-mobile-admin-toggle]')?.setAttribute('aria-expanded', 'false');
      }
    });
  }
  return {init, sync, syncNavigation, sessionReady, isMobile, account, settings, search, menu, gamePage, listingPanel, topupReviews, cart, navHidden, navKey, orders, purchaseGroup, purchaseDate, notifications, notificationGlyph, notificationAge, registrationSubmitted, emailCheck, maskVerificationEmail, verificationStatus, matchingSearchGames};
})();

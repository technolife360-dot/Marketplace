(function () {
  const t = (uz, ru, en) => ({ uz, ru, en });
  const pick = (value, lang) => value[lang] || window.RegionPreferences?.translate?.(value.en, lang) || value.en;
  const paths = {
    '/selling':'selling', '/guide':'guide', '/fees':'fees', '/support':'support',
    '/help':'support', '/help/orders':'help/orders', '/help/payments':'help/payments',
    '/help/refunds':'help/refunds', '/help/chat':'help/chat', '/contact':'contact',
    '/terms':'terms', '/policies':'policies', '/seller-policy':'sellerPolicy',
    '/prohibited-items':'prohibited', '/refunds':'refunds', '/delivery':'delivery',
    '/disputes':'disputes', '/about':'about'
  };
  const payload = document.getElementById('public-info-content');
  const initial = payload ? JSON.parse(payload.textContent) : null;
  let library;
  let observer;

  const buy = {
    title:t('Xarid va sotuv','Покупка и продажа','Buy & Sell'),
    links:[
      ['/browse', t('E’lonlarni ko‘rish','Смотреть объявления','Browse listings')],
      ['/selling', t('Sotishni boshlash','Начать продавать','Start selling')],
      ['/top-up', t('Top Up katalogi','Каталог пополнений','Top Up catalog')],
      ['/guide', t('Xarid qanday ishlaydi','Как проходит покупка','How buying works')],
      ['/fees', t('Komissiya va to‘lovlar','Комиссии и платежи','Fees and payments')],
    ],
  };
  const help = {
    title:t('Yordam','Помощь','Help'),
    links:[
      ['/support', t('Yordam markazi','Центр поддержки','Help Center')],
      ['/help/orders', t('Buyurtma va yetkazish','Заказы и доставка','Orders and delivery')],
      ['/help/payments', t('To‘lovlar bo‘yicha yordam','Помощь по оплате','Payment support')],
      ['/help/refunds', t('Qaytarim va nizo yordami','Помощь по возвратам и спорам','Refunds and disputes')],
      ['/contact', t('Biz bilan bog‘lanish','Связаться с нами','Contact us')],
      ['/help/chat', t('Chat orqali yozish','Написать в чат','Message support')],
    ],
  };
  const trust = {
    title:t('Ishonch va qoidalar','Правила и безопасность','Trust & policies'),
    links:[
      ['/terms', t('Foydalanish shartlari','Условия использования','Terms of Service')],
      ['/policies', t('Marketplace qoidalari','Правила маркетплейса','Marketplace policies')],
      ['/seller-policy', t('Sotuvchi kelishuvi','Соглашение с продавцом','Seller Agreement')],
      ['/prohibited-items', t('Taqiqlangan mahsulotlar','Запрещённые товары','Prohibited Items')],
      ['/refunds', t('Qaytarim va bekor qilish','Возврат и отмена','Refund & Cancellation')],
      ['/delivery', t('Yetkazish siyosati','Политика доставки','Delivery Policy')],
      ['/disputes', t('Nizolarni hal qilish','Разрешение споров','Dispute & Resolution')],
      ['/privacy-policy', t('Maxfiylik siyosati','Политика конфиденциальности','Privacy Policy')],
    ],
  };

  async function load(route) {
    if (initial?.route === route) return initial;
    library ??= fetch('/static/info-pages-content.json?v=2').then(response => {
      if (!response.ok) throw new Error('Could not load the information page.');
      return response.json();
    }).catch(error => {
      library = null;
      throw error;
    });
    const content = await library;
    return { ...content, page: content.pages[route] };
  }

  function about(page, notice, lang) {
    const [topup, market, mission, vision, contact] = page.sections;
    const copy = entry => `<h3>${pick(entry.title,lang)}</h3><p>${pick(entry.paragraphs[0],lang)}</p>`;
    const icon = name => `<svg viewBox="0 0 24 24" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
    const heading = pick(page.title,lang).replace('SentryLoot','<span>SentryLoot</span>');
    const games = [
      ['pubg-mobile','PUBG Mobile'], ['mobile-legends','Mobile Legends'],
      ['free-fire','Free Fire'], ['honor-of-kings','Honor of Kings'],
    ];
    return `<div class="sl-about" data-info-route="about">
      <section class="sl-about-hero">
        <header class="sl-about-intro">
          <p class="sl-about-kicker">${pick(t('Biz haqimizda','О нас','About us'),lang)}</p>
          <h1>${heading}</h1>
          <p class="sl-about-lead">${pick(page.lead,lang)}</p>
          <a class="sl-about-button" href="#about-platform">${pick(t('Platformani ko‘ring','О платформе','Explore the platform'),lang)} <span aria-hidden="true">↓</span></a>
        </header>
        <div class="sl-about-stage">
          <div class="sl-about-showcase">
            <div class="sl-about-showcase-bar">
              <strong>Sentry<span>Loot</span></strong>
              <span class="sl-about-showcase-label">${pick(t('O‘yin katalogidan','Из игрового каталога','From the game catalog'),lang)}</span>
              <a href="/top-up">${pick(buy.links[2][1],lang)} <span aria-hidden="true">↗</span></a>
            </div>
            <div class="sl-about-art">
              <img src="/static/assets/about-controller.webp" width="1200" height="800" alt="" fetchpriority="high">
              <p>${pick(t('O‘yinlar. Paketlar. Marketplace.','Игры. Пополнения. Маркетплейс.','Games. Top Ups. Marketplace.'),lang)}</p>
            </div>
            <ul class="sl-about-games">
              ${games.map(([slug,name])=>`<li><a href="/top-up/${slug}">
                <img src="/static/assets/game-art/${slug}-640.webp" width="64" height="64" alt="">
                <span>${name}</span>
              </a></li>`).join('')}
            </ul>
          </div>
        </div>
      </section>
      <section class="sl-about-platform" id="about-platform" aria-labelledby="about-platform-title" tabindex="-1">
        <header class="sl-about-heading" data-about-reveal>
          <p class="sl-about-kicker">${pick(t('Platforma','Платформа','The platform'),lang)}</p>
          <h2 id="about-platform-title">${pick(t('SentryLoot qanday ishlaydi','Как работает SentryLoot','How SentryLoot works'),lang)}</h2>
        </header>
        <div class="sl-about-grid">
          <article class="sl-about-card" data-about-reveal>
            ${icon('search')}${copy(topup)}
            <a href="/top-up">${pick(buy.links[2][1],lang)} <span aria-hidden="true">→</span></a>
          </article>
          <article class="sl-about-card" data-about-reveal>
            ${icon('cart')}${copy(market)}
            <a href="/browse">${pick(buy.links[0][1],lang)} <span aria-hidden="true">→</span></a>
          </article>
          <article class="sl-about-card" data-about-reveal>
            ${icon('message')}<h3>${pick(help.links[0][1],lang)}</h3><p>${pick(contact.paragraphs[0],lang)}</p>
            <a href="/support">${pick(t('Yordam olish','Получить помощь','Get help'),lang)} <span aria-hidden="true">→</span></a>
          </article>
        </div>
        <p class="sl-about-status">${pick(notice,lang)}</p>
      </section>
      <section class="sl-about-purpose" id="about-purpose" aria-labelledby="about-purpose-title">
        <header class="sl-about-heading" data-about-reveal>
          <h2 id="about-purpose-title">${pick(t('Vazifamiz va maqsadimiz','Наша миссия и видение','Our mission and vision'),lang)}</h2>
        </header>
        <div class="sl-about-grid">
          <article class="sl-about-card" data-about-reveal>${icon('shield')}${copy(mission)}</article>
          <article class="sl-about-card" data-about-reveal>${icon('check')}${copy(vision)}</article>
        </div>
      </section>
      <section class="sl-about-contact" id="about-contact" aria-labelledby="about-contact-title" data-about-reveal>
        <h2 id="about-contact-title">${pick(contact.title,lang)}</h2>
        <p>${pick(contact.paragraphs[0],lang)}</p>
        <div class="sl-about-contact-links">
          <a class="sl-about-button" href="/contact">${pick(help.links[4][1],lang)} <span aria-hidden="true">→</span></a>
          <a class="sl-about-email" href="mailto:sentryloot@gamestorehub.com">sentryloot@gamestorehub.com</a>
        </div>
      </section>
    </div>`;
  }

  function render(data, lang) {
    const {page, salesNotice, publisherRules} = data;
    if (page.path === '/about') return about(page, salesNotice, lang);
    const group = buy.links.some(([path])=>path===page.path) ? buy : help.links.some(([path])=>path===page.path) ? help : trust;
    const sections = page.sections.map((entry, index)=>({ ...entry, id:entry.id || `info-section-${index+1}` }));
    if (publisherRules) {
      sections.push({
        id:`info-section-${sections.length+1}`,
        title:t('Rasmiy noshir qoidalari','Официальные правила издателей','Official publisher rules'),
        paragraphs:[],
        bullets:publisherRules.map(([name,url,description])=>`<a href="${url}" target="_blank" rel="noopener noreferrer">${name}</a> · ${pick(description,lang)}`),
      });
    }
    const topicNav = group.links.map(([path,title])=>`<a href="${path}"${path===page.path?' aria-current="page"':''}>${pick(title,lang)}</a>`).join('');
    const related = group===help ? ['/refunds','/delivery','/disputes'] : ['/support','/contact'];
    const relatedLinks = [...help.links,...trust.links].filter(([path])=>related.includes(path) && path!==page.path);
    const headings = sections.map(section=>`<a href="#${section.id}">${pick(section.title,lang)}</a>`).join('');
    return `<div class="page info-page info-page-layout" data-info-route="${paths[page.path]}">
      <header class="info-page-header"><p class="info-category">${pick(group.title,lang)}</p>
        <h1 class="page-title">${pick(page.title,lang)}</h1><p>${pick(page.lead,lang)}</p></header>
      <div class="info-page-grid">
        <nav class="info-topics" aria-label="${pick(group.title,lang)}">${topicNav}</nav>
        <article class="legal-copy">
          ${page.showSalesNotice?`<p class="notice warn">${pick(salesNotice,lang)}</p>`:''}
          <nav class="info-contents" aria-label="${pick(t('Shu sahifada','На этой странице','On this page'),lang)}">${headings}</nav>
          ${sections.map(section=>`<section class="info-section" id="${section.id}" tabindex="-1">
            <h2>${pick(section.title,lang)}</h2>
            ${section.paragraphs.map(text=>`<p>${pick(text,lang)}</p>`).join('')}
            ${section.bullets.length?`<ul>${section.bullets.map(text=>`<li>${typeof text==='string'?text:pick(text,lang)}</li>`).join('')}</ul>`:''}
          </section>`).join('')}
          ${page.action?`<p><a class="button-primary" href="/contact" data-open-support-chat>${pick(page.action,lang)}</a></p>`:''}
          <p class="info-related">${relatedLinks.map(([path,title])=>`<a href="${path}">${pick(title,lang)}</a>`).join('')}</p>
        </article>
      </div>
    </div>`;
  }

  function activate(root) {
    if (!root.querySelector('.sl-about') || !('IntersectionObserver' in window)
      || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        observer.unobserve(entry.target);
        entry.target.classList.add('sl-about-revealed');
      }
    }, { threshold:0.12 });
    root.querySelectorAll('[data-about-reveal]').forEach(element=>observer.observe(element));
  }

  function stop() {
    observer?.disconnect();
    observer = null;
  }

  window.SENTRYLOOT_INFO_PAGES = { paths, load, render, activate, stop };
})();

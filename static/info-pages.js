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
  let motionEngine;
  let aboutMotion;
  let motionVersion = 0;

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
    library ??= fetch('/static/info-pages-content.json?v=5').then(response => {
      if (!response.ok) throw new Error('Could not load the information page.');
      return response.json();
    }).catch(error => {
      library = null;
      throw error;
    });
    const content = await library;
    return { ...content, page: content.pages[route] };
  }

  function about(page, lang) {
    const sections = Object.fromEntries(page.sections.map(section=>[section.id,section]));
    const title = id => pick(sections[id].title,lang);
    const paragraph = id => `<p>${pick(sections[id].paragraphs[0],lang)}</p>`;
    const copy = id => `<h3>${title(id)}</h3>${paragraph(id)}`;
    const link = (href, label) => `<a class="sl-about-link" href="${href}">${label} <span aria-hidden="true">↗</span></a>`;
    const button = (href, label, arrow) => `<a class="sl-about-button" href="${href}">${label} <span aria-hidden="true">${arrow}</span></a>`;
    const marketplace = pick(t('Marketplace qanday ishlaydi','Как работает площадка','How the marketplace works'),lang);
    const trustTitle = pick(t('Qoidalar va xavfsizlik','Правила и безопасность','Rules and safety'),lang);
    const contact = pick(help.links[4][1],lang);
    const payments = sections['about-payments'];
    const paymentIcons = {
      card: '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18M7 15h4"/>',
      device: '<rect x="6" y="2" width="12" height="20" rx="3"/><path d="m9 11 2 2 4-4m-4 9h2"/>',
      google: '<rect x="3" y="5" width="18" height="13" rx="2"/><path d="M3 9h18m-11 5 2 2 4-4"/>',
      bank: '<path d="M3 9h18L12 3 3 9Zm0 12h18M6 12v6m6-6v6m6-6v6"/>',
      wallet: '<path d="M21 10V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-3m-5-2h.01"/><path d="M16 10h5v4h-5a2 2 0 1 1 0-4Z"/>',
      link: '<path d="m13 2-9 12h7l-1 8 9-12h-7l1-8Z"/>',
    };
    const heading = pick(page.title,lang).replace('SentryLoot','<span>SentryLoot</span>');
    return `<div class="sl-about" data-info-route="about">
      <section class="sl-about-hero" aria-labelledby="about-title">
        <div class="sl-about-scene" aria-hidden="true">
          <img src="/static/assets/about-orbit.webp" width="1440" height="960" alt="" fetchpriority="high" data-about-depth>
        </div>
        <div class="sl-about-hero-inner">
          <nav class="sl-about-nav" aria-label="${pick(page.metadataTitle||page.title,lang)}">
            <a href="#about-purpose">${title('about-purpose')}</a>
            <a href="#about-platform">Marketplace</a>
            <a href="#about-trust">${pick(t('Qoidalar','Правила','Rules'),lang)}</a>
            <a href="#about-payments">${pick(t('To‘lovlar','Оплата','Payments'),lang)}</a>
            <a href="#about-contact">${contact}</a>
          </nav>
          <div class="sl-about-intro">
            <h1 id="about-title" data-about-intro>${heading}</h1>
            <p class="sl-about-lead" data-about-intro>${pick(page.lead,lang)}</p>
            <div class="sl-about-actions" data-about-intro>
              ${button('#about-purpose',title('about-purpose'),'↓')}
            </div>
          </div>
        </div>
      </section>

      <section class="sl-about-purpose" id="about-purpose" aria-labelledby="about-purpose-title" tabindex="-1">
        <header data-about-reveal><h2 id="about-purpose-title">${title('about-purpose')}</h2>${paragraph('about-purpose')}</header>
        <div class="sl-about-principles">
          <article data-about-reveal>${copy('mission')}</article>
          <article data-about-reveal>${copy('vision')}</article>
        </div>
      </section>

      <section class="sl-about-platform" id="about-platform" aria-labelledby="about-platform-title" tabindex="-1">
        <header class="sl-about-heading" data-about-reveal><h2 id="about-platform-title">${marketplace}</h2></header>
        <div class="sl-about-grid">
          <article class="sl-about-card" data-about-reveal>
            ${copy('about-platform')}
            ${link('/guide',pick(buy.links[3][1],lang))}
          </article>
          <article class="sl-about-card" data-about-reveal>
            ${copy('sellers')}
            ${link('/seller-policy',pick(trust.links[2][1],lang))}
          </article>
          <article class="sl-about-card" data-about-reveal>
            ${copy('support')}
            ${link('/disputes',pick(trust.links[6][1],lang))}
          </article>
        </div>
      </section>

      <section class="sl-about-trust" id="about-trust" aria-labelledby="about-trust-title" tabindex="-1">
        <header data-about-reveal><h2 id="about-trust-title">${trustTitle}</h2></header>
        <div class="sl-about-principles">
          <article data-about-reveal>${copy('about-trust')}${link('/policies',pick(trust.links[1][1],lang))}</article>
          <article data-about-reveal>${copy('payments')}${link('/help/payments',pick(help.links[2][1],lang))}</article>
        </div>
      </section>

      <section class="sl-about-payments" id="about-payments" aria-labelledby="about-payments-title" tabindex="-1">
        <div class="sl-payment-inner">
        <header data-about-reveal>
          <h2 id="about-payments-title">${title('about-payments')}</h2>
          ${paragraph('about-payments')}
        </header>
        <div class="sl-payment-grid">
          ${payments.methods.map(method => `<article class="sl-payment-card" data-about-reveal>
            <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paymentIcons[method.icon]}</svg>
            <h3>${pick(method.title,lang)}</h3>
            <p>${pick(method.description,lang)}</p>
          </article>`).join('')}
        </div>
        <ul class="sl-payment-brands" role="list" data-about-reveal>
          ${payments.methods.flatMap(method => method.brands).map(brand => `<li><img src="/static/assets/payment-brands/${brand.toLowerCase().replaceAll(' ','-')}.svg?v=2" width="108" height="32" loading="lazy" decoding="async" alt="${brand}"></li>`).join('')}
        </ul>
        <p class="sl-payment-status">${pick(payments.status,lang)}</p>
        </div>
      </section>

      <section class="sl-about-contact" id="about-contact" aria-labelledby="about-contact-title" tabindex="-1" data-about-reveal>
        <div>
          <h2 id="about-contact-title">${title('about-contact')}</h2>
          ${paragraph('about-contact')}
        </div>
        <div class="sl-about-actions">
          ${button('/contact',contact,'↗')}
          <a class="sl-about-email" href="mailto:sentryloot@gamestorehub.com">sentryloot@gamestorehub.com</a>
        </div>
      </section>
    </div>`;
  }

  function render(data, lang) {
    const {page, salesNotice, publisherRules} = data;
    if (page.path === '/about') return about(page, lang);
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

  function loadMotion() {
    motionEngine ??= new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '/static/vendor/gsap-scrolltrigger-3.14.2.min.js';
      script.onload = () => {
        if (window.gsap && window.ScrollTrigger) resolve(window.gsap);
        else reject();
      };
      script.onerror = reject;
      document.head.append(script);
    });
    return motionEngine;
  }

  async function activate(root) {
    const page = root.querySelector('.sl-about');
    if (!page || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const version = ++motionVersion;
    const gsap = await loadMotion().catch(()=>null);
    if (!gsap || version !== motionVersion || !page.isConnected) return;
    gsap.registerPlugin(window.ScrollTrigger);
    aboutMotion = gsap.matchMedia(page);
    aboutMotion.add({
      play: '(prefers-reduced-motion: no-preference)',
      wide: '(min-width: 741px)',
    }, ({ conditions, selector }) => {
      if (!conditions.play) return;
      const hero = selector('.sl-about-hero')[0];
      if (hero.getBoundingClientRect().top >= -30) {
        gsap.from(selector('[data-about-intro]'), { y:15, opacity:.55, duration:.85, stagger:.075, ease:'power3.out' });
      }
      if (conditions.wide) {
        gsap.fromTo(selector('[data-about-depth]'), { scale:1.035 }, {
          scale:1.13, yPercent:4, ease:'none',
          scrollTrigger:{ trigger:hero, start:'top top', end:'bottom top', scrub:.7 },
        });
      }
      for (const [index, element] of selector('[data-about-reveal]').entries()) {
        gsap.from(element, {
          y:conditions.wide?20:12, opacity:.62, duration:.75, delay:(index%3)*.055, ease:'power3.out',
          scrollTrigger:{ trigger:element, start:'top 92%', once:true },
        });
      }
    });
  }

  function stop() {
    motionVersion++;
    aboutMotion?.revert();
    aboutMotion = null;
  }

  window.SENTRYLOOT_INFO_PAGES = { paths, load, render, activate, stop };
})();

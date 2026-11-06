async function loadHomeTopups(host) {
  if (!host) return;
  const t = (uz, ru, en) => adminText(uz, ru, en);
  host.setAttribute('aria-busy', 'true');
  try {
    const rows = await api('/top-up/home');
    if (!host.isConnected) return;
    host.innerHTML = rows.length ? '<div class="home-topup-grid">' + rows.map(item => {
      const subtitle = item.subtitle === 'Diamonds' ? t('Olmoslar', 'Алмазы', 'Diamonds') : item.subtitle;
      return `<a class="home-topup-card" href="/top-up/${encodeURIComponent(item.slug)}"><span class="home-topup-art"><img src="${esc(item.image_url)}" alt="" width="${Number(item.image_width)}" height="${Number(item.image_height)}" loading="lazy" decoding="async"></span><span class="home-topup-copy"><strong>${esc(item.name)}</strong><span class="home-topup-bottom"><span>${esc(subtitle)}</span><span aria-hidden="true">→</span></span></span></a>`;
    }).join('') + '</div>' : `<p class="help">${t('Hozircha top-uplar yo‘q.','Пополнений пока нет.','No top ups available yet.')}</p>`;
  } catch (_) {
    if (!host.isConnected) return;
    host.innerHTML = `<div class="notice error" role="alert">${t('Top-uplarni yuklab bo‘lmadi.','Не удалось загрузить пополнения.','Could not load top ups.')} <button class="button-secondary" type="button" data-home-topups-retry>${t('Qayta urinish','Повторить','Try again')}</button></div>`;
    host.querySelector('[data-home-topups-retry]').onclick = () => loadHomeTopups(host);
  } finally {
    if (host.isConnected) host.setAttribute('aria-busy', 'false');
  }
}

const TOPUP_CATALOG_IMAGE_FALLBACKS = {
  "h2h-5307-free-fire-max-global-13": "https://play-lh.googleusercontent.com/M_l-dWl4q9FLX3IgYu8lrSPAs6WrMiL2gPxzYwehWAsfFpOVOSG-APyLkUkJn8Og_uHXw_qv5K351Dyy4pmqoQ=s512-rw",
  "h2h-5388-solo-leveling-arise-drop-link-13": "https://cdn.melostore.id/uploads/catalog/thumbnails/solo-leveling-arise-auto-via-login-20261027.webp",
  "h2h-5348-solo-leveling-arise-10-2": "https://cdn.melostore.id/uploads/catalog/thumbnails/solo-leveling-arise-auto-via-login-20261027.webp",
  "h2h-5539-umamusume-pretty-derby-drop-link-13": "https://cdn.melostore.id/uploads/catalog/thumbnails/umamusume-pretty-derby-20261027.webp",
  "h2h-5573-whiteout-survival-6": "https://cdn.melostore.id/uploads/catalog/thumbnails/whiteout-survival-manual-20261028.webp",
  "h2h-5428-tarisland-14-2": "https://shared.fastly.steamstatic.com/store_item_assets/steam/apps/3126180/header.jpg",
  "h2h-5479-the-seven-deadly-sins-drop-link-13-2": "https://is1-ssl.mzstatic.com/image/thumb/PurpleSource221/v4/6c/fd/65/6cfd6551-746a-7914-24cd-05c61b5eaff8/Placeholder.mill/1200x630wa.jpg",
  "h2h-5541-x-clash-13": "https://play-lh.googleusercontent.com/ENd_7tg4X0CHk76h_QJs6sHPTTQf9Y40Xwc7eRqUigGdpLAXYtvNi13DTGcpAd4ft9WHC8pdjgCA-6TIcT2H=s0-br30",
  "h2h-2520-tungkal-fight-night-ticket-12": "data:image/svg+xml,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%22512%22%20height%3D%22512%22%20viewBox%3D%220%200%20512%20512%22%3E%3Cdefs%3E%3ClinearGradient%20id%3D%22g%22%20x2%3D%221%22%20y2%3D%221%22%3E%3Cstop%20stop-color%3D%22%23592620%22%2F%3E%3Cstop%20offset%3D%221%22%20stop-color%3D%22%2316161e%22%2F%3E%3C%2FlinearGradient%3E%3C%2Fdefs%3E%3Cpath%20fill%3D%22url%28%23g%29%22%20d%3D%22M0%200h512v512H0z%22%2F%3E%3Cg%20fill%3D%22none%22%20stroke%3D%22%23f3ba69%22%20stroke-width%3D%225%22%3E%3Cpath%20d%3D%22M100%20130h312v60a32%2032%200%20000%2064v60H100v-60a32%2032%200%20000-64z%22%2F%3E%3Cpath%20d%3D%22M325%20143v158%22%20stroke-dasharray%3D%228%2010%22%2F%3E%3Cpath%20d%3D%22m155%20200%2036-28%2036%2028-12%2042h-48z%22%2F%3E%3Cpath%20d%3D%22M191%20172v-20m-25%2091-13%2030m62-30%2013%2030%22%2F%3E%3C%2Fg%3E%3Cg%20fill%3D%22%23f3ba69%22%20font-family%3D%22Arial%2Csans-serif%22%20text-anchor%3D%22middle%22%20font-weight%3D%22700%22%3E%3Ctext%20x%3D%22256%22%20y%3D%22370%22%20font-size%3D%2237%22%3ETUNGKAL%3C%2Ftext%3E%3Ctext%20x%3D%22256%22%20y%3D%22410%22%20font-size%3D%2227%22%20letter-spacing%3D%224%22%3EFIGHT%20NIGHT%3C%2Ftext%3E%3Ctext%20x%3D%22256%22%20y%3D%22449%22%20font-size%3D%2216%22%20letter-spacing%3D%225%22%3ETICKET%3C%2Ftext%3E%3C%2Fg%3E%3C%2Fsvg%3E"
};

const TOPUP_CATEGORIES = [
  ['all', 'Barchasi', 'Все', 'All'],
  ['game', 'O‘yin', 'Игра', 'Game'],
  ['gift-card', 'Sovg‘a kartasi', 'Подарочная карта', 'Gift card'],
  ['social', 'Ijtimoiy tarmoqlar', 'Социальные сети', 'Social media'],
  ['ewallet', 'Elektron hamyon', 'Электронный кошелёк', 'E-wallet'],
  ['airtime-data', 'Mobil aloqa va internet', 'Мобильная связь и интернет', 'Airtime & data'],
  ['pln', 'PLN', 'PLN', 'PLN'],
  ['apps-subscriptions', 'Ilovalar va obunalar', 'Приложения и подписки', 'Apps & subscriptions']
];

function topupCategory(item) {
  const value = String(item.category_slug || item.category || 'game').trim().toLowerCase().replace(/[ _]+/g, '-');
  const aliases = {'games':'game', 'gift-cards':'gift-card', 'e-wallet':'ewallet', 'pulsa':'airtime-data', 'data':'airtime-data', 'pulsa-&-data':'airtime-data', 'airtime-&-data':'airtime-data', 'aplikasi-&-langganan':'apps-subscriptions'};
  return aliases[value] || value;
}

function topupApplyFilters(page) {
  const category = page.dataset.activeTopupCategory || 'all';
  const query = (page.dataset.topupQuery || '').trim().toLocaleLowerCase();
  const limit = Number(page.dataset.topupLimit) || 48;
  const cards = [...page.querySelectorAll('[data-topup-category-card]')];
  let matched = 0;
  cards.forEach(card => {
    const matches = (category === 'all' || card.dataset.topupCategoryCard === category) && card.querySelector('h2').textContent.toLocaleLowerCase().includes(query);
    card.hidden = !matches || matched >= limit;
    if (matches) matched++;
  });
  const empty = page.querySelector('[data-topup-category-empty]');
  if (empty) {
    empty.hidden = matched > 0;
    empty.textContent = query
      ? adminText('Mos mahsulot topilmadi.', 'Подходящих товаров не найдено.', 'No matching products found.')
      : adminText('Bu kategoriyada hozircha mahsulotlar yo‘q.', 'В этой категории пока нет товаров.', 'No products in this category yet.');
  }
  const count = page.querySelector('[data-topup-result-count]');
  if (count) count.textContent = adminText(matched + ' ta mahsulot', matched + ' товаров', matched + ' products');
  const more = page.querySelector('[data-topup-load-more]');
  if (more) more.hidden = matched <= limit;
}

function topupCatalogCard(item, index) {
  const source = item.image_url || TOPUP_CATALOG_IMAGE_FALLBACKS[item.slug] || TOPUP_OFFICIAL_GAME_ART[item.slug];
  const mobileArt = TOPUP_MOBILE_GAME_ART[item.slug];
  const fallback = TOPUP_OFFICIAL_GAME_ART[item.slug] ? 'https://images.gamestorehub.com/site-assets/topup-' + item.slug + '.svg' : '';
  const backdrop = source ? '<img class="topup-card-backdrop" src="' + esc(source) + '" alt="" aria-hidden="true" loading="lazy" decoding="async">' : '';
  const picture = source ? '<picture>' + (mobileArt ? '<source media="(max-width:840px)" srcset="/static/assets/' + mobileArt + '">' : '') + '<img ' + (fallback ? 'data-topup-fallback="' + fallback + '" ' : 'data-topup-hide-error ') + 'src="' + esc(source) + '" alt="' + esc(item.name) + '" loading="' + (index < 2 ? 'eager' : 'lazy') + '" decoding="async"></picture>' : '';
  return '<article data-topup-category-card="' + esc(topupCategory(item)) + '" class="topup-game-card topup-game-' + esc(item.slug) + '"><a class="topup-game-cover" href="/top-up/' + encodeURIComponent(item.slug) + '" aria-label="' + esc(item.name) + '"><span class="topup-cover-placeholder" aria-hidden="true">' + topupGameIcon(item.slug) + '</span>' + backdrop + picture + '<span class="topup-game-cover-shade"></span></a><div class="topup-game-card-body"><h2 title="' + esc(item.name) + '">' + esc(item.name) + '</h2>' + (item.review_summary?.count ? '<span class="pr-card-rating">★ ' + Number(item.review_summary.rating).toFixed(1) + ' <small>(' + Number(item.review_summary.count) + ')</small></span>' : '') + '<a class="topup-game-cta" href="/top-up/' + encodeURIComponent(item.slug) + '">Top Up</a></div></article>';
}

function topupSupplierTypeIcon(name) {
  const kinds = {
    uc:'wallet', coins:'coins', diamonds:'gem', tokens:'gem', gems:'gem',
    crystals:'gem', shop:'cart', 'battle pass':'ticket', 'first top-up bonus':'star'
  };
  const type = name.trim().toLowerCase();
  return icon(Object.hasOwn(kinds,type) ? kinds[type] : 'box','tus-type-icon');
}

function topupSupplierGroups(packages, slug = '') {
  const collator = new Intl.Collator('en', {numeric:true, sensitivity:'base'});
  const amount = label => {
    const expression = String(label || '').match(/\d[\d.,]*(?:\s*\+\s*\d[\d.,]*)*/);
    if (!expression) return Infinity;
    return expression[0].split('+').reduce((total, value) => {
      const normalized = value.trim().replace(/[.,](?=\d{3}(?:[.,]|$))/g, '').replace(',', '.');
      return total + Number(normalized);
    }, 0);
  };
  const groups = new Map(), seen = new Set();
  packages.forEach((pack, index) => {
    if (pack.status !== 'active') return;
    const originalType = String(pack.type_name || '').trim() || 'Other';
    const name = slug === 'pubg-mobile' && ['Prime','Prime Plus','Weekly Deal Pack','Mythic Emblem Pack','Weekly Mythic Emblem Value Pack','Upgradable Firearm Materials Pack','First Purchase Pack'].includes(originalType) ? 'Shop' : originalType;
    const identity = JSON.stringify([originalType, String(pack.name || '').normalize('NFKC').trim().replace(/\s+/g, ' ').toLocaleLowerCase()]);
    if (seen.has(identity)) return;
    seen.add(identity);
    if (!groups.has(name)) groups.set(name, {name, items: []});
    groups.get(name).items.push({pack, index});
  });
  for (const group of groups.values()) {
    group.items.sort((a, b) => (group.name === 'Shop' ? (['Prime','Prime Plus','Weekly Deal Pack','Mythic Emblem Pack','Weekly Mythic Emblem Value Pack','Upgradable Firearm Materials Pack','First Purchase Pack'].indexOf(a.pack.type_name) - ['Prime','Prime Plus','Weekly Deal Pack','Mythic Emblem Pack','Weekly Mythic Emblem Value Pack','Upgradable Firearm Materials Pack','First Purchase Pack'].indexOf(b.pack.type_name)) : 0) || amount(a.pack.name) - amount(b.pack.name) || collator.compare(a.pack.name, b.pack.name));
  }
  const result = [...groups.values()];
  return slug === 'pubg-mobile' ? result : result.sort((a,b)=>Number(a.name==='Shop')-Number(b.name==='Shop'));
}

function topupSupplierPresentationPackages(slug, packages) {
  const normalized = packages.map(pack => ({...pack,
    name: String(pack.name || '').replace(/\bunknown\s+cash\b/gi, 'UC'),
    type_name: String(pack.type_name || '').replace(/\bunknown\s+cash\b/gi, 'UC')
  }));
  if (slug !== 'pubg-mobile') return normalized.map(pack => {
    const bonus = /first[ -]*top[ -]*up bonus/i.test(pack.name + ' ' + pack.type_name);
    const shop = /pass|membership|subscription|bundle|pack/i.test(pack.type_name + ' ' + pack.name);
    return {...pack, type_name:bonus ? 'First Top-Up Bonus' : shop ? 'Shop' : pack.type_name};
  });
  const ucLabels = new Map([
    [60, '60 UC'], [120, '120 UC'], [325, '300 + 25 UC'],
    [660, '600 + 60 UC'], [1800, '1500 + 300 UC'], [3850, '3000 + 850 UC'],
    [8100, '6000 + 2100 UC'], [16200, '12000 + 4200 UC'],
    [24300, '18000 + 6300 UC'], [32400, '24000 + 8400 UC'],
    [40500, '30000 + 10500 UC']
  ]);
  const preferredSkus = new Map([[60, 'pubgmgl60eu-s2'], [325, 'pubgmgl325u-s7'], [660, 'pubgmgl660u-s7'], [1800, 'pubgmgl1800u-s7'], [3850, 'pubgmgl3850u-s7'], [8100, 'pubgmgl8100uco-s11'], [16200, 'pubgmgl16200uco-s11'], [24300, 'pubgmgl24300uco-s11'], [32400, 'pubgmgl32400uco-s11'], [40500, 'pubgmgl40500uco-s11']]);
  const usdPrices = new Map([
    [60, 99], [120, 198], [325, 499], [660, 899], [1800, 2499],
    [3850, 4999], [8100, 9999], [16200, 18999], [24300, 28999],
    [32400, 37999], [40500, 46999]
  ]);
  const passPrices = new Map([
    ['pubgmel5ucbp-s101', 549], ['pubgmel1ucbp-s101', 1079], ['pubgmepl1ucbp-s10', 2699]
  ]);
  const coinOffers = new Map([
  [
    "pubgm60wc-s101",
    {
      "name": "60 Coins",
      "selling_price_cents": 99,
      "selling_currency": "USD",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/coins-60-5231f32f578dd31be5e9.png"
    }
  ],
  [
    "pubgm325wc-s101",
    {
      "name": "300 + 25 Coins",
      "selling_price_cents": 499,
      "selling_currency": "USD",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/coins-325-916657fcdb871e747524.png"
    }
  ],
  [
    "pubgm660wc-s101",
    {
      "name": "600 + 60 Coins",
      "selling_price_cents": 999,
      "selling_currency": "USD",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/coins-660-f068e3cb6acf706322bd.png"
    }
  ],
  [
    "pubgm1800wc-s101",
    {
      "name": "1500 + 300 Coins",
      "selling_price_cents": 2499,
      "selling_currency": "USD",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/coins-1800-bebb53489b8dd64f309e.png"
    }
  ],
  [
    "pubgm3850wc-s101",
    {
      "name": "3000 + 850 Coins",
      "selling_price_cents": 4999,
      "selling_currency": "USD",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/coins-3850-b19a39c804ac5fe51bf3.png"
    }
  ],
  [
    "pubgm8100wc-s101",
    {
      "name": "6000 + 2100 Coins",
      "selling_price_cents": 9999,
      "selling_currency": "USD",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/coins-8100-7dc96560e8d1673eaef1.png"
    }
  ]
]);
  const firstPurchase = {"membership":true,
  "display_name": "First Purchase Pack",
  "max_quantity": 1,
  "selling_price_cents": 89,
  "selling_currency": "USD",
  "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png",
  "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-banner-25b1d7baf26e989de845.png",
  "included_items": [
    {
      "name": "100 AG",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-ag-6ead67d5a5c1a99a842e.png"
    },
    {
      "name": "90 UC",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
    }
  ]
};
  const mythicEmblem = {
  "open_detail": true,
  "membership": true,
  "display_name": "Mythic Emblem Pack",
  "selling_price_cents": 445,
  "selling_currency": "USD",
  "max_quantity": 1,
  "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/mythic-emblem-fragment-8a815edf1aeff4101f97.png",
  "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/mythic-emblem-banner-d5ae588db8e3818af980.png",
  "included_items": [
    {
      "name": "15 Mythic Emblem Fragment",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/mythic-emblem-fragment-8a815edf1aeff4101f97.png"
    },
    {
      "name": "300 UC",
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/mythic-emblem-uc-f27f18c82b7625431641.png"
    }
  ],
  "description": {
    "en": "Mythic Emblem Pack, limited to one purchase per UID. Get 300 UC and 15 Mythic Emblem Fragments immediately upon purchase. Other rewards can be claimed daily in the game's Special Offers tab - Growth Pack.",
    "uz": "Mythic Emblem Pack har bir UID uchun bir marta olinadi. Xariddan so‘ng darhol 300 UC va 15 Mythic Emblem Fragment beriladi. Qolgan mukofotlarni o‘yindagi Special Offers → Growth Pack bo‘limidan har kuni olish mumkin.",
    "ru": "Mythic Emblem Pack доступен один раз для каждого UID. После покупки сразу начисляются 300 UC и 15 Mythic Emblem Fragments. Остальные награды можно получать ежедневно в разделе Special Offers → Growth Pack в игре."
  }
};
  const memberships = new Map([
  [
    "pubgmmucp-s101",
    {
      "membership": true,
      "display_name": "Prime (1 Month)",
      "name": "Prime (1 Month)",
      "selling_price_cents": 89,
      "selling_currency": "USD",
      "max_quantity": 1,
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-1-34d12468569003f0f658.png",
      "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-1-34d12468569003f0f658.png",
      "included_items": [
        {
          "name": "60 UC",
          "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
        }
      ],
      "description": {
        "en": "Prime (1 Month): get 60 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks.",
        "uz": "Prime (1 Month): get 60 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks.",
        "ru": "Prime (1 Month): get 60 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks."
      }
    }
  ],
  [
    "pubgmmucpb-s101",
    {
      "membership": true,
      "display_name": "Prime (3 Months)",
      "name": "Prime (3 Months)",
      "selling_price_cents": 269,
      "selling_currency": "USD",
      "max_quantity": 1,
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-3-f165feecab750e7bd24c.png",
      "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-3-f165feecab750e7bd24c.png",
      "included_items": [
        {
          "name": "180 UC",
          "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
        }
      ],
      "description": {
        "en": "Prime (3 Months): get 180 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks.",
        "uz": "Prime (3 Months): get 180 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks.",
        "ru": "Prime (3 Months): get 180 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks."
      }
    }
  ],
  [
    "pubgmmucpc-s101",
    {
      "membership": true,
      "display_name": "Prime (6 Months)",
      "name": "Prime (6 Months)",
      "selling_price_cents": 539,
      "selling_currency": "USD",
      "max_quantity": 1,
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-6-6b4cbbaae7ba38202fff.png",
      "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-6-6b4cbbaae7ba38202fff.png",
      "included_items": [
        {
          "name": "360 UC",
          "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
        }
      ],
      "description": {
        "en": "Prime (6 Months): get 360 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks.",
        "uz": "Prime (6 Months): get 360 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks.",
        "ru": "Prime (6 Months): get 360 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks."
      }
    }
  ],
  [
    "pubgmmucpa-s101",
    {
      "membership": true,
      "display_name": "Prime (12 Months)",
      "name": "Prime (12 Months)",
      "selling_price_cents": 1079,
      "selling_currency": "USD",
      "max_quantity": 1,
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-12-43481d7fc3f6bb30fba2.png",
      "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-12-43481d7fc3f6bb30fba2.png",
      "included_items": [
        {
          "name": "720 UC",
          "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
        }
      ],
      "description": {
        "en": "Prime (12 Months): get 720 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks.",
        "uz": "Prime (12 Months): get 720 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks.",
        "ru": "Prime (12 Months): get 720 UC immediately. Claim 3 UC and 5 RP daily during the subscription. See the banner for subscription perks."
      }
    }
  ],
  [
    "pubgmmucpp-s101",
    {
      "membership": true,
      "display_name": "Prime Plus (1 Month)",
      "name": "Prime Plus (1 Month)",
      "selling_price_cents": 899,
      "selling_currency": "USD",
      "max_quantity": 1,
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-plus-1-0cfeb3cc329cd12739c0.png",
      "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-plus-1-0cfeb3cc329cd12739c0.png",
      "included_items": [
        {
          "name": "660 UC",
          "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
        },
        {
          "name": "300 RP",
          "symbol": "RP"
        }
      ],
      "description": {
        "en": "Prime Plus (1 Month): get 660 UC and 300 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks.",
        "uz": "Prime Plus (1 Month): get 660 UC and 300 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks.",
        "ru": "Prime Plus (1 Month): get 660 UC and 300 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks."
      }
    }
  ],
  [
    "pubgmmucppb-s101",
    {
      "membership": true,
      "display_name": "Prime Plus (3 Months)",
      "name": "Prime Plus (3 Months)",
      "selling_price_cents": 2699,
      "selling_currency": "USD",
      "max_quantity": 1,
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-plus-3-355292a57613d4e40850.png",
      "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-plus-3-355292a57613d4e40850.png",
      "included_items": [
        {
          "name": "1980 UC",
          "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
        },
        {
          "name": "900 RP",
          "symbol": "RP"
        }
      ],
      "description": {
        "en": "Prime Plus (3 Months): get 1980 UC and 900 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks.",
        "uz": "Prime Plus (3 Months): get 1980 UC and 900 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks.",
        "ru": "Prime Plus (3 Months): get 1980 UC and 900 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks."
      }
    }
  ],
  [
    "pubgmmucppc-s101",
    {
      "membership": true,
      "display_name": "Prime Plus (6 Months)",
      "name": "Prime Plus (6 Months)",
      "selling_price_cents": 5399,
      "selling_currency": "USD",
      "max_quantity": 1,
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-plus-6-f0810a36c9c072a6011b.png",
      "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-plus-6-f0810a36c9c072a6011b.png",
      "included_items": [
        {
          "name": "3960 UC",
          "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
        },
        {
          "name": "1800 RP",
          "symbol": "RP"
        }
      ],
      "description": {
        "en": "Prime Plus (6 Months): get 3960 UC and 1800 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks.",
        "uz": "Prime Plus (6 Months): get 3960 UC and 1800 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks.",
        "ru": "Prime Plus (6 Months): get 3960 UC and 1800 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks."
      }
    }
  ],
  [
    "pubgmmucppa-s101",
    {
      "membership": true,
      "display_name": "Prime Plus (12 Months)",
      "name": "Prime Plus (12 Months)",
      "selling_price_cents": 10799,
      "selling_currency": "USD",
      "max_quantity": 1,
      "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-plus-12-fe0a0c7c55aed4f293f3.png",
      "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/membership-prime-plus-12-fe0a0c7c55aed4f293f3.png",
      "included_items": [
        {
          "name": "7920 UC",
          "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-uc-f27f18c82b7625431641.png"
        },
        {
          "name": "3600 RP",
          "symbol": "RP"
        }
      ],
      "description": {
        "en": "Prime Plus (12 Months): get 7920 UC and 3600 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks.",
        "uz": "Prime Plus (12 Months): get 7920 UC and 3600 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks.",
        "ru": "Prime Plus (12 Months): get 7920 UC and 3600 RP immediately. Claim 8 UC, 10 RP and 50 AG daily during the subscription. See the banner for subscription perks."
      }
    }
  ]
]);
  const firearmMaterials = {"membership":true,"selling_price_cents":269,"selling_currency":"USD","display_name": "Upgradable Firearm Materials Pack", "max_quantity": 1, "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/firearm-materials-material-c272ba6c040945c5f323.png", "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/firearm-materials-banner-4b759c34102a30282f79.png", "included_items": [{"name": "100 UC", "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/firearm-materials-uc-f27f18c82b7625431641.png"}, {"name": "1 Modification Material Piece", "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/firearm-materials-material-c272ba6c040945c5f323.png"}], "description": {"en": "Upgradable Firearm Materials Pack, limited to one purchase per UID. Get 100UC and Modification Material Piece ×1 immediately upon purchase. Other rewards can be claimed daily in the game's Special Offers tab - Growth Pack.", "uz": "Upgradable Firearm Materials Pack, limited to one purchase per UID. Get 100UC and Modification Material Piece ×1 immediately upon purchase. Other rewards can be claimed daily in the game's Special Offers tab - Growth Pack.", "ru": "Upgradable Firearm Materials Pack, limited to one purchase per UID. Get 100UC and Modification Material Piece ×1 immediately upon purchase. Other rewards can be claimed daily in the game's Special Offers tab - Growth Pack."}};
  const weeklyMythic = {"open_detail": true, "membership": true, "name": "Weekly Mythic Emblem Value Pack", "display_name": "Weekly Mythic Emblem Value Pack", "selling_price_cents": 269, "selling_currency": "USD", "max_quantity": 1, "image_url": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/weekly-mythic-pack-416254d25e35f8df0ed5.png", "detail_banner": "https://images.gamestorehub.com/site-assets/topup/pubg-mobile/weekly-mythic-pack-416254d25e35f8df0ed5.png", "banner_width": 820, "banner_height": 820, "included_items": [{"name": "1 Mythic Emblem", "symbol": "✦"}], "description": {"uz": "Haftalik Mythic Emblem Value Pack. Tarkibida 1 ta Mythic Emblem bor. Haftada bir marta olinadi.", "ru": "Еженедельный Mythic Emblem Value Pack. Содержит 1 Mythic Emblem. Доступен один раз в неделю.", "en": "Weekly Mythic Emblem Value Pack. Includes 1 Mythic Emblem. Available once a week."}};
  const result = normalized.flatMap(pack => {
    if (pack.type_name === 'Weekly Deal Pack') {
      const prices = {'pubgm1ucwdp-s101':89, 'pubgm2ucwdp-s101':269};
      if (!(pack.sku in prices)) return [];
      const art = 'https://images.gamestorehub.com/site-assets/topup-weekly-deal-' + (/pack 2/i.test(pack.name) ? '2' : '1') + '.png';
      const name = pack.name.replace(/\s+UC$/i, '');
      return [{...pack, name, display_name:name, membership:true, max_quantity:1, image_url:art, detail_banner:art, selling_price_cents:prices[pack.sku], selling_currency:'USD'}];
    }
    if (pack.type_name === 'Weekly Mythic Emblem Value Pack') return pack.sku === 'pubgmucwmevp-s101' ? [{...pack, ...weeklyMythic}] : [];
    if (pack.type_name === 'Upgradable Firearm Materials Pack') return pack.sku === 'pubgmucufmp-s101' ? [{...pack, ...firearmMaterials}] : [];
    if (['Prime','Prime Plus'].includes(pack.type_name)) return memberships.has(pack.sku) ? [{...pack, ...memberships.get(pack.sku)}] : [];
    if (pack.type_name === 'Mythic Emblem Pack') return pack.sku === 'pubgmucmep-s101' ? [{...pack, ...mythicEmblem}] : [];
    if (pack.type_name === 'First Purchase Pack') return pack.sku === 'pubgmucfpp-s101' ? [{...pack, ...firstPurchase}] : [];
    if (pack.type_name === 'Coins') return coinOffers.has(pack.sku) ? [{...pack, ...coinOffers.get(pack.sku)}] : [];
    if (pack.type_name === 'Battle Pass') {
      return passPrices.has(pack.sku) ? [{...pack, selling_price_cents:passPrices.get(pack.sku), selling_currency:'USD'}] : [];
    }
    if (pack.type_name !== 'UC') return [pack];
    const total = Number(pack.name.replace(/UC/gi, '').replace(/[\s.,]/g, ''));
    if (preferredSkus.has(total) && pack.sku !== preferredSkus.get(total)) return [];
    return ucLabels.has(total) ? [{...pack, name:ucLabels.get(total), selling_price_cents:usdPrices.get(total), selling_currency:'USD'}] : [];
  });
  return result;
}

function topupSupplierBasePrice(pack) {
  return pack.selling_currency === 'USD' && Number.isSafeInteger(pack.selling_price_cents) && pack.selling_price_cents > 0
    ? '$' + (pack.selling_price_cents / 100).toFixed(2) : '';
}

function topupSupplierPrice(pack) {
  const original = topupSupplierBasePrice(pack);
  return original ? globalThis.RegionPreferences?.estimate(pack.selling_price_cents, 'USD') || original : '';
}

function topupSupplierPriceAttributes(pack) {
  const original = topupSupplierBasePrice(pack);
  return original ? `data-region-money data-region-amount="${pack.selling_price_cents}" data-region-currency="USD" data-region-original="${esc(original)}"` : '';
}

function topupSupplierPackageLabel(pack) {
  const parts = String(pack.name || '').match(/^(\d+)\s*\+\s*(\d+)\s+(UC|Coins|Diamonds|Tokens|Gems|Crystals|Vouchers|Points|Credits|Gold)$/i);
  if (!parts) {
    const plain = String(pack.name || '').match(/^(\d+)\s+(UC|Coins|Diamonds|Tokens|Gems|Crystals|Vouchers|Points|Credits|Gold)$/i);
    return plain ? `${esc(plain[1])}<span class="tus-pack-unit" data-currency-unit="${esc(plain[2].toUpperCase())}">${esc(plain[2])}</span>` : esc(pack.name);
  }
  const tag = '<svg class="tus-bonus-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M3 4h8l10 10-7 7L3 10V4Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><circle cx="7.5" cy="8" r="1.2" fill="currentColor"/><path d="m11 11 5 5m0-5-5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
  return `${esc(parts[1])}<span class="tus-pack-bonus">+${esc(parts[2])}${tag}</span><span class="tus-pack-unit" data-currency-unit="${esc(parts[3].toUpperCase())}">${esc(parts[3])}</span>`;
}

async function renderTopUpSupplierBrand(game) {
  const brand = await api('/top-up/catalog/' + encodeURIComponent(game.slug));
  const returnOrder = new URLSearchParams(location.search).get('topup_return');
  const requestedSku = new URLSearchParams(location.search).get('package');
  brand.image_url = brand.image_url || TOPUP_CATALOG_IMAGE_FALLBACKS[game.slug] || '';
  brand.packages = topupSupplierPresentationPackages(game.slug, brand.packages);
  const t = adminText, groups = topupSupplierGroups(brand.packages, game.slug);
  const categoryLabels = TOPUP_CATEGORIES.find(([slug]) => slug === brand.category)?.slice(1);
  const category = categoryLabels ? t(...categoryLabels) : '';
  const heroArt = brand.banner_url || TOPUP_OFFICIAL_GAME_ART[game.slug] || brand.image_url;
  const packageArt = pack => {
    const kind = String(pack.type_name || '').toLowerCase();
    let art = pack.image_url || (/^(uc|diamonds|tokens)$/.test(kind) ? TOPUP_CURRENCY_ART[game.slug] : '');
    if (game.slug === 'pubg-mobile' && kind === 'battle pass') art = 'https://images.gamestorehub.com/site-assets/topup-elite-pass.png';
    if (game.slug === 'pubg-mobile' && kind === 'weekly deal pack') art = 'https://images.gamestorehub.com/site-assets/topup-weekly-deal-' + (/pack 2/i.test(pack.name) ? '2' : '1') + '.png';
    return art ? '<img' + (kind === 'coins' ? ' class="tus-coin-image"' : '') + ' src="' + esc(art) + '" alt="" loading="lazy" decoding="async">' : brand.image_url ? '<img src="' + esc(brand.image_url) + '" alt="" loading="lazy" decoding="async">' : icon('box');
  };
  const productInfo = group => {
    const pack = group.items.find(item=>item.pack.sku===requestedSku)?.pack || group.items[0]?.pack;
    if (!pack?.detail_banner || ((pack.membership || pack.open_detail) && pack.sku !== requestedSku)) return '';
    return `<article class="tus-product-info"><img class="tus-product-info-banner" width="${pack.banner_width || 1520}" height="${pack.banner_height || 770}" src="${esc(pack.detail_banner)}" alt="${esc(pack.display_name || pack.name)} overall rewards" loading="lazy"></article>`;
  };
  const typeName = group => group.name === 'Other' ? t('Boshqa paketlar','Другие пакеты','Other packages') : group.name;
  const packageCard = ({pack, index}) => pack.membership ? `<button type="button" class="tus-pack tus-membership-card" data-supplier-package="${index}" data-package-search="${esc(pack.name.toLocaleLowerCase())}" aria-label="${esc(pack.display_name)}"><img class="tus-membership-cover" src="${esc(pack.detail_banner)}" alt="" loading="lazy" width="1520" height="770"><span class="tus-membership-card-body"><strong class="tus-membership-title">${esc(pack.display_name)}</strong><span class="tus-membership-card-footer"><span class="tus-membership-price" ${topupSupplierPriceAttributes(pack)}>${topupSupplierPrice(pack) || t('Narx tayyorlanmoqda','Цена готовится','Price coming soon')}</span><span class="tus-membership-bag" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 8h14l1 13H4L5 8Z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/><path d="M8 9V6a4 4 0 0 1 8 0v3" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></span></span></span></button>` : `<button type="button" class="tus-pack${pack.open_detail ? ' tus-weekly-pack' : ''}" data-supplier-package="${index}" data-package-search="${esc(pack.name.toLocaleLowerCase())}" ${pack.open_detail ? '' : 'aria-pressed="false"'} ${pack.status !== 'active' ? 'disabled' : ''}>${pack.open_detail ? '' : '<span class="tus-pack-top"><span class="tus-pack-check" aria-hidden="true">✓</span></span>'}<span class="tus-pack-art">${packageArt(pack)}</span><strong class="tus-pack-label">${topupSupplierPackageLabel(pack)}</strong><span class="tus-pack-price${topupSupplierPrice(pack) ? ' has-price' : ''}" ${topupSupplierPriceAttributes(pack)}>${topupSupplierPrice(pack) || t('Narx tayyorlanmoqda','Цена готовится','Price coming soon')}</span></button>`;
  app.innerHTML = `<section class="page topup-page topup-supplier-page" data-supplier-game="${esc(game.slug)}">
    <nav class="tus-breadcrumb" aria-label="Breadcrumb"><a href="/top-up">Top Up</a><span>/</span><span>${esc(brand.name)}</span></nav>
    <header class="tus-hero${brand.category === 'game' ? ' tus-hero-game' : ''}">${heroArt ? `<img class="tus-hero-bg" src="${esc(heroArt)}" alt="" aria-hidden="true">` : ''}<div class="tus-hero-main"><div class="tus-brand-art">${brand.image_url ? `<img src="${esc(brand.image_url)}" alt="" decoding="async">` : topupGameIcon(game.slug)}</div><div><span class="tus-eyebrow">${esc(category)}</span><h1>${esc(brand.name)}</h1><p>${t('O‘zingizga mos paketni tanlang','Выберите подходящий пакет','Find the right package for you')}</p></div></div></header>
    <nav class="tus-types" aria-label="${t('Mahsulot turi','Тип товара','Product type')}">${groups.map((group,index)=>`<button type="button" data-supplier-type="${index}" aria-pressed="${index===0}" aria-controls="tus-type-${index}">${topupSupplierTypeIcon(group.name)}${esc(typeName(group))}</button>`).join('')}</nav>
    <div class="tus-layout"><div class="tus-main">
    ${groups.map((group,index)=>`<section class="tus-type-section" id="tus-type-${index}" data-supplier-section="${index}" aria-label="${esc(typeName(group))}" ${index?'hidden':''}><div class="tus-package-grid">${group.items.map(packageCard).join('')}</div>${productInfo(group)}</section>`).join('')}
    <p class="tus-empty" data-topup-package-empty hidden>${t('Mos paket topilmadi.','Подходящих пакетов не найдено.','No matching packages found.')}</p><div class="tus-more"><button type="button" data-supplier-more>${t('Ko‘proq ko‘rsatish','Показать ещё','Show more')}</button></div></div>
    <aside class="tus-summary"><div class="tus-summary-title"><h2>${t('Tanlangan paket','Выбранный пакет','Your selection')}</h2></div><div class="tus-summary-brand">${brand.image_url?`<img src="${esc(brand.image_url)}" alt="">`:''}<span>${esc(brand.name)}</span></div><div class="tus-summary-empty" data-supplier-summary-empty>${icon('box')}<b>${t('Paketni tanlang','Выберите пакет','Select a package')}</b><p>${t('Paket tafsilotlari shu yerda ko‘rinadi.','Здесь появятся детали пакета.','Your package details will appear here.')}</p></div><div class="tus-summary-selected" data-supplier-summary-selected aria-live="polite" hidden></div>${game.slug !== 'pubg-mobile' && brand.category === 'game' ? '<div class="tus-customer-fields" data-supplier-customer-fields></div>' : ''}${game.slug === 'pubg-mobile' ? `<form id="tus-checkout-form" class="tus-checkout-form"><label class="field"><span>${t('O‘yinchi ID raqami','ID игрока','Player ID')}</span><input name="player_id" inputmode="numeric" autocomplete="off" pattern="[0-9]{3,40}" minlength="3" maxlength="40" placeholder="${t('Player ID kiriting','Введите Player ID','Enter Player ID')}" required aria-describedby="tus-player-help"></label><small id="tus-player-help">${t('PUBG Mobile profilidagi ID raqamingiz.','ID из вашего профиля PUBG Mobile.','Your numeric ID from your PUBG Mobile profile.')}</small><label class="field tus-quantity-field" data-supplier-quantity-field hidden><span>${t('Miqdor','Количество','Quantity')}</span><div class="tus-quantity-stepper"><button type="button" data-supplier-quantity-step="-1" aria-label="${t('Kamaytirish','Уменьшить','Decrease quantity')}">−</button><input type="number" name="quantity" inputmode="numeric" min="1" max="99" step="1" value="1" required disabled><button type="button" data-supplier-quantity-step="1" aria-label="${t('Ko‘paytirish','Увеличить','Increase quantity')}">+</button></div></label><label class="tus-test-consent"><input type="checkbox" name="accept_terms" required><span>${t('Player ID ni tekshirdim. Stripe test to‘loviga roziman; haqiqiy UC yetkazilmaydi.','Я проверил Player ID и согласен на тестовую оплату Stripe. Реальные UC не доставляются.','I checked my Player ID and agree to a Stripe test payment. No real UC will be delivered.')}</span></label><p class="tus-checkout-error" role="alert" hidden></p></form>` : ''}<div data-supplier-rewards></div><div class="tus-summary-total"><span>${t('Jami','Итого','Total')}</span><b>—</b></div><button type="submit" form="tus-checkout-form" class="tus-buy" disabled>${t('Xarid qilish','Купить сейчас','Buy now')}</button><p class="tus-checkout-note">${icon('shield')}<span>${t('Sotuv narxlari va xarid qilish imkoniyati tayyorlanmoqda.','Цены продажи и возможность покупки готовятся.','Selling prices and checkout are being prepared.')}</span></p></aside></div></section>`;
  const page = app.querySelector('.topup-supplier-page');
  const typeButtons = [...page.querySelectorAll('[data-supplier-type]')];
  const sections = [...page.querySelectorAll('[data-supplier-section]')];
  const cards = [...page.querySelectorAll('[data-supplier-package]')];
  const cardsByIndex = new Map(cards.map(card => [Number(card.dataset.supplierPackage), card]));
  let activeType = 0, limit = 48, selectedPackage = null, requestKey = crypto.randomUUID();
  const checkoutForm = page.querySelector('#tus-checkout-form');
  const rewardsHost = page.querySelector('[data-supplier-rewards]');
  const supplierRewards = checkoutForm && me && brand.payment_mode === 'stripe_test' && window.RewardsUI ? window.RewardsUI.mountQuote(rewardsHost, {
    context:()=>selectedPackage && (!selectedPackage.detail_banner || Number(checkoutForm.elements.quantity.value) === 1) ? {kind:'topup',sku:selectedPackage.sku,quantity:1} : null,
    onChange:quote=>{
      requestKey = crypto.randomUUID();
      if (!quote) {refreshQuantity(); return;}
      renderTotal(quote.total_minor,quote.currency,fmt(quote.total_minor,quote.currency,true));
      renderPaymentNote(quote.total_minor,quote.currency);
    }
  }) : null;
  if (!supplierRewards) rewardsHost.hidden = true;
  function renderTotal(amount,currency,original) {
    const display = original ? globalThis.RegionPreferences?.estimate(amount,currency) || original : '—';
    const featuredPrice = page.querySelector('[data-fpp-total]');
    const nodes = [page.querySelector('.tus-summary-total b')];
    if (featuredPrice) nodes.push(featuredPrice,page.querySelector('.tus-buy'));
    for (const node of nodes) {
      node.textContent = display;
      if (original) {
        node.dataset.regionMoney = '';
        node.dataset.regionAmount = String(amount);
        node.dataset.regionCurrency = currency;
        node.dataset.regionOriginal = original;
      } else {
        ['regionMoney','regionAmount','regionCurrency','regionOriginal'].forEach(key=>delete node.dataset[key]);
      }
    }
  }
  function renderPaymentNote(amount,currency) {
    const note = page.querySelector('.tus-checkout-note span');
    note.dataset.originalCurrency = '';
    note.textContent = t('Stripe sinov buyurtmasi. Haqiqiy pul yechilmaydi va haqiqiy UC berilmaydi.','Тестовый заказ Stripe. Реальные деньги не списываются, UC не начисляются.','Stripe test order. No real money is charged and no real UC is delivered.')
      + ' ' + t('Asl to‘lov summasi','Исходная сумма платежа','Original payment amount') + ': ' + fmt(amount,currency,true);
  }
  function refreshQuantity() {
    if (!selectedPackage) return;
    const quantity = selectedPackage.detail_banner ? Number(checkoutForm.elements.quantity.value) : 1;
    const valid = Number.isInteger(quantity) && quantity >= 1 && quantity <= (selectedPackage.max_quantity || 1);
    const priced = {...selectedPackage, selling_price_cents:selectedPackage.selling_price_cents * quantity};
    const original = valid ? topupSupplierBasePrice(priced) : '';
    renderTotal(priced.selling_price_cents,priced.selling_currency,original);
    checkoutForm?.querySelectorAll('[data-supplier-quantity-step]').forEach(button => {
      button.disabled = !valid || (Number(button.dataset.supplierQuantityStep) < 0 ? quantity <= 1 : quantity >= (selectedPackage.max_quantity || 1));
    });
    const summaryQuantity = page.querySelector('[data-supplier-quantity-summary]');
    if (summaryQuantity) summaryQuantity.textContent = valid ? String(quantity) : '—';
    page.querySelector('.tus-buy').disabled = !valid || !topupSupplierBasePrice(selectedPackage) || brand.payment_mode !== 'stripe_test';
    if (original && brand.payment_mode === 'stripe_test') renderPaymentNote(priced.selling_price_cents,priced.selling_currency);
  }
  function selectPackage(index) {
    const pack = brand.packages[index];
    if (!pack || pack.status !== 'active') return;
    cards.forEach(card => {
      const cardIndex = Number(card.dataset.supplierPackage), item = brand.packages[cardIndex];
      if (item.open_detail || item.membership) card.removeAttribute('aria-pressed');
      else card.setAttribute('aria-pressed', String(cardIndex === index));
    });
    selectedPackage = pack;
    const customerFields = page.querySelector('[data-supplier-customer-fields]');
    if (customerFields) {
      const previous = new Map([...customerFields.querySelectorAll('input')].map(input=>[input.name,input.value]));
      customerFields.innerHTML = (pack.inquiry_fields || []).filter(field=>['text','number','email'].includes(field.type)).map((field,index)=>`<label class="field"><span>${esc(field.name || (index===0 ? 'Player ID' : 'Zone ID'))}</span><input type="${field.type==='email'?'email':'text'}" name="${esc(field.key)}" autocomplete="off" ${field.type==='number'?'inputmode="numeric"':''} ${field.required===false?'':'required'}></label>`).join('');
      customerFields.querySelectorAll('input').forEach(input=>{input.value=previous.get(input.name)||'';});
    }
    const listing = Boolean((pack.membership || pack.open_detail) && pack.sku !== requestedSku);
    page.classList.toggle('is-membership-list', listing);
    page.classList.toggle('is-first-purchase', Boolean(pack.detail_banner) && !listing);
    if (checkoutForm) {
      const multiple = Boolean(pack.detail_banner);
      checkoutForm.querySelector('[data-supplier-quantity-field]').hidden = !multiple;
      checkoutForm.elements.quantity.disabled = !multiple;
      checkoutForm.elements.quantity.value = '1';
      checkoutForm.elements.quantity.max = String(pack.max_quantity || 1);
      checkoutForm.elements.quantity.readOnly = (pack.max_quantity || 1) === 1;
    }
    requestKey = crypto.randomUUID();
    const price = topupSupplierPrice(pack);
    const total = page.querySelector('.tus-summary-total b');
    total.textContent = price || '—';
    if (topupSupplierBasePrice(pack)) {
      total.dataset.regionMoney = '';
      total.dataset.regionAmount = String(pack.selling_price_cents);
      total.dataset.regionCurrency = 'USD';
      total.dataset.regionOriginal = topupSupplierBasePrice(pack);
    } else {
      ['regionMoney','regionAmount','regionCurrency','regionOriginal'].forEach(key => delete total.dataset[key]);
    }
    const ready = Boolean(price && brand.payment_mode === 'stripe_test' && checkoutForm);
    const buy = page.querySelector('.tus-buy');
    ['regionMoney','regionAmount','regionCurrency','regionOriginal'].forEach(key=>delete buy.dataset[key]);
    buy.disabled = !ready;
    buy.textContent = ready ? t('Stripe test to‘lovi','Тестовая оплата Stripe','Stripe test checkout') : t('Xarid qilish','Купить сейчас','Buy now');
    page.querySelector('.tus-checkout-note span').textContent = ready
      ? t(`Stripe test. To‘lov: ${topupSupplierBasePrice(pack)} USD. Haqiqiy UC yetkazilmaydi.`,`Stripe test. Оплата: ${topupSupplierBasePrice(pack)} USD. Реальные UC не доставляются.`,`Stripe test. Payment: ${topupSupplierBasePrice(pack)} USD. No real UC delivery.`)
      : price ? t('Stripe test sozlamalari kutilmoqda.','Ожидается настройка Stripe test.','Stripe test configuration is required.')
      : t('Sotuv narxlari va xarid qilish imkoniyati tayyorlanmoqda.','Цены продажи и возможность покупки готовятся.','Selling prices and checkout are being prepared.');
    page.querySelector('[data-supplier-summary-empty]').hidden = true;
    const details = page.querySelector('[data-supplier-summary-selected]');
    details.hidden = false;
    details.innerHTML = `<div class="tus-summary-product"><div class="tus-summary-product-art">${packageArt(pack)}</div><h3 class="tus-pack-label">${topupSupplierPackageLabel(pack)}</h3></div><dl><div><dt>${t('Mahsulot turi','Тип товара','Product type')}</dt><dd>${esc(pack.type_name || t('Boshqa paketlar','Другие пакеты','Other packages'))}</dd></div><div><dt>${t('Miqdor','Количество','Quantity')}</dt><dd data-supplier-quantity-summary>1</dd></div></dl>`;
    if (pack.detail_banner) {
      details.innerHTML = `<div class="tus-first-purchase-heading"><h2>${esc(pack.display_name || pack.name)}</h2><strong data-fpp-total ${topupSupplierPriceAttributes(pack)}>${topupSupplierPrice(pack)}</strong></div>`;
    }
    refreshQuantity();
    supplierRewards?.invalidate();
  }
  function filterPackages() {
    const query = '';
    sections.forEach((section,index)=>{section.hidden=index!==activeType;});
    const group = groups[activeType];

    let matched = 0;
    if (group) group.items.forEach(({index})=>{
      const card = cardsByIndex.get(index), matches = card.dataset.packageSearch.includes(query);
      card.hidden = !matches || matched >= limit;
      if(matches) matched++;
    });

    page.querySelector('[data-topup-package-empty]').hidden = matched > 0;
    page.querySelector('[data-supplier-more]').hidden = matched <= limit;
  }
  typeButtons.forEach((button,index)=>button.addEventListener('click',()=>{
    if (requestedSku && groups[index]?.name === 'Shop') {
      location.assign('/top-up/' + encodeURIComponent(game.slug) + '?type=shop'); return;
    }
    const query = groups[index]?.name === 'Shop' ? '?type=shop' : '';
    history.replaceState(history.state, '', location.pathname + query);
    activeType=index;limit=48;
    typeButtons.forEach(item=>item.setAttribute('aria-pressed',String(item===button)));
    filterPackages();
    if (groups[activeType]?.items.length) selectPackage(groups[activeType].items[0].index);
  }));
  cards.forEach(card=>card.addEventListener('click',()=>{
    const index=Number(card.dataset.supplierPackage), pack=brand.packages[index];
    if (pack.membership || pack.open_detail) {location.assign('/top-up/' + encodeURIComponent(game.slug) + '?package=' + encodeURIComponent(pack.sku));return;}
    selectPackage(index);
  }));
  page.querySelector('[data-supplier-more]').addEventListener('click',()=>{limit+=48;filterPackages();});
  if (checkoutForm) {
    checkoutForm.querySelectorAll('[data-supplier-quantity-step]').forEach(button => button.addEventListener('click', () => {
      const input = checkoutForm.elements.quantity;
      input.value = String(Math.min(Number(input.max) || 1, Math.max(1, (Number(input.value) || 1) + Number(button.dataset.supplierQuantityStep))));
      input.dispatchEvent(new Event('input', {bubbles:true}));
    }));
    checkoutForm.addEventListener('input', () => {requestKey = crypto.randomUUID(); refreshQuantity(); supplierRewards?.invalidate();});
    checkoutForm.addEventListener('submit', async event => {
      event.preventDefault();
      if (!checkoutForm.reportValidity() || !selectedPackage || brand.payment_mode !== 'stripe_test') return;
      if (!me) {location.hash = 'login'; return;}
      const button = page.querySelector('.tus-buy'), error = checkoutForm.querySelector('.tus-checkout-error');
      button.disabled = true; error.hidden = true;
      try {
        const promotion = supplierRewards?.checkout();
        const order = await api('/top-up/test-checkout', {method:'POST', body:JSON.stringify({...(promotion?{rewards_quote_id:promotion.id}:{}),sku:selectedPackage.sku, player_id:checkoutForm.elements.player_id.value.trim(), quantity:selectedPackage.detail_banner ? Number(checkoutForm.elements.quantity.value) : 1, server_id:'', request_key:requestKey, accept_terms:checkoutForm.elements.accept_terms.checked})});
        const session = await api('/top-up/test-orders/' + encodeURIComponent(order.id) + '/checkout', {method:'POST', body:'{}'});
        try {sessionStorage.setItem('sentryloot-supplier-checkout', JSON.stringify({slug:game.slug,sku:selectedPackage.sku,player_id:checkoutForm.elements.player_id.value.trim()}));} catch {}
        location.assign(session.checkout_url);
      } catch (failure) {
        error.textContent = failure.message; error.hidden = false;
        toast(failure.message, 'error');
      } finally {button.disabled = false;}
    });
  }
  const requestedIndex = brand.packages.findIndex(pack=>(pack.membership || pack.open_detail) && pack.sku===requestedSku);
  const requestedType = new URLSearchParams(location.search).get('type');
  if (requestedIndex >= 0 || ['shop','prime','weekly','mythic'].includes(requestedType)) {
    const groupIndex=groups.findIndex(group=>requestedIndex>=0 ? group.items.some(item=>item.index===requestedIndex) : group.name === 'Shop');
    if (groupIndex>=0) activeType=groupIndex;
  }
  typeButtons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===activeType)));
  filterPackages();
  if (requestedIndex >= 0 && cardsByIndex.has(requestedIndex)) selectPackage(requestedIndex);
  else if (groups[activeType]?.items.length) selectPackage(groups[activeType].items[0].index);
  if (checkoutForm && !returnOrder) {
    try {
      const draft = JSON.parse(sessionStorage.getItem('sentryloot-supplier-checkout') || 'null');
      if (draft?.slug === game.slug) {
        const index = brand.packages.findIndex(pack => pack.sku === draft.sku);
        if (cardsByIndex.has(index)) {
          const groupIndex = groups.findIndex(group => group.items.some(item => item.index === index));
          if (groupIndex >= 0) {
            activeType = groupIndex;
            typeButtons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===activeType)));
            filterPackages();
          }
          selectPackage(index);
        }
        if (/^[0-9]{3,40}$/.test(draft.player_id || '')) checkoutForm.elements.player_id.value = draft.player_id;
        sessionStorage.removeItem('sentryloot-supplier-checkout');
      }
    } catch {}
  }
  if (returnOrder && /^[A-Za-z0-9_-]+$/.test(returnOrder)) {
    const params = new URLSearchParams(location.search); params.delete('topup_return');
    history.replaceState(history.state, '', location.pathname + (params.size ? '?' + params.toString() : '') + location.hash);
    try {sessionStorage.removeItem('sentryloot-supplier-checkout');} catch {}
    try {
      const order = await api('/top-up/test-orders/' + encodeURIComponent(returnOrder) + '/refresh', {method:'POST',body:'{}'});
      if (['paid_test','delivered_test','completed'].includes(order.status)) {
        toast(t('Stripe test to‘lovi muvaffaqiyatli. Test rejimida haqiqiy UC yuborilmaydi.','Тестовая оплата Stripe успешна. Реальные UC в тестовом режиме не отправляются.','Stripe test payment successful. No real UC is delivered in test mode.'),'success');
      } else {
        toast(t('To‘lov hali tasdiqlanmagan.','Оплата ещё не подтверждена.','Payment has not been confirmed yet.'),'info');
      }
    } catch (error) {toast(error.message,'error');}
  }
}

const TOPUP_MOBILE_GAME_ART = {'pubg-mobile':'mobile-topup-pubg.webp','mobile-legends':'market-game-mobile-legends.png','free-fire':'market-game-free-fire.png','honor-of-kings':'market-game-honor-of-kings.png'};
const TOPUP_GAME_ORDER = ['pubg-mobile', 'mobile-legends', 'free-fire', 'honor-of-kings'];
function topupGameCount(count) {
  if (locale === 'uz') return count + ' o‘yin';
  if (locale === 'ru') {
    const last = count % 10, lastTwo = count % 100;
    return count + ' ' + (last === 1 && lastTwo !== 11 ? 'игра' : last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14) ? 'игры' : 'игр');
  }
  return count + ' ' + (count === 1 ? 'game' : 'games');
}
const TOPUP_OFFICIAL_GAME_ART = {
  'pubg-mobile': 'https://play-lh.googleusercontent.com/xRj26dOD5JhpfQ54rOXl8WNwij9p5dOYoaKGbyEjsEhRu35ogBp08qYS7HFHfHjlahSWEPs8VJRmqbjw8Q4SsQ%3Dw526-h296',
  'mobile-legends': 'https://play-lh.googleusercontent.com/hrpZdffP0Mt4nSZnr6FUk0OyeEm_GyXZ3TxCoQb7cSFoNOeF0KGEQoXgSR-PKqk1rlOyImJFvIPvZyXuoG3eXA%3Dw526-h296',
  'free-fire': 'https://play-lh.googleusercontent.com/LsawRbqk_iyOjjY_NkmKv62sTH9U4WqaF9juPzT0nhN4u9v52SHAfQliNaKpYZgo4KPN2j-cLVI44PhKpuAGJQ%3Dw526-h296',
  'honor-of-kings': 'https://play-lh.googleusercontent.com/m7qsYcurlr6a2PrgrgzWq1RO4mbs9miB7X9gb0oTTcYUI-Tbe8eELvvh3uO8VNy8-3UQchKw9W7P5iAgLRUe%3Dw526-h296'
};

const TOPUP_CURRENCY_ART = {
  'pubg-mobile': 'https://images.gamestorehub.com/site-assets/topup-uc.png',
  'mobile-legends': 'https://images.gamestorehub.com/site-assets/topup-mobile-legends-diamonds.png',
  'free-fire': 'https://images.gamestorehub.com/site-assets/topup-free-fire-diamonds.png',
  'honor-of-kings': 'https://images.gamestorehub.com/site-assets/topup-honor-of-kings-tokens.png'
};

function topupCurrencyImage(game, variant) {
  const source = TOPUP_CURRENCY_ART[game.slug];
  return source ? '<img class="topup-currency-image topup-currency-image-' + variant + '" src="' + source + '" alt="' + esc(game.name + ' ' + game.currency) + '" decoding="async">' : topupGameIcon(game.slug);
}

function topupGameIcon(slug) {
  const art = {
    'pubg-mobile': '<path d="M12 3 20 7v5c0 4.3-3.1 7.4-8 9-4.9-1.6-8-4.7-8-9V7l8-4Z"/><path d="M12 7v10m-4-5h8"/>',
    'mobile-legends': '<path d="m5 19 11-11m-6-3 8 8m-9-8 9 9m-11 3h7"/><path d="m16 4 4 4-3 1-2-2 1-3Z"/>',
    'free-fire': '<path d="M13 3c1 5-3 5-1 9 1-2 3-3 4-5 3 3 4 6 3 9a7 7 0 0 1-14 0c0-4 2-7 5-10 0 3 1 4 3 5-1-4 1-6 0-8Z"/>',
    'honor-of-kings': '<path d="M12 3 20 6v5c0 5-3.5 8.4-8 10-4.5-1.6-8-5-8-10V6l8-3Z"/><path d="m8 12 2.5 2.5L16 9"/>'
  };
  return '<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + (art[slug] || '<path d="M7 8h10l3 3v6H4v-6l3-3Z"/><path d="M8 12v3m-1.5-1.5h3m6-1h.01M18 14h.01"/>') + '</svg>';
}

function topupComingSoonBadge(show) {
  return show ? '<span class="topup-coming-soon"><span></span>' + adminText('Tez orada','Скоро','Coming soon') + '</span>' : '';
}

async function renderTopUpCatalog(selectedGame, selectedProduct) {
  document.body.classList.remove('home-page'); app.classList.remove('home-background');
  const rows = await api('/top-up/catalog');
  rows.sort((a, b) => (TOPUP_GAME_ORDER.indexOf(a.slug) < 0 ? 99 : TOPUP_GAME_ORDER.indexOf(a.slug)) - (TOPUP_GAME_ORDER.indexOf(b.slug) < 0 ? 99 : TOPUP_GAME_ORDER.indexOf(b.slug)));
  const game = rows.find(x => x.slug === selectedGame);
  if (selectedGame && !game) {
    app.innerHTML = '<section class="page topup-page"><div class="notice error">' + adminText('O‘yin topilmadi.','Игра не найдена.','Game not found.') + '</div></section>';
    return;
  }
  if (selectedProduct && !game.packages.some(item => item.url_slug === selectedProduct)) {
    app.innerHTML = '<section class="page topup-page"><div class="notice error">' + adminText('Top Up paketi topilmadi.','Пакет Top Up не найден.','Top Up package not found.') + '</div></section>';
    return;
  }
  const words = {
    catalog: 'Top Up',
    intro: adminText('Kategoriya va mahsulotni tanlang — o‘yinlar, sovg‘a kartalari va raqamli xizmatlar.','Выберите категорию и товар: игры, подарочные карты и цифровые услуги.','Choose a category and product — games, gift cards, and digital services.'),
    games: adminText('O‘yinlar','Игры','Games'), packs: adminText('Paketlar','Пакеты','Packs'),
    select: adminText('O‘yinni tanlang','Выберите игру','Choose your game'),
    feature: adminText('Top Up va raqamli xizmatlar','Пополнения и цифровые услуги','Top ups & digital services')
  };
  const heading = game ? game.name : words.catalog;
  const currentPackage = game && selectedProduct ? game.packages.find(item => item.url_slug === selectedProduct) : null;
  document.title = (currentPackage ? (currentPackage.product_name || Number(currentPackage.amount).toLocaleString(localeTag()) + ' ' + currentPackage.currency) + ' ' + game.name + ' Top Up' : game ? game.name + ' Top Up' : words.catalog) + ' | SentryLoot';
  const pageDescription = $('meta[name="description"]');
  if (pageDescription) pageDescription.content = currentPackage ? (currentPackage.product_name || currentPackage.amount + ' ' + currentPackage.currency) + ' for ' + game.name + ' on SentryLoot.' : game ? game.name + ' top-up packages and game currency.' : words.intro;
  const canonical = $('link[rel="canonical"]');
  if (canonical) canonical.href = location.origin + (currentPackage ? '/top-up/' + encodeURIComponent(game.slug) + '/' + encodeURIComponent(currentPackage.url_slug) : game ? '/top-up/' + encodeURIComponent(game.slug) : '/top-up');

  let body = '';
  if (game) {
    if (game.source === 'melostore' && !selectedProduct) { await renderTopUpSupplierBrand(game); return; }
    renderTopUpDetail(game, currentPackage);
    return;
  } else {
    body = '<div class="topup-catalog-tools"><p data-topup-result-count role="status"></p><label class="topup-catalog-search"><span class="sr-only">' + adminText('Mahsulotlarni qidirish','Поиск товаров','Search products') + '</span><input type="search" data-topup-search placeholder="' + adminText('Mahsulotlarni qidirish…','Поиск товаров…','Search products…') + '" autocomplete="off"></label></div><div id="topup-catalog-products"><p class="topup-category-empty" data-topup-category-empty role="status" hidden></p><div class="topup-games-grid">' + rows.map(topupCatalogCard).join('') + '</div></div><div class="topup-catalog-more"><button type="button" class="button-secondary" data-topup-load-more>' + adminText('Ko‘proq ko‘rsatish','Показать ещё','Show more') + '</button></div>';
  }
  const categoryNavigation = '<nav class="topup-categories" aria-label="' + adminText('Top Up kategoriyalari','Категории Top Up','Top Up categories') + '">' + TOPUP_CATEGORIES.map(([id, ...labels]) => '<button type="button" class="topup-category" data-topup-category="' + id + '" aria-pressed="' + (id === 'all') + '" aria-controls="topup-catalog-products">' + esc(adminText(...labels)) + '</button>').join('') + '</nav>';
  const catalogContent = '<div class="topup-hero topup-hero-image"><nav class="topup-breadcrumb topup-hero-back" aria-label="Breadcrumb"></nav><img class="topup-hero-background" src="https://images.gamestorehub.com/site-assets/topup-hero.jpg" alt="" fetchpriority="high"><div class="topup-hero-overlay"></div><div class="topup-hero-content"><div class="topup-hero-brand"><b>Sentry<span class="brand-dot">Loot</span></b></div><h1>' + esc(words.feature) + '</h1><p>' + words.intro + '</p></div></div>' + categoryNavigation + body + '<aside class="topup-safe-note">' + icon('shield') + '<p><b>' + adminText('Xaridlar va to‘lovlar','Покупки и оплата','Payments are being prepared') + '</b><br>' + adminText('To‘lov tizimi ulangach paketlarni xarid qilish mumkin bo‘ladi.','Пакеты можно будет купить после подключения платёжной системы.','Packages will be available to buy once a payment provider is connected.') + '</p></aside>';
  app.innerHTML = '<section class="page topup-page">' + (game ? body : catalogContent) + '</section>';
  const page = app.querySelector('.topup-page');
  page.dataset.activeTopupCategory = 'all';
  page.querySelectorAll('[data-topup-category]').forEach(button => button.addEventListener('click', () => {
    page.dataset.activeTopupCategory = button.dataset.topupCategory;
    page.dataset.topupLimit = '48';
    page.querySelectorAll('[data-topup-category]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
    topupApplyFilters(page);
  }));
  page.querySelector('[data-topup-search]').addEventListener('input', event => {
    page.dataset.topupQuery = event.target.value; page.dataset.topupLimit = '48'; topupApplyFilters(page);
  });
  page.querySelector('[data-topup-load-more]').addEventListener('click', () => {
    page.dataset.topupLimit = String((Number(page.dataset.topupLimit) || 48) + 48); topupApplyFilters(page);
  });
  page.querySelectorAll('[data-topup-hide-error]').forEach(image => image.addEventListener('error', () => { image.hidden = true; }, { once:true }));
  topupApplyFilters(page);
  $$('[data-topup-fallback]', app).forEach(image => image.addEventListener('error', () => { if (image.src !== new URL(image.dataset.topupFallback, location.origin).href) image.src = image.dataset.topupFallback; }, { once: true }));

}

async function renderTopUpProduct(gameSlug, productSlug) {
  await renderTopUpCatalog(gameSlug, productSlug);
}

function topupAdminExistingGame(packages,slug) {
  const same=packages.filter(p=>p.game_slug===String(slug).trim().toLowerCase());
  if(!same.length)return null;
  const counts=new Map();same.forEach(p=>counts.set(p.currency,(counts.get(p.currency)||0)+1));
  return {game_name:same[0].game_name,currency:[...counts].sort((a,b)=>b[1]-a[1])[0][0]};
}

function topupAdminMatchesStatus(p,filter='') {
  if(!p)return false;
  if(filter==='hidden')return !p.enabled;
  if(!p.enabled)return false;
  const priced=Number(p.price_minor)>0,available=Number(p.stock_on_hand)>Number(p.stock_reserved);
  return !filter||(filter==='priced'&&priced)||(filter==='needs-price'&&!priced)||(filter==='stock'&&available)||(filter==='empty'&&!available);
}

async function renderTopUpAdmin() {
  if (!me) { location.hash = 'login'; return; }
  if (!me.is_admin) { app.innerHTML = '<section class="page">' + pageTitle(adminText('Top Up boshqaruvi','Управление Top Up','Top Up management')) + '<div class="notice error">' + adminText('Administrator ruxsati kerak.','Требуются права администратора.','Administrator access required.') + '</div></section>'; return; }
  const text=(uz,ru,en)=>adminText(uz,ru,en);
  app.innerHTML = '<section class="page topup-admin-page"><div class="topup-admin-heading"><div><span class="topup-overline">SENTRYLOOT · ADMIN</span><h1>' + text('Top Up boshqaruvi','Управление Top Up','Top Up management') + '</h1><p>' + text('Paketlarni, narxlarni va omborni bir joydan sodda boshqaring.','Управляйте пакетами, ценами и остатками в одном месте.','Manage packages, prices, and stock from one clear workspace.') + '</p></div></div><div class="topup-admin-notice" aria-live="polite"></div><div class="topup-admin-mount"><div class="loading"><span class="spinner"></span> ' + text('Ma’lumotlar yuklanmoqda…','Загрузка данных…','Loading data…') + '</div></div></section>';
  const root = $('.topup-admin-mount'), notice = $('.topup-admin-notice');
  try {
    const data = await api('/admin/top-up'), packages=data.packages||[], orders=data.orders||[], supplier=data.supplier||{};
    const gameCount=new Set(packages.map(p=>p.game_slug)).size, enabledCount=packages.filter(p=>p.enabled).length, needsPrice=packages.filter(p=>Number(p.price_minor)<=0).length, stocked=packages.filter(p=>Number(p.stock_on_hand)>Number(p.stock_reserved)).length;
    const status=(p)=>!p.enabled?text('Yashirilgan','Скрыт','Hidden'):p.coming_soon?text('Tez kunda','Скоро','Coming soon'):text('Saytda faol','Активен на сайте','Live on site');
    const orderStatus=(value)=>({awaiting_payment:text('To‘lov kutilmoqda','Ожидает оплаты','Awaiting payment'),paid:text('To‘langan','Оплачен','Paid'),fulfilled:text('Yetkazildi','Выполнен','Fulfilled'),completed:text('Yakunlandi','Завершён','Completed'),cancelled:text('Bekor qilingan','Отменён','Cancelled'),refunded:text('Qaytarilgan','Возвращён','Refunded')})[value]||value||'—';
    const packageCards=packages.map(p=>{
      const available=Math.max(0,Number(p.stock_on_hand)-Number(p.stock_reserved));
      const price=Number(p.price_minor)>0?fmt(p.price_minor,'UZS',true):text('Narx kiritilmagan','Цена не задана','Price not set');
      const search=[p.game_name,p.game_slug,p.product_name,p.amount,p.currency,p.url_slug].join(' ').toLocaleLowerCase();
      return `<details class="topup-admin-package" data-game="${esc(p.game_slug)}" data-search="${esc(search)}"><summary><span class="topup-admin-pack-main"><span class="topup-admin-pack-game">${esc(p.game_name)}</span><b>${esc(p.product_name || Number(p.amount).toLocaleString(localeTag())+' '+p.currency)}</b></span><span class="topup-admin-pack-price">${price}</span><span class="topup-admin-pack-stock ${available?'is-ready':'is-empty'}">${available?text(`${available} ta mavjud`,`${available} доступно`,`${available} available`):text('Zaxira yo‘q','Нет запаса','Out of stock')}</span><span class="topup-admin-pack-state ${!p.enabled?'is-hidden':p.coming_soon?'is-pending':'is-live'}">${status(p)}</span><span class="topup-admin-chevron">⌄</span></summary><div class="topup-admin-package-body"><div class="topup-admin-package-top"><div><span class="topup-admin-label">${text('Paket sozlamalari','Настройки пакета','Package settings')}</span><a href="/top-up/${encodeURIComponent(p.game_slug)}/${encodeURIComponent(p.url_slug)}" target="_blank" rel="noopener">${text('Saytdagi sahifani ko‘rish','Открыть страницу на сайте','Preview on site')} ${icon('arrow-up-right')}</a></div><small>${esc(p.game_slug)} / ${esc(p.url_slug)}</small></div><form class="topup-admin-save topup-admin-settings" data-package="${esc(p.id)}"><label>${text('Sotuv narxi (UZS)','Цена продажи (UZS)','Selling price (UZS)')}<input name="price_minor" type="number" min="0" max="1000000000000" step="100" value="${Number(p.price_minor)||0}" required><small>${text('0 bo‘lsa, narx belgilanmagan hisoblanadi.','0 означает, что цена не задана.','Set to 0 to leave the price unset.')}</small></label><fieldset><legend>${text('Ko‘rinish va yetkazish','Видимость и выдача','Visibility and fulfillment')}</legend><label class="topup-admin-check"><input type="checkbox" name="enabled" ${p.enabled?'checked':''}>${text('Saytda ko‘rsatish','Показывать на сайте','Show on site')}</label><label class="topup-admin-check"><input type="checkbox" name="coming_soon" ${p.coming_soon?'checked':''}>${text('Tez kunda belgisi','Метка «Скоро»','Coming soon label')}</label><label class="topup-admin-check"><input type="checkbox" name="manual_enabled" ${p.manual_enabled?'checked':''}>${text('Qo‘lda yetkazish','Ручная выдача','Manual fulfillment')}</label></fieldset><button class="button-accent" type="submit">${text('Sozlamalarni saqlash','Сохранить настройки','Save settings')}</button></form><div class="topup-admin-inventory"><div class="topup-admin-inventory-head"><div><span class="topup-admin-label">${text('Ombor qoldig‘i','Остатки на складе','Inventory')}</span><p>${text('Kirim uchun musbat, kamaytirish uchun manfiy miqdor kiriting.','Для поступления укажите плюс, для списания — минус.','Use a positive number to add stock, a negative number to remove it.')}</p></div><span>${text('Jami','Всего','Total')} <b>${Number(p.stock_on_hand)||0}</b> · ${text('Band','Резерв','Reserved')} <b>${Number(p.stock_reserved)||0}</b> · ${text('Sotuvga tayyor','Доступно','Available')} <b>${available}</b></span></div><form class="topup-stock-adjust topup-admin-stock-form" data-package="${esc(p.id)}"><label>${text('Miqdor (+ / −)','Количество (+ / −)','Quantity (+ / −)')}<input name="delta" type="number" min="-100000" max="100000" step="1" placeholder="+10" required></label><label>${text('Izoh (majburiy)','Комментарий (обязательно)','Reason (required)')}<input name="reason" maxlength="240" minlength="3" placeholder="${text('Masalan: omborga 10 ta kiritildi','Например: поступило 10 шт.','e.g. Added 10 units')}" required></label><button class="button-secondary" type="submit">${text('Qoldiqni yangilash','Обновить остаток','Update stock')}</button></form></div></div></details>`;
    }).join('');
    const orderRows=orders.length?orders.map(order=>`<article class="topup-admin-order"><div><b>${esc(order.reference||order.id)}</b><small>${esc(order.game_name)} · ${Number(order.amount).toLocaleString(localeTag())} ${esc(order.package_currency||'')} × ${Number(order.quantity)||1}</small></div><div><b>${esc(order.buyer_email||'')}</b><small>${text('O‘yinchi ID','Игровой ID','Player ID')}: ${esc(order.player_id||'—')}${order.server_id?' · '+text('Server','Сервер','Server')+': '+esc(order.server_id):''}</small></div><div><span class="topup-admin-order-status">${esc(orderStatus(order.status))}</span><small>${order.created_at?new Date(order.created_at).toLocaleString(localeTag()):''}</small></div></article>`).join(''):`<div class="topup-admin-empty"><span>${icon('box')}</span><b>${text('Hozircha buyurtmalar yo‘q','Заказов пока нет','No orders yet')}</b><p>${text('Yangi Top Up buyurtmalari shu yerda ko‘rinadi.','Новые заказы Top Up появятся здесь.','New Top Up orders will appear here.')}</p></div>`;
    root.innerHTML=`<div class="topup-admin-stats"><article><span>${text('O‘yinlar','Игры','Games')}</span><b>${gameCount}</b><small>${text('katalogda','в каталоге','in catalog')}</small></article><article><span>${text('Jami paketlar','Всего пакетов','Total packages')}</span><b>${packages.length}</b><small>${text(`${enabledCount} tasi saytda ko‘rinadi`,`${enabledCount} отображаются на сайте`,`${enabledCount} visible on site`)}</small></article><article class="${needsPrice?'needs-attention':''}"><span>${text('Narx kutilmoqda','Нужна цена','Need a price')}</span><b>${needsPrice}</b><small>${text('narx belgilanmagan','цена не задана','without a price')}</small></article><article><span>${text('Zaxirasi bor','С запасом','In stock')}</span><b>${stocked}</b><small>${text('paket sotuvga tayyor','пакетов готовы к продаже','packages with available stock')}</small></article></div><div class="topup-admin-status-banner"><span class="topup-admin-status-icon">${icon('clock')}</span><div><b>${text('Xaridlar hozircha o‘chiq','Покупки пока отключены','Checkout is currently disabled')}</b><p>${text('To‘lov provayderi va avtomatik ta’minotchi ulanmagan. Narx va omborni tayyorlashingiz mumkin, ammo xaridorlar hozircha buyurtma bera olmaydi.','Платёжный провайдер и API поставщика не подключены. Вы можете подготовить цены и остатки, но покупатели пока не смогут оформить заказ.','Payment and supplier integrations are not connected. You can prepare prices and stock, but customers cannot place orders yet.')}</p></div></div><div class="topup-admin-section-heading"><div><span class="topup-overline">${text('KATALOG','КАТАЛОГ','CATALOG')}</span><h2>${text('Paketlarni boshqarish','Управление пакетами','Manage packages')}</h2><p>${text('Paket ustiga bosing — narxi, holati va omborini o‘zgartiring.','Нажмите на пакет, чтобы изменить цену, статус или остаток.','Open a package to edit its price, status, and stock.')}</p></div><details class="topup-admin-add"><summary class="button-accent">${icon('plus')} ${text('Paket qo‘shish','Добавить пакет','Add package')}</summary><form class="topup-admin-create"><div><label>${text('O‘yin nomi','Название игры','Game name')}<input name="game_name" maxlength="100" required placeholder="PUBG Mobile"></label><small>${text('O‘yin nomi mijozlarga ko‘rinadi.','Название увидят покупатели.','Shown to customers.')}</small></div><div><label>${text('O‘yin slug','Slug игры','Game slug')}<input name="game_slug" maxlength="80" required placeholder="pubg-mobile"></label><small>${text('Kichik harf va tire: pubg-mobile','Маленькие буквы и дефис: pubg-mobile','Lowercase and dashes: pubg-mobile')}</small></div><div><label>${text('Valyuta nomi','Название валюты','Currency name')}<input name="currency" maxlength="20" required placeholder="UC"></label><small>${text('Masalan: UC yoki Diamonds','Например: UC или Diamonds','e.g. UC or Diamonds')}</small></div><div><label>${text('Miqdor','Количество','Amount')}<input name="amount" type="number" min="1" max="1000000000" required placeholder="60"></label></div><div><label>${text('Paket slug','Slug пакета','Package slug')}<input name="url_slug" maxlength="100" required placeholder="60-uc"></label><small>${text('Masalan: 60-uc','Например: 60-uc','e.g. 60-uc')}</small></div><div><label>${text('Sotuv narxi (UZS)','Цена продажи (UZS)','Selling price (UZS)')}<input name="price_minor" type="number" min="0" max="1000000000000" step="100" value="0" required></label><small>${text('Keyin ham o‘zgartirish mumkin.','Можно изменить позже.','You can edit this later.')}</small></div><label class="topup-admin-check topup-admin-create-soon"><input type="checkbox" name="coming_soon" checked>${text('Tez kunda deb ko‘rsatish','Показывать «Скоро»','Mark as coming soon')}</label><button class="button-accent" type="submit">${icon('plus')} ${text('Yangi paket yaratish','Создать пакет','Create package')}</button></form></details></div><div class="topup-admin-toolbar"><label class="topup-admin-search">${icon('search')}<input type="search" data-topup-search placeholder="${text('O‘yin yoki paketni qidiring…','Поиск игры или пакета…','Search game or package…')}" aria-label="${text('O‘yin yoki paketni qidirish','Поиск игры или пакета','Search games or packages')}"></label><label class="topup-admin-filter"><span>${text('O‘yin bo‘yicha','По игре','Game')}</span><select data-topup-game-filter><option value="">${text('Barcha o‘yinlar','Все игры','All games')}</option>${Array.from(new Map(packages.map(p=>[p.game_slug,p.game_name])).entries()).map(([slug,name])=>`<option value="${esc(slug)}">${esc(name)}</option>`).join('')}</select></label><label class="topup-admin-filter"><span>${text('Holati','Статус','Status')}</span><select data-topup-status-filter><option value="">${text('Faol paketlar','Активные пакеты','Active packages')}</option><option value="hidden">${text('O‘chirilgan / yashirilgan','Удалённые / скрытые','Deleted / hidden')}</option><option value="priced">${text('Narxi bor','С ценой','Priced')}</option><option value="needs-price">${text('Narxi yo‘q','Без цены','Needs price')}</option><option value="stock">${text('Zaxirasi bor','Есть остаток','In stock')}</option><option value="empty">${text('Zaxirasi yo‘q','Нет остатка','Out of stock')}</option></select></label></div><div class="topup-admin-package-list">${packageCards||`<div class="topup-admin-empty"><b>${text('Katalogda paket topilmadi','Пакеты не найдены','No packages found')}</b></div>`}</div><div class="topup-admin-no-results" hidden>${text('Bu qidiruvga mos paket topilmadi. Filtrlarni o‘zgartirib ko‘ring.','Пакеты не найдены. Попробуйте изменить фильтры.','No packages match. Try changing your filters.')}</div><details class="topup-admin-orders"><summary><span><b>${text('So‘nggi buyurtmalar','Последние заказы','Recent orders')}</b><small>${orders.length} / ${text('oxirgi 100 ta','последние 100','latest 100')}</small></span><span>${icon('chevron')}</span></summary><div class="topup-admin-order-list">${orderRows}</div></details><aside class="topup-admin-footnote">${text('Ombor qo‘lda boshqariladi. Avtomatik yetkazish uchun alohida ta’minotchi API va ruxsat kerak.','Остатки управляются вручную. Для автоматической выдачи нужен API поставщика и разрешение.','Stock is managed manually. Automatic fulfillment requires a supplier API and approval.')}</aside>`;
    const supplierCard=document.createElement('section');
    let activeSupplierMapping=null;
    supplierCard.className='topup-admin-supplier-card';
    supplierCard.innerHTML='<div class="topup-admin-supplier-copy"><span class="topup-overline">SEAGM · '+esc((supplier.environment||'sandbox').toUpperCase())+'</span><h3>'+text('Ta’minotchi ulanishi','Подключение поставщика','Supplier connection')+'</h3><p data-seagm-message>'+esc(supplier.configured?text('Server kalitlari bor. API aloqasini tekshiring.','Ключи заданы на сервере. Проверьте API.','Server credentials are present. Check the API connection.'):text('Avval SEAGM bilan hamkorlik ochib, server kalitlarini kiriting.','Сначала оформите партнёрство с SEAGM и добавьте ключи на сервер.','Apply for SEAGM access, then add the API credentials to the server.'))+'</p><small>'+text('Balans supplier hisobidan yechiladi; SEAGM kaliti brauzerga berilmaydi.','Покупка списывается с баланса поставщика; ключ не передаётся в браузер.','Purchases draw from the supplier wallet. The API secret stays server-side.')+'</small></div><div class="topup-admin-supplier-actions"><button class="button-secondary" type="button" data-seagm-check '+(supplier.configured?'':'disabled')+'>'+text('Ulanishni tekshirish','Проверить подключение','Check connection')+'</button><button class="button-secondary" type="button" data-seagm-catalog '+(supplier.configured?'':'disabled')+'>'+text('SEAGM katalogi','Каталог SEAGM','Load SEAGM catalog')+'</button><a href="https://www.seagm.com/en-sa/page/index?view=partnership" target="_blank" rel="noopener">'+text('Hamkorlikka ariza','Заявка на партнёрство','Apply for partnership')+' ↗</a></div><div class="topup-admin-supplier-result" data-seagm-result aria-live="polite"></div>';
    $('.topup-admin-status-banner',root)?.insertAdjacentElement('afterend',supplierCard);
    supplierCard.addEventListener('click',async event=>{
      const button=event.target.closest('[data-seagm-check],[data-seagm-catalog],[data-seagm-category],[data-seagm-use]'); if(!button)return;
      button.disabled=true; button.classList.add('is-loading');
      const message=$('[data-seagm-message]',supplierCard), result=$('[data-seagm-result]',supplierCard);
      try{
        if(button.hasAttribute('data-seagm-check')){
          const response=await api('/admin/top-up/supplier/check',{method:'POST',body:'{}'}), account=response.account||{};
          message.textContent=account.connected?text('SEAGM API ulandi.','API SEAGM подключён.','SEAGM API connected.'):text('SEAGM API kalitlari sozlanmagan.','Ключи API SEAGM не настроены.','SEAGM API credentials are not configured.');
          result.textContent=account.connected?[account.username||account.account_id,account.balance!=null?(account.balance+' '+(account.currency||'')):''].filter(Boolean).join(' · '):'';
        }else if(button.hasAttribute('data-seagm-catalog')){
          const response=await api('/admin/top-up/supplier/catalog');
          const categories=response.categories||[];
          result.innerHTML='<b>'+text('O‘yin bo‘limini tanlang — paketlarni ko‘ring va mos ID ni nusxalang.','Выберите игру, просмотрите пакеты и скопируйте ID.','Choose a game, review its packages, and copy the matching ID.')+'</b><ul>'+categories.slice(0,60).map(item=>'<li><span>'+esc(item.name)+'</span><button class="button-secondary" type="button" data-seagm-category="'+esc(item.id)+'">'+text('Paketlar','Пакеты','Packages')+'</button><code>'+esc(item.id)+'</code></li>').join('')+'</ul>'+(categories.length>60?'<small>'+text('Birinchi 60 ta ko‘rsatildi.','Показаны первые 60.','Showing the first 60.')+'</small>':'');
        }
        const categoryButton=event.target.closest('[data-seagm-category]');
        if(categoryButton){
          const response=await api('/admin/top-up/supplier/categories/'+encodeURIComponent(categoryButton.dataset.seagmCategory)+'/types');
          const products=response.products||[];
          result.innerHTML='<b>'+text('Supplier paketlari','Пакеты поставщика','Supplier packages')+'</b><ul>'+products.map(item=>'<li><span>'+esc(item.name)+' · '+esc(item.unit_price)+' '+esc(item.currency)+(item.fields.length?' · '+item.fields.map(field=>esc(field.name)).join(', '):'')+'</span><button class="button-secondary" type="button" data-seagm-use="'+esc(item.id)+'">'+text('ID ni tanlash','Использовать ID','Use ID')+'</button><code>'+esc(item.id)+'</code></li>').join('')+'</ul>';
        }
        const useButton=event.target.closest('[data-seagm-use]');
        if(useButton&&activeSupplierMapping){activeSupplierMapping.value=useButton.dataset.seagmUse;activeSupplierMapping.dispatchEvent(new Event('input',{bubbles:true}));result.insertAdjacentHTML('afterbegin','<p>'+text('ID paket maydoniga qo‘yildi. Saqlashni bosing.','ID добавлен в поле пакета. Нажмите «Сохранить».','ID copied into the package field. Save the package.')+'</p>')}
      }catch(error){result.textContent=error.message}
      finally{button.disabled=false;button.classList.remove('is-loading')}
    });
    root.addEventListener('focusin',event=>{if(event.target.matches('input[name="supplier_type_id"]'))activeSupplierMapping=event.target});
    $$('.topup-admin-package',root).forEach(card=>{
      const packageData=packages.find(item=>item.id===card.querySelector('.topup-admin-save')?.dataset.package);
      const mapping=document.createElement('form'); mapping.className='topup-supplier-map topup-admin-settings'; mapping.dataset.package=packageData?.id||'';
      mapping.innerHTML='<label>'+text('SEAGM paket ID','ID пакета SEAGM','SEAGM product type ID')+'<input name="supplier_type_id" inputmode="numeric" pattern="[0-9]*" maxlength="20" value="'+esc(packageData?.supplier_type_id||'')+'" placeholder="'+text('Katalogdan tanlang','Выберите из каталога','Select from catalog')+'"><small>'+text('Katalogdan mos o‘yin/hudud paketini tanlab ID sini kiriting.','Выберите соответствующую игру/регион в каталоге.','Map the matching game and region package from the supplier catalog.')+'</small></label><button class="button-secondary" type="submit">'+text('SEAGM ID ni saqlash','Сохранить ID SEAGM','Save SEAGM mapping')+'</button>';
      card.querySelector('.topup-admin-package-body')?.append(mapping);
      const actions=document.createElement('section');actions.className='topup-admin-package-actions';
      actions.innerHTML=packageData?.enabled?`<p>${text('Paket katalogdan olib tashlanadi. Buyurtmalar tarixi va qoldiq saqlanadi; “O‘chirilgan / yashirilgan” filtridan tiklash mumkin.','Пакет будет убран из каталога. Заказы и остаток сохранятся; восстановление доступно через фильтр «Удалённые / скрытые».','Remove this package from the catalog. Orders and stock stay intact; restore it from the Deleted / hidden filter.')}</p><button type="button" class="button-danger" data-topup-delete>${text('Paketni o‘chirish','Удалить пакет','Delete package')}</button><div class="topup-admin-delete-confirm" hidden><p role="alert">${text('Ushbu paketni katalogdan olib tashlaysizmi?','Убрать этот пакет из каталога?','Remove this package from the catalog?')}</p><div><button type="button" class="button-danger" data-topup-delete-confirm="${esc(packageData.id)}">${text('Ha, o‘chirish','Да, удалить','Yes, delete')}</button><button type="button" class="button-secondary" data-topup-delete-cancel>${text('Bekor qilish','Отмена','Cancel')}</button></div></div>`:`<p>${text('Paket katalogda ko‘rinmaydi. Tiklasangiz, oldingi narx va qoldiq bilan yana ko‘rinadi.','Пакет скрыт. При восстановлении сохранятся прежняя цена и остаток.','This package is hidden. Restoring keeps its previous price and stock.')}</p><button type="button" class="button-secondary" data-topup-restore="${esc(packageData?.id||'')}">${text('Paketni tiklash','Восстановить пакет','Restore package')}</button>`;
      card.querySelector('.topup-admin-package-body')?.append(actions);
    });
    const applyFilters=()=>{
      const query=$('[data-topup-search]',root).value.trim().toLocaleLowerCase(), game=$('[data-topup-game-filter]',root).value, filter=$('[data-topup-status-filter]',root).value;
      let visible=0;
      $$('.topup-admin-package',root).forEach(card=>{
        const p=packages.find(item=>item.id===card.querySelector('.topup-admin-save')?.dataset.package), matchesQuery=!query||card.dataset.search.includes(query), matchesGame=!game||card.dataset.game===game;
        const matchesStatus=topupAdminMatchesStatus(p,filter);
        card.hidden=!(matchesQuery&&matchesGame&&matchesStatus); if(!card.hidden)visible++;
      });
      $('.topup-admin-no-results',root).hidden=visible>0;
    };
    root.addEventListener('input',event=>{
      if(event.target.matches('[data-topup-search]'))applyFilters();
      if(event.target.matches('.topup-admin-create input[name=game_slug]')){
        const form=event.target.form,existing=topupAdminExistingGame(packages,event.target.value);
        form.elements.game_name.readOnly=Boolean(existing);
        if(existing){form.elements.game_name.value=existing.game_name;if(!form.elements.currency.value.trim())form.elements.currency.value=existing.currency}
        form.elements.game_name.closest('div').querySelector('small').textContent=existing?text('Mavjud o‘yin: uning nomi saqlanadi. Valyuta, Pass yoki Pack turini kiritishingiz mumkin.','Существующая игра: название сохраняется. Можно указать валюту, Pass или Pack.','Existing game: its name is reused. You can use currency, Pass, or Pack for the package unit.'):text('O‘yin nomi mijozlarga ko‘rinadi.','Название увидят покупатели.','Shown to customers.');
      }
    });
    root.addEventListener('change',event=>{if(event.target.matches('[data-topup-game-filter],[data-topup-status-filter]'))applyFilters();});
    applyFilters();
    root.addEventListener('click',async event=>{
      const button=event.target.closest('[data-topup-delete],[data-topup-delete-confirm],[data-topup-delete-cancel],[data-topup-restore]');
      if(!button||button.disabled)return;
      const actions=button.closest('.topup-admin-package-actions'),confirmation=actions.querySelector('.topup-admin-delete-confirm');
      if(button.hasAttribute('data-topup-delete')){button.hidden=true;confirmation.hidden=false;confirmation.querySelector('button').focus();return}
      if(button.hasAttribute('data-topup-delete-cancel')){confirmation.hidden=true;const trigger=actions.querySelector('[data-topup-delete]');trigger.hidden=false;trigger.focus();return}
      const restore=button.hasAttribute('data-topup-restore'),id=restore?button.dataset.topupRestore:button.dataset.topupDeleteConfirm;
      const buttons=[...actions.querySelectorAll('button')];buttons.forEach(control=>control.disabled=true);
      actions.querySelector('.topup-admin-action-error')?.remove();
      try{
        await api('/admin/top-up/packages/'+encodeURIComponent(id),{method:'PATCH',body:JSON.stringify({enabled:restore})});
        await renderTopUpAdmin();
        toast(restore?text('Paket tiklandi.','Пакет восстановлен.','Package restored.'):text('Paket katalogdan olib tashlandi.','Пакет убран из каталога.','Package removed from the catalog.'));
      }catch(error){
        buttons.forEach(control=>control.disabled=false);
        const message=document.createElement('p');message.className='notice error topup-admin-action-error';message.setAttribute('role','alert');message.textContent=error.message;actions.append(message);
      }
    });
    root.addEventListener('submit', async function(event) {
      const form = event.target; if (!form.matches('.topup-admin-save,.topup-stock-adjust,.topup-admin-create,.topup-supplier-map')) return; event.preventDefault();
      form.querySelector('.topup-admin-form-error')?.remove();
      const values = new FormData(form);
      const submit=form.querySelector('[type="submit"]'); if(submit){submit.disabled=true;submit.classList.add('is-loading');}
      try {
        if (form.matches('.topup-supplier-map')) await api('/admin/top-up/packages/' + encodeURIComponent(form.dataset.package), {method:'PATCH', body:JSON.stringify({supplier_type_id:values.get('supplier_type_id')||''})});
        else if (form.matches('.topup-admin-save')) await api('/admin/top-up/packages/' + encodeURIComponent(form.dataset.package), {method:'PATCH', body:JSON.stringify({price_minor:Number(values.get('price_minor')), enabled:values.has('enabled'), coming_soon:values.has('coming_soon'), manual_enabled:values.has('manual_enabled')})});
        else if (form.matches('.topup-admin-create')) await api('/admin/top-up/packages', {method:'POST', body:JSON.stringify({game_name:values.get('game_name'),game_slug:values.get('game_slug'),currency:values.get('currency'),amount:Number(values.get('amount')),url_slug:values.get('url_slug'),price_minor:Number(values.get('price_minor')),coming_soon:values.has('coming_soon')})});
        else await api('/admin/top-up/inventory', {method:'POST', body:JSON.stringify({package_id:form.dataset.package,delta:Number(values.get('delta')),reason:values.get('reason')})});
        await renderTopUpAdmin();
        const refreshedNotice=$('.topup-admin-notice');
        if(refreshedNotice)refreshedNotice.innerHTML='<div class="notice topup-admin-success">'+text('O‘zgarish muvaffaqiyatli saqlandi.','Изменения успешно сохранены.','Changes saved successfully.')+'</div>';
      } catch (error) {
        if(submit){submit.disabled=false;submit.classList.remove('is-loading');}
        const box=document.createElement('p');box.className='notice error topup-admin-form-error';box.setAttribute('role','alert');box.textContent=error.message;form.prepend(box);
        const invalid=Object.keys(error.fields||{}).map(name=>form.elements.namedItem(name)).find(Boolean);
        if(invalid)invalid.focus();else box.scrollIntoView({block:'nearest',behavior:'smooth'});
      }
    });
  } catch (error) { root.innerHTML = '<div class="notice error">' + esc(error.message) + '</div><button class="button-secondary" data-topup-retry>' + text('Qayta urinish','Повторить','Try again') + '</button>'; root.addEventListener('click',event=>{if(event.target.closest('[data-topup-retry]'))renderTopUpAdmin();},{once:true}); }
}

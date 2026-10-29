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
    catalog: adminText('O‘yin valutasini Top Up qilish','Пополнение игровых валют','Game top ups'),
    intro: adminText('Sevimli o‘yiningizni tanlang — kerakli valyuta paketini topib, alohida sahifasini oching.','Выберите игру, найдите нужный пакет валюты и откройте его отдельную страницу.','Pick your game, find the right currency pack, and open its own product page.'),
    games: adminText('O‘yinlar','Игры','Games'), packs: adminText('Paketlar','Пакеты','Packs'),
    select: adminText('O‘yinni tanlang','Выберите игру','Choose your game'),
    feature: adminText('O‘yin valutasini oson to‘ldiring','Пополняйте игровой баланс легко','Power up your game')
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
    renderTopUpDetail(game, currentPackage);
    return;
  } else {
    body = '<div class="topup-games-grid">' + rows.map(function(item, index) {
      const currencyIcon = topupCurrencyImage(item, 'catalog');
      return '<article class="topup-game-card topup-game-' + esc(item.slug) + '"><a class="topup-game-cover" href="/top-up/' + encodeURIComponent(item.slug) + '" aria-label="' + esc(item.name) + '"><picture><source media="(max-width:840px)" srcset="/static/assets/' + TOPUP_MOBILE_GAME_ART[item.slug] + '"><img data-topup-fallback="https://images.gamestorehub.com/site-assets/topup-' + esc(item.slug) + '.svg" src="' + TOPUP_OFFICIAL_GAME_ART[item.slug] + '" alt="' + esc(item.name) + '" loading="' + (index < 2 ? 'eager' : 'lazy') + '"' + (index < 2 ? ' fetchpriority="high"' : '') + '></picture><span class="topup-game-cover-shade"></span></a><div class="topup-game-card-body"><div class="topup-currency-row"><span class="topup-currency-icon">' + currencyIcon + '</span><span>' + esc(item.currency) + '</span></div><h2>' + esc(item.name) + '</h2>' + (item.review_summary?.count ? '<span class="pr-card-rating">★ ' + Number(item.review_summary.rating).toFixed(1) + ' <small>(' + Number(item.review_summary.count) + ')</small></span>' : '') + '<a class="topup-game-cta" href="/top-up/' + encodeURIComponent(item.slug) + '">Top Up</a></div></article>';
    }).join('') + '</div>';
  }
  const catalogContent = '<div class="topup-hero topup-hero-image"><nav class="topup-breadcrumb topup-hero-back" aria-label="Breadcrumb"></nav><img class="topup-hero-background" src="https://images.gamestorehub.com/site-assets/topup-hero.jpg" alt="" fetchpriority="high"><div class="topup-hero-overlay"></div><div class="topup-hero-content"><div class="topup-hero-brand"><b>Sentry<span class="brand-dot">Loot</span></b></div><h1>' + esc(words.feature) + '</h1><p>' + words.intro + '</p></div></div>' + body + '<aside class="topup-safe-note">' + icon('shield') + '<p><b>' + adminText('Xaridlar va to‘lovlar','Покупки и оплата','Payments are being prepared') + '</b><br>' + adminText('To‘lov tizimi ulangach paketlarni xarid qilish mumkin bo‘ladi.','Пакеты можно будет купить после подключения платёжной системы.','Packages will be available to buy once a payment provider is connected.') + '</p></aside>';
  app.innerHTML = '<section class="page topup-page">' + (game ? body : catalogContent) + '</section>';
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

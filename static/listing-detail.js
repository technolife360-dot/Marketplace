/* Product detail presentation. Prices, identity and history come from the listing API. */
window.ListingDetail = (() => {
  const t = (...text) => adminText(...text);
  function facts(item) {
    const a = item.attributes || {};
    const missing=t('Ko‘rsatilmagan','Не указано','Not specified');
    const rows = [
      [t('Hudud','Регион','Region'),[...new Set([item.region,a.server,a.server_id].filter(Boolean))].join(' · ') || missing],
      [t('Platforma','Платформа','Platform'),item.platform || missing],
    ];
    if (item.product_type === 'account') {
      const linked=a.linked_accounts||a.linked_services||[];
      const services=(Array.isArray(linked)?linked:String(linked).split(',')).filter(Boolean).map(key=>listingProviders.find(p=>p[0]===String(key).trim().toLowerCase())?.[1]||String(key).trim()).join(', ');
      const transfer=String(a.transferable??'').toLowerCase();
      rows.push(
        [t('Akkaunt darajasi','Уровень аккаунта','Account level'),a.account_level || missing],
        [t('Reyting','Ранг','Rank'),a.tier || a.competitive_rank || a.current_rank || a.rank || missing],
        [t('Original email','Оригинальная почта','Original email'),originalEmail(item) === 'yes' ? t('Kiritilgan','Включена','Included') : originalEmail(item) === 'no' ? t('Kiritilmagan','Не включена','Not included') : missing],
        [t('Ulangan xizmatlar','Привязанные сервисы','Linked services'),services || missing],
        [t('O‘tkazish mumkin','Можно передать','Transferable'),['yes','true'].includes(transfer)?t('Ha','Да','Yes'):['no','false'].includes(transfer)?t('Yo‘q','Нет','No'):missing]
      );
    } else rows.push([t('Original email','Оригинальная почта','Original email'),originalEmail(item)==='yes'?t('Kiritilgan','Включена','Included'):originalEmail(item)==='no'?t('Kiritilmagan','Не включена','Not included'):missing],...listingAttributeFacts(item));
    for (const [key,label] of [['condition',t('Holati','Состояние','Condition')],['rarity',t('Noyobligi','Редкость','Rarity')],['float_value','Float'],['mmr','MMR'],['prime_status','Prime']]) {
      if (a[key]) rows.push([label,a[key]]);
    }
    return rows.filter(([,value]) => value !== undefined && value !== null && value !== '');
  }
  function originalEmail(item) {
    const value=item.attributes?.original_email_included;
    return value===true||['yes','included','true'].includes(String(value).toLowerCase())?'yes':value===false||['no','false','excluded'].includes(String(value).toLowerCase())?'no':'unknown';
  }
  function deliveryMarkup(item) {
    const account=item.product_type==='account',email=originalEmail(item);
    const svg=(path)=>`<svg viewBox="0 0 24 24" aria-hidden="true">${path}</svg>`;
    const clock=svg('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),right=svg('<path d="m9 5 7 7-7 7"/>'),mail=svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 6 9 7 9-7"/>'),lock=svg('<rect x="4" y="10" width="16" height="12" rx="2"/><path d="M7 10V6a5 5 0 0 1 10 0v4M12 15v3"/>'),shield=svg('<path d="m12 2 8 3v6c0 5-5 9-8 11-3-2-8-6-8-11V5l8-3Z"/><path d="m8 11 3 3 5-5"/>');
    const eta=item.delivery_eta||t('Buyurtmada ko‘rsatilgan muddat','Срок указан в заказе','Time shown in your order');
    const timing=item.delivery_method==='manual'?t('To‘lovdan keyin qo‘lda yetkaziladi: ','Ручная доставка после оплаты: ','Delivered manually after payment: ')+eta:t('Yetkazish muddati: ','Срок доставки: ','Delivery time: ')+eta;
    const emailText=email==='yes'?t('Original email kiritilgan','Оригинальная почта включена','Original email included'):email==='no'?t('Original email kiritilmagan','Оригинальная почта не включена','Original email not included'):t('Original email: ko‘rsatilmagan','Оригинальная почта: не указано','Original email: not specified');
    return `<section class="mobile-listing-delivery-view" hidden><h1>${t('Yetkazish va talablar','Доставка и требования','Delivery & requirements')}</h1><div class="sim-delivery-notice">${clock}<span>${esc(timing)}</span></div><h2>${t('Nima olasiz','Что вы получите','What you receive')}</h2>${account?`<button type="button" class="sim-delivery-row" data-mobile-details>${mail}<span>${emailText}</span>${right}</button><button type="button" class="sim-delivery-row" data-mobile-details>${lock}<span>${t('Akkauntni maxfiy topshirish','Конфиденциальная передача аккаунта','Private account handover')}</span>${right}</button>`:`<div class="sim-delivery-row">${lock}<span>${t('Buyurtma sahifasi orqali yetkazish','Доставка через страницу заказа','Delivery through your order page')}</span></div>`}<div class="sim-delivery-after"><h2>${t('Xariddan keyin','После покупки','After purchase')}</h2><p>${account?t('Buyurtma sahifangizdagi bosqichlarni bajaring. Kirish ma’lumotlarini olgach login va tiklash ma’lumotlarini almashtiring.','Следуйте шагам на странице заказа. Получив доступ, измените данные входа и восстановления.','Follow the steps on your order page. Change the login and recovery details after receiving access.'):t('Yetkazishni buyurtma sahifangizda kuzating. Mahsulotni tekshirgandan keyin qabul qilganingizni tasdiqlang.','Следите за доставкой в заказе. Подтвердите получение после проверки товара.','Follow delivery on your order page. Confirm receipt after checking your item.')}</p></div>${item.requirements?`<div class="sim-delivery-after"><h2>${t('Talablar','Требования','Requirements')}</h2><p data-user-content>${esc(item.requirements)}</p></div>`:''}<div class="sim-delivery-notice">${shield}<span>${t('Parollarni ommaviy xabarlarda yubormang.','Не отправляйте пароли в публичных сообщениях.','Never send passwords in public messages.')}</span></div></section>`;
  }
  function markup(item) {
    const seller = item.seller || {}, identity = marketSellerIdentity(item);
    const stock = item.status === 'published' ? Math.max(0,Number(item.available) || 0) : 0;
    const available = stock > 0 && stock >= (item.min_quantity || 1) && !item.availability?.vacation;
    const verified = Boolean(item.identity_verified);
    const count = Number(item.seller_card_review_count) || 0;
    const listingCount = Number(item.product_review_count) || 0;
    const rating = count && Number(item.seller_card_rating) > 0 ? Number(item.seller_card_rating).toFixed(1) : '';
    const saved = Boolean(item.is_favorite), id = esc(item.id);
    const stockText = item.availability?.vacation ? t('Sotuvchi ta’tilda','Продавец в отпуске','Seller away') : available ? `${t('Mavjud','В наличии','In stock')} · ${stock} ${t('dona','шт.','available')}` : item.status === 'sold_out' ? t('Sotilib bo‘lgan','Продано','Sold out') : t('Hozir mavjud emas','Сейчас недоступно','Currently unavailable');
    const photo = identity.avatar ? `<img src="${esc(identity.avatar)}" alt="" width="48" height="48" loading="lazy" referrerpolicy="no-referrer">` : '';
    const productLabel = item.category_id === 'top-ups' ? t('Top Up','Пополнение','Top-ups') : categoryLabel(item.product_type);
    const about = item.product_type === 'account' ? t('Akkaunt haqida','Об аккаунте','About this account') : t('Mahsulot haqida','О товаре','About this product');
    const factRows = facts(item);
    return `<section class="page listing-detail-page listing-redesign">
      <nav class="listing-breadcrumbs" aria-label="${t('Sahifa yo‘li','Навигация','Breadcrumb')}"><a href="/browse">${t('Bozor','Маркет','Marketplace')}</a><span>/</span><a href="/browse?game=${encodeURIComponent(item.game_slug || '')}">${esc(item.game_name)}</a><span>/</span><span>${esc(productLabel)}</span></nav>
      <div class="listing-reference-grid"><div class="listing-left-column">
        ${listingDetailGallery(item)}
        <section class="listing-info-panel" aria-label="${t('Mahsulot ma’lumotlari','Информация о товаре','Product information')}">
          <nav class="listing-detail-tabs" aria-label="${t('Mahsulot bo‘limlari','Разделы товара','Product sections')}">
            ${[['description',t('Tavsif','Описание','Description')],['specifications',t('Tafsilotlar','Подробности','Details')],['reviews',`${t('Sharhlar','Отзывы','Reviews')}${listingCount ? ` (${listingCount})` : ''}`]].map(([key,label],i) => `<a href="#listing-panel-${key}" data-listing-jump="${key}" ${i === 0 ? 'aria-current="location"' : ''}>${label}</a>`).join('')}
          </nav>
          <section id="listing-panel-description" class="listing-content-section" tabindex="-1"><h2>${about}</h2><div id="listing-description" class="detail-desc is-collapsed" data-user-content>${esc(item.description)}</div><button type="button" id="listing-description-toggle" class="description-toggle" aria-controls="listing-description" aria-expanded="false" hidden>${t('To‘liq o‘qish','Читать полностью','Read full description')}</button></section>
          <section id="listing-panel-specifications" class="listing-content-section listing-details-section" tabindex="-1" aria-label="${t('Tafsilotlar','Подробности','Details')}"><dl class="listing-facts">${factRows.map(([label,value]) => `<div data-listing-overview="${[t('Hudud','Регион','Region'),t('Platforma','Платформа','Platform'),t('Original email','Оригинальная почта','Original email')].includes(label)}"><dt>${esc(label)}</dt><dd data-user-content>${esc(value)}</dd></div>`).join('')}</dl></section>
          <section id="listing-panel-reviews" class="listing-content-section" data-listing-panel="reviews" tabindex="-1" aria-label="${t('Xaridorlar sharhlari','Отзывы покупателей','Buyer reviews')}"></section>
          <div class="listing-info-footer"><button type="button" data-action="report-listing" data-id="${id}">${icon('shield')}${t('Xabar berish','Пожаловаться','Report listing')}</button><small>${t('E’lon sanasi','Дата объявления','Listed')} ${esc(String(item.created_at || '').slice(0,10))}</small></div>
        </section>
      </div><div class="listing-right-column">
        <aside class="detail-panel listing-purchase-panel" aria-label="${t('Xarid ma’lumotlari','Покупка','Purchase details')}">
          <p class="listing-item-meta">${esc(item.game_name)} · ${esc(productLabel)}</p>
          <h1 data-user-content>${esc(item.title)}</h1>
          <span class="listing-stock ${available ? '' : 'is-sold-out'}"><i></i>${esc(stockText)}</span>
          <div class="price" data-listing-price>${fmt(item.price_minor,item.currency)}</div>
          <button type="button" class="button-primary listing-buy-button" data-action="buy-now" data-id="${id}" ${available ? '' : 'disabled'}>${t('Xarid qilish','Купить','Buy now')}<span aria-hidden="true">→</span></button>
          <div class="listing-secondary-actions">${item.is_owner ? `<button type="button" class="button-secondary" disabled title="${t('Bu sizning e’loningiz','Это ваше объявление','This is your own listing')}">${icon('message')}${t('Sotuvchiga yozish','Написать продавцу','Message seller')}</button>` : `<button type="button" class="button-secondary" data-action="contact-seller" data-id="${id}" ${item.status !== 'published' ? 'disabled' : ''}>${icon('message')}${t('Sotuvchiga yozish','Написать продавцу','Message seller')}</button>`}</div>
          <p class="listing-delivery-summary">${icon('clock')}<span>${esc(item.delivery_eta || t('Yetkazishni sotuvchidan aniqlang','Уточните доставку у продавца','Confirm delivery time with seller'))}</span></p>
          <section class="listing-seller-panel" aria-label="${t('Sotuvchi','Продавец','Seller')}">
            <div class="listing-seller-profile-row"><span class="listing-seller-avatar"><span aria-hidden="true">${esc(identity.name.slice(0,1).toUpperCase())}</span>${photo}</span><div class="listing-seller-identity"><b>${esc(identity.name)}${verified ? `<span class="listing-verified" aria-label="${t('Shaxsi tasdiqlangan','Личность подтверждена','Identity verified')}">${icon('shield')}</span>` : ''}</b><small>${verified ? t('Shaxsi tasdiqlangan','Личность подтверждена','Identity verified') : seller.online ? t('Hozir saytda','Сейчас на сайте','Online now') : t('Sotuvchi','Продавец','Seller')}</small></div><a class="listing-store-link" href="/store/${encodeURIComponent(item.store_id || item.seller_id)}">${t('Do‘kon','Магазин','View store')} ↗</a></div>
            <div class="listing-seller-metrics"><span>${icon('star')}${rating ? `<b>${rating}</b><span>(${count})</span>` : `<span>${t('Hali sharh yo‘q','Пока нет отзывов','No reviews yet')}</span>`}</span><span><b>${Math.max(0,Number(item.seller_sales_count) || 0)}</b> ${t('sotuv','продаж','sales')}</span></div>
          </section>
          <div class="listing-save-share"><button type="button" class="listing-wishlist ${saved ? 'saved' : ''}" data-action="favorite" data-id="${id}" data-saved="${saved ? '1' : '0'}" aria-pressed="${saved}">${icon('heart')}${saved ? t('Saqlangan','Сохранено','Saved') : t('Saqlash','Сохранить','Save')}</button><button type="button" data-action="share">${icon('share')}${t('Ulashish','Поделиться','Share')}</button></div>
        </aside>
        <section class="listing-trust-panel"><div>${icon('shield')}<h2>${t('Buyurtma himoyasi','Защита заказа','Order protection')}</h2></div><p>${t('Yetkazishni buyurtma sahifasida kuzating. Muammo yuzaga kelsa, yordamga murojaat qiling.','Отслеживайте доставку в заказе. Если возникнет проблема, обратитесь за помощью.','Track delivery through your order page. Get help if an issue occurs.')}</p><a href="/help/orders">${t('Shartlarni ko‘rish','Посмотреть условия','View terms')} →</a></section>
        <details class="listing-delivery-details"><summary><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M1 4h13v13H1V4ZM14 9h5l4 5v3h-9M5 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm14 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/></svg><span>${t('Yetkazish va talablar','Доставка и требования','Delivery & requirements')}</span><svg class="icon listing-details-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m3 7.5 9 9 9-9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></summary><div class="listing-delivery-body" data-listing-delivery><p data-user-content>${esc(item.requirements || t('Talablar buyurtma berish paytida ko‘rsatiladi.','Требования указаны при оформлении заказа.','Delivery requirements are shown during checkout.'))}</p></div></details>
        <div data-listing-payment-note></div>
      </div></div>
      ${deliveryMarkup(item)}
      ${item.related?.length ? `<section class="listing-related"><h2>${t('O‘xshash e’lonlar','Похожие объявления','Related listings')}</h2><div class="product-grid">${item.related.map(marketCard).join('')}</div></section>` : ''}
    </section>`;
  }
  function setup(root) {
    root.querySelector('.listing-delivery-details>summary')?.addEventListener('click',event=>{if(window.MobileSite?.isMobile()){event.preventDefault();window.MobileSite.listingPanel('delivery');}});
    root.querySelectorAll('[data-mobile-details]').forEach(button=>button.onclick=()=>window.MobileSite?.listingPanel('specifications'));
    root.querySelectorAll('[data-listing-jump]').forEach(link => link.addEventListener('click',event => {
      event.preventDefault();
      const target = root.querySelector('#listing-panel-' + link.dataset.listingJump);
      root.querySelectorAll('[data-listing-jump]').forEach(other => other.removeAttribute('aria-current'));
      link.setAttribute('aria-current','location');
      if(window.MobileSite?.isMobile()){window.MobileSite.listingPanel(link.dataset.listingJump);return;}
      target?.focus({preventScroll:true});
      target?.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
    }));
    root.querySelectorAll('.listing-seller-avatar img').forEach(image => image.addEventListener('error',() => { image.hidden = true; }));
  }
  return {markup,facts,setup,deliveryMarkup,originalEmail};
})();

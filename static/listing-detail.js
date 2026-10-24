/* Product detail presentation. Prices, identity and history come from the listing API. */
window.ListingDetail = (() => {
  const t = (...text) => adminText(...text);
  function facts(item) {
    const a = item.attributes || {};
    const rows = [
      [t('Hudud / server','Регион / сервер','Region / server'), [item.region,a.server,a.server_id].filter(Boolean).join(' · ')],
      [t('Platforma','Платформа','Platform'), item.platform],
      ...listingAttributeFacts(item),
    ];
    if (item.product_type === 'account') {
      rows.push(
        [t('Akkaunt darajasi','Уровень аккаунта','Account level'),a.account_level],
        [t('Reyting','Ранг','Rank'),a.tier || a.competitive_rank || a.current_rank || a.rank],
        [t('Original email','Оригинальная почта','Original email'),a.original_email_included === 'yes' ? t('Kiritilgan','Включена','Included') : a.original_email_included === 'no' ? t('Kiritilmagan','Не включена','Not included') : ''],
        [t('Ulangan xizmatlar','Привязанные сервисы','Linked services'),(a.linked_accounts || []).map(key => listingProviders.find(p => p[0] === key)?.[1] || key).join(', ')]
      );
    }
    for (const [key,label] of [['condition',t('Holati','Состояние','Condition')],['rarity',t('Noyobligi','Редкость','Rarity')],['float_value','Float'],['mmr','MMR'],['prime_status','Prime']]) {
      if (a[key]) rows.push([label,a[key]]);
    }
    return rows.filter(([,value]) => value !== undefined && value !== null && value !== '');
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
          <section id="listing-panel-specifications" class="listing-content-section listing-details-section" tabindex="-1" aria-label="${t('Tafsilotlar','Подробности','Details')}"><dl class="listing-facts">${factRows.map(([label,value]) => `<div><dt>${esc(label)}</dt><dd data-user-content>${esc(value)}</dd></div>`).join('')}</dl></section>
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
        <details class="listing-delivery-details"><summary>${icon('box')}<span>${t('Yetkazish va talablar','Доставка и требования','Delivery & requirements')}</span><svg class="icon listing-details-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m3 7.5 9 9 9-9" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></summary><div class="listing-delivery-body" data-listing-delivery><p data-user-content>${esc(item.requirements || t('Talablar buyurtma berish paytida ko‘rsatiladi.','Требования указаны при оформлении заказа.','Delivery requirements are shown during checkout.'))}</p></div></details>
        <div data-listing-payment-note></div>
      </div></div>
      ${item.related?.length ? `<section class="listing-related"><h2>${t('O‘xshash e’lonlar','Похожие объявления','Related listings')}</h2><div class="product-grid">${item.related.map(marketCard).join('')}</div></section>` : ''}
    </section>`;
  }
  function setup(root) {
    root.querySelectorAll('[data-listing-jump]').forEach(link => link.addEventListener('click',event => {
      event.preventDefault();
      const target = root.querySelector('#listing-panel-' + link.dataset.listingJump);
      root.querySelectorAll('[data-listing-jump]').forEach(other => other.removeAttribute('aria-current'));
      link.setAttribute('aria-current','location');
      target?.focus({preventScroll:true});
      target?.scrollIntoView({block:'start',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
    }));
    root.querySelectorAll('.listing-seller-avatar img').forEach(image => image.addEventListener('error',() => { image.hidden = true; }));
  }
  return {markup,facts,setup};
})();

/* SentryLoot administrative console. Uses authenticated first-party APIs only. */
window.AdminConsole = (() => {
  let context, panelSequence = 0;
  const chartObservers = new Map();
  const palette = ['#ff9b42', '#fa647c', '#a682fa', '#559af6', '#94a3b8'];
  const categories = {
    advertising: ['Reklama', 'Реклама', 'Advertising'], infrastructure: ['Infratuzilma', 'Инфраструктура', 'Infrastructure'],
    provider: ['To‘lov provayderi', 'Платёжный провайдер', 'Payment provider'], support: ['Support', 'Поддержка', 'Support'], other: ['Boshqa', 'Прочее', 'Other']
  };
  const tr = (...values) => context.adminText(...values);
  const esc = value => context.esc(value);
  const money = (value, currency) => context.fmt(value, currency);
  const label = key => categories[key] ? tr(...categories[key]) : key;
  const today = () => new Date().toISOString().slice(0, 10);
  const empty = text => `<div class="ac-empty">${esc(text)}</div>`;
  const headings = {
    overview: ['Biznes ko‘rsatkichlari', 'Показатели бизнеса', 'Business overview'],
    finance: ['Daromad va xarajatlar', 'Доходы и расходы', 'Revenue & expenses'],
    audit: ['Audit jurnali', 'Журнал аудита', 'Audit log'],
    management: ['Sayt boshqaruvi', 'Управление сайтом', 'Site management']
  };
  function shell(root, ctx) {
    context = ctx; stop(); root.classList.add('admin-premium');
    const nav = root.querySelector('.admin-nav');
    const old = new Map([...nav.querySelectorAll('[data-admin-view-target]')].map(el => [el.dataset.adminViewTarget, el]));
    const make = (view, glyph, text) => {
      if (old.has(view)) return old.get(view).outerHTML;
      return `<button class="admin-nav-item" data-admin-view-target="${view}"><span>${ctx.icon(glyph)}<b>${esc(text)}</b></span></button>`;
    };
    const link = (route, glyph, text) => `<a class="admin-nav-item" href="/#${route}"><span>${ctx.icon(glyph)}<b>${esc(text)}</b></span></a>`;
    const group = text => `<span class="admin-nav-label">${esc(text)}</span>`;
    nav.innerHTML = group(tr('BOSHQARUV', 'УПРАВЛЕНИЕ', 'MANAGEMENT')) +
      make('overview','gamepad',tr('Umumiy ko‘rinish','Обзор','Overview')) + make('listings') + make('orders') +
      link('top-up-admin','wallet','Top Up') + make('sellers') + make('users') +
      group(tr('MOLIYA','ФИНАНСЫ','FINANCE')) + make('finance','wallet',tr('Daromad va xarajatlar','Доходы и расходы','Revenue & expenses')) +
      make('payouts') + group(tr('ISHONCH','ДОВЕРИЕ','TRUST')) + make('disputes') + make('account-reviews') + make('reports') +
      link('admin-support','message',tr('Support','Поддержка','Support')) + link('review-moderation','star',tr('Sharhlar','Отзывы','Reviews')) +
      group(tr('KONTENT VA TIZIM','КОНТЕНТ И СИСТЕМА','CONTENT & SYSTEM')) +
      link('catalog-readiness','gamepad',tr('O‘yinlar va katalog','Игры и каталог','Games & catalogue')) +
      link('admin-blog','box',tr('Blog va maqolalar','Блог и статьи','Blog & articles')) +
      link('launch-settings','users',tr('Jamoa va biznes profili','Команда и профиль','Team & business profile')) +
      make('management','settings',tr('Sayt boshqaruvi','Управление сайтом','Site management')) +
      make('audit','shield',tr('Audit jurnali','Журнал аудита','Audit log')) + make('settings');
    root.querySelectorAll('.admin-sidebar > a.admin-nav-item').forEach(el => el.remove());
    const profile = root.querySelector('.admin-profile');
    root.querySelector('.admin-sidebar-foot').before(profile);
    profile.insertAdjacentHTML('beforeend',`<a href="/#account" class="ac-profile-link" aria-label="${tr('Hisob sozlamalari','Настройки аккаунта','Account settings')}">${ctx.icon('settings')}</a>`);
    root.querySelector('.admin-brand small').textContent = 'ADMIN CONSOLE';
    root.querySelector('.admin-brand b').innerHTML = 'Sentry<span>Loot</span>';
    const views = root.querySelector('.admin-views');
    ['finance','audit','management'].forEach(name => views.insertAdjacentHTML('beforeend', `<span hidden data-admin-heading="${name}">${esc(tr(...headings[name]))}</span><section class="admin-view" data-admin-view="${name}" hidden></section>`));
    root.querySelector('[data-admin-heading="overview"]').textContent = tr(...headings.overview);
    root.querySelector('.admin-topbar p').textContent = tr('Daromad, xarajat va do‘kon faoliyatini bir joyda kuzating.','Доходы, расходы и работа магазина в одном месте.','Your revenue, expenses and store operations in one place.');
    root.querySelector('.admin-topbar').insertAdjacentHTML('beforebegin', `<div class="ac-toolbar"><span>${ctx.icon('shield')} ADMIN / SENTRYLOOT</span><a class="ac-account-link" href="/#account">${tr('Hisobim','Мой аккаунт','My account')}</a><label class="ac-nav-search">${ctx.icon('search')}<input type="search" name="section" autocomplete="off" id="ac-nav-search" placeholder="${tr('Bo‘limni qidirish…','Найти раздел…','Find a section…')}" aria-label="${tr('Admin bo‘limini qidirish','Поиск раздела админ-панели','Search admin sections')}"></label><button type="button" class="button-secondary" data-ac-menu aria-expanded="false">${ctx.icon('menu')}${tr('Menyu','Меню','Menu')}</button></div>`);
    root.querySelector('[data-ac-menu]').onclick = e => { const open=root.classList.toggle('ac-menu-open'); e.currentTarget.setAttribute('aria-expanded',String(open)); if(open)nav.querySelector('.admin-nav-item')?.focus(); };
    root.addEventListener('keydown',event=>{if(event.key==='Escape'&&root.classList.contains('ac-menu-open')){root.classList.remove('ac-menu-open');const button=root.querySelector('[data-ac-menu]');button.setAttribute('aria-expanded','false');button.focus();}});
    root.querySelector('#ac-nav-search').oninput = event => {
      const q=event.target.value.toLocaleLowerCase().trim();
      nav.querySelectorAll('.admin-nav-item').forEach(el => { el.hidden=!el.textContent.toLocaleLowerCase().includes(q); });
      root.classList.toggle('ac-searching',Boolean(q));
    };
    nav.addEventListener('click', event => {
      if (event.target.closest('.admin-nav-item')) { root.classList.remove('ac-menu-open'); root.querySelector('[data-ac-menu]').setAttribute('aria-expanded','false'); }
    });
  }
  function stop() { for (const observer of chartObservers.values()) observer.disconnect(); chartObservers.clear(); panelSequence++; }
  function queue(o) {
    const items=[['listings','pending_listings',tr('Tekshiriladigan e’lonlar','Объявления на проверке','Listings to review')],['sellers','pending_sellers',tr('Sotuvchi tasdiqlari','Проверки продавцов','Seller verification')],['disputes','open_disputes',tr('Ochiq nizolar','Открытые споры','Open disputes')],['reports','open_reports',tr('Shikoyatlar','Жалобы','Reports')]];
    return `<article class="ac-card"><h2>${tr('Boshqaruv navbati','Очередь задач','Work queue')}</h2><div class="ac-queue">${items.map(([view,key,text],i)=>`<button data-admin-view-target="${view}">${context.icon(['box','users','shield','bell'][i])}<span>${text}</span><b>${esc(o[key]??0)}</b>${context.icon('arrow-up-right')}</button>`).join('')}</div></article>`;
  }
  function table(headers, rows, caption='') {
    return `<div class="ac-table-scroll"><table class="ac-table">${caption?`<caption>${esc(caption)}</caption>`:''}<thead><tr>${headers.map(h=>`<th scope="col">${h}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div>`;
  }
  function financeMarkup(d, o, filters) {
    const c=d.currency, book=d.book==='live'?tr('HAQIQIY HISOB','РЕАЛЬНЫЙ УЧЁТ','LIVE BOOK'):d.book==='sandbox'?'SANDBOX · TEST':'STRIPE · TEST';
    const kpis=[['cart',tr('Savdo hajmi (GMV)','Объём продаж (GMV)','Paid sales (GMV)'),d.gmv_minor,tr('To‘langan mahsulotlar qiymati','Стоимость оплаченных товаров','Paid merchandise value')],['box',tr('Platforma daromadi','Доход платформы','Platform revenue'),d.revenue_minor,tr('Ledgerda qayd etilgan komissiya','Комиссия в учётном журнале','Recognized ledger commission')],['wallet',tr('Xarajatlar','Расходы','Expenses'),d.expense_minor,tr('Kiritilgan operatsion xarajatlar','Записанные операционные расходы','Recorded operating expenses')],['arrow-up-right',tr('Hisoblangan foyda','Расчётная прибыль','Recorded profit'),d.profit_minor,tr('Daromad − kiritilgan xarajatlar','Доход − записанные расходы','Revenue − recorded expenses')]];
    const rows=d.categories.map((r,i)=>`<li><span class="ac-legend-dot" style="--series:${palette[i%5]}"></span><span>${esc(label(r.category))}</span><b>${money(r.amount_minor,c)}</b><small>${(r.amount_minor/Math.max(1,d.expense_minor)*100).toFixed(1)}%</small></li>`).join('');
    const gameMax=Math.max(1,...d.games.map(g=>Math.abs(g.amount_minor)));
    const expenses=d.expenses.map(r=>`<tr class="${r.voided_at?'ac-voided':''}"><td>${esc(r.incurred_on)}</td><td>${esc(label(r.category))}</td><td>${esc(r.description)}</td><td class="ac-numeric">${money(r.amount_minor,c)}</td><td>${r.voided_at?`<span title="${esc(r.void_reason)}">${tr('Bekor qilingan','Аннулировано','Voided')}</span>`:`<button type="button" class="ac-text-button" data-ac-void="${esc(r.id)}">${tr('Bekor qilish','Аннулировать','Void')}</button>`}</td></tr>`).join('');
    const events=[...d.commissions.map(r=>({...r,kind:tr('Komissiya','Комиссия','Commission'),description:r.reference,signed:r.amount_minor})),...d.expenses.filter(r=>!r.voided_at).map(r=>({...r,kind:label(r.category),signed:-r.amount_minor}))].sort((a,b)=>String(b.created_at).localeCompare(String(a.created_at))).slice(0,6);
    return `<div class="ac-tabs"><button type="button" class="is-active" data-ac-tab="analysis" aria-pressed="true">${tr('Moliyaviy tahlil','Финансовый анализ','Financial analysis')}</button><button type="button" data-ac-tab="expenses" aria-pressed="false">${tr('Xarajatlar jurnali','Журнал расходов','Expense ledger')}</button><button type="button" data-admin-view-target="sellers">${tr('Sotuvchilar','Продавцы','Sellers')}</button><span class="ac-book ${d.test_only?'is-test':''}">${book}</span></div>
    <form class="ac-filters" data-ac-filters><label>${tr('Boshlanish','Начало','From')}<input type="date" name="start" required min="2000-01-01" max="${today()}" value="${d.start}"></label><label>${tr('Tugash','Конец','To')}<input type="date" name="end" required min="2000-01-01" max="${today()}" value="${d.end}"></label><label>${tr('Hisob','Учёт','Book')}<select name="book">${[['live',tr('Haqiqiy','Реальный','Live')],['sandbox','Sandbox'],['stripe_test','Stripe test']].map(([v,l])=>`<option value="${v}" ${d.book===v?'selected':''}>${l}</option>`).join('')}</select></label><label>${tr('Valyuta','Валюта','Currency')}<select name="currency">${d.currencies.map(v=>`<option ${c===v?'selected':''}>${esc(v)}</option>`).join('')}</select></label><button class="button-secondary" type="submit">${context.icon('search')}${tr('Ko‘rsatish','Показать','Apply')}</button><button class="button-secondary" type="button" data-ac-export>${tr('CSV yuklash','Скачать CSV','Export CSV')}</button><button class="button-primary" type="button" data-ac-add>${context.icon('plus')}${tr('Xarajat qo‘shish','Добавить расход','Add expense')}</button></form>
    <p class="ac-scope">${d.test_only?tr('Sinov hisobi — bu summalar haqiqiy daromad emas.','Тестовый учёт — суммы не являются реальным доходом.','Test book — these amounts are not real earnings.'):tr('Haqiqiy hisob — sinov to‘lovlari kiritilmaydi.','Реальный учёт — тестовые платежи исключены.','Live book — test payments are excluded.')} · UTC · ${tr('Marketplace buyurtmalari; Top Up marjasi kiritilmagan.','Заказы маркетплейса; маржа Top Up не включена.','Marketplace orders; Top Up margin is not included.')}</p>
    <div class="ac-kpis">${kpis.map(([glyph,title,value,sub])=>`<article class="ac-kpi"><span class="ac-kpi-icon">${context.icon(glyph)}</span><div><span>${title}</span><strong>${money(value,c)}</strong><small>${sub}</small></div></article>`).join('')}</div>
    <div data-ac-pane="analysis"><div class="ac-chart-grid"><article class="ac-card"><div class="ac-card-heading"><h2>${tr('Daromad, xarajat va foyda','Доходы, расходы и прибыль','Revenue, expenses & profit')}</h2><span>UTC · ${esc(c)}</span></div><div class="ac-chart"><canvas data-ac-line role="img" aria-label="${tr('Kunlik daromad, xarajat va foyda grafigi. Quyidagi jadvalda raqamlar berilgan.','График доходов, расходов и прибыли. Значения в таблице ниже.','Daily revenue, expenses and profit. Values are in the table below.')}"></canvas></div><div class="ac-legend">${[tr('Daromad','Доход','Revenue'),tr('Xarajatlar','Расходы','Expenses'),tr('Foyda','Прибыль','Profit')].map((x,i)=>`<span><i style="--series:${palette[i]}"></i>${x}</span>`).join('')}</div><details class="ac-chart-values"><summary>${tr('Kunlik raqamlar','Значения по дням','View daily values')}</summary>${table([tr('Sana','Дата','Date'),tr('Daromad','Доход','Revenue'),tr('Xarajat','Расход','Expense'),tr('Foyda','Прибыль','Profit')],d.daily.map(x=>`<tr><td>${x.day}</td><td>${money(x.revenue_minor,c)}</td><td>${money(x.expense_minor,c)}</td><td>${money(x.profit_minor,c)}</td></tr>`).join(''))}</details></article>
    <article class="ac-card"><h2>${tr('Xarajatlar tarkibi','Структура расходов','Expense breakdown')}</h2><div class="ac-breakdown"><div class="ac-donut"><canvas data-ac-donut role="img" aria-label="${tr('Xarajatlar kategoriya bo‘yicha; qiymatlar yonidagi ro‘yxatda.','Расходы по категориям; значения в соседнем списке.','Expenses by category; values listed alongside.')}"></canvas><div><strong>${money(d.expense_minor,c)}</strong><small>${tr('Jami xarajat','Всего расходов','Total expenses')}</small></div></div><ul>${rows||`<li>${tr('Xarajat hali kiritilmagan.','Расходы ещё не записаны.','No expenses recorded yet.')}</li>`}</ul></div></article></div>
    <div class="ac-middle-grid"><article class="ac-card"><h2>${tr('Pul qayerdan kelmoqda?','Откуда поступают деньги?','Where does revenue come from?')}</h2>${table([tr('Manba','Источник','Source'),tr('Miqdor','Сумма','Amount')],`<tr><td>${tr('Qayd etilgan komissiyalar','Учтённые комиссии','Recognized commissions')}</td><td class="ac-numeric">${money(d.revenue_minor,c)}</td></tr><tr><td>${tr('Operatsion xarajatlar','Операционные расходы','Recorded operating expenses')}</td><td class="ac-numeric">− ${money(d.expense_minor,c)}</td></tr><tr class="ac-total"><td>${tr('Hisoblangan foyda','Расчётная прибыль','Recorded profit')}</td><td class="ac-numeric">${money(d.profit_minor,c)}</td></tr>`)}<p class="ac-footnote">${tr('Foyda faqat kiritilgan xarajatlarni ayiradi. Provayder haqi, soliq va boshqa sarflarni ham jurnalga kiriting.','Прибыль учитывает только записанные расходы. Внесите комиссии провайдера, налоги и остальные затраты.','Profit subtracts recorded expenses only. Record provider fees, taxes and other costs in the ledger.')}</p></article>
    <article class="ac-card"><h2>${tr('O‘yinlar bo‘yicha daromad','Доход по играм','Revenue by game')}</h2><div class="ac-games">${d.games.slice(0,8).map((g,i)=>`<div><span class="ac-game-name">${context.gameArt?.[g.slug]?`<img src="${esc(context.gameArt[g.slug])}" alt="" width="28" height="28" loading="lazy">`:''}${esc(g.name)}</span><meter min="0" max="${gameMax}" value="${Math.abs(g.amount_minor)}" style="--series:${palette[i%5]}" aria-label="${esc(g.name)}"></meter><b>${money(g.amount_minor,c)}</b></div>`).join('')||empty(tr('Komissiya qayd etilgach o‘yinlar shu yerda ko‘rinadi.','Игры появятся после учёта комиссии.','Games appear here once commission is recorded.'))}</div><p class="ac-footnote">${tr('Buyurtma komissiyasi mahsulotlar qiymatiga mutanosib taqsimlangan.','Комиссия распределена пропорционально стоимости товаров.','Order commission allocated in proportion to line-item value.')}</p></article></div>
    <div class="ac-operation-counts">${[[tr('Bugungi buyurtmalar','Заказы сегодня','Orders today'),o.today_orders],[tr('Yakunlangan buyurtmalar','Завершённые заказы','Completed orders'),o.completed_orders],[tr('Faol e’lonlar','Активные объявления','Active listings'),o.active_listings],[tr('Foydalanuvchilar','Пользователи','Users'),o.users]].map(([name,value])=>`<div><span>${name}</span><b>${esc(value??0)}</b></div>`).join('')}</div>
    <div class="ac-bottom-grid">${queue(o)}<article class="ac-card"><h2>${tr('So‘nggi moliyaviy yozuvlar','Последние финансовые записи','Recent financial entries')}</h2>${events.length?table([tr('Turi','Тип','Type'),tr('Tavsif','Описание','Description'),tr('Miqdor','Сумма','Amount')],events.map(r=>`<tr><td>${esc(r.kind)}</td><td>${esc(r.description)}</td><td class="ac-numeric ${r.signed>=0?'ac-positive':'ac-negative'}">${r.signed>=0?'+':''}${money(r.signed,c)}</td></tr>`).join('')):empty(tr('Tanlangan davrda yozuvlar yo‘q.','В выбранном периоде нет записей.','No entries in this period.'))}</article></div></div>
    <section class="ac-card" data-ac-pane="expenses" hidden><div class="ac-card-heading"><h2>${tr('Xarajatlar jurnali','Журнал расходов','Expense ledger')}</h2><span>${d.expenses.length} / ${d.expense_count}</span></div>${expenses?table([tr('Sana','Дата','Date'),tr('Kategoriya','Категория','Category'),tr('Tavsif','Описание','Description'),tr('Miqdor','Сумма','Amount'),tr('Holat','Статус','Status')],expenses):empty(tr('Xarajat qo‘shish tugmasidan boshlang.','Начните с кнопки «Добавить расход».','Start with Add expense.'))}<p class="ac-footnote">${tr('Oxirgi 100 yozuv. Eski yozuvlar uchun davrni qisqartiring. Bekor qilingan yozuvlar audit uchun saqlanadi.','Последние 100 записей. Сузьте период для старых записей. Аннулированные записи сохраняются для аудита.','Latest 100 entries. Narrow the period for older records. Voided entries remain available for audit.')}</p></section>
    <p class="ac-footnote">${tr('GMV: davrda yaratilgan, muvaffaqiyatli to‘langan buyurtmalar qiymati. Daromad: davrda ledgerga yozilgan komissiya; escrow daromad hisoblanmaydi.','GMV: оплаченные заказы, созданные в периоде. Доход: комиссии, записанные в периоде; эскроу не является доходом.','GMV: successfully paid orders created in the period. Revenue: commission posted during the period; escrow is not revenue.')}</p><div data-ac-form-slot></div>`;
  }
  function drawCharts(root, d) {
    chartObservers.get(root)?.disconnect();
    const redraw=()=>{ if (!root.isConnected || root.hidden) return; drawLine(root.querySelector('[data-ac-line]'),d); drawDonut(root.querySelector('[data-ac-donut]'),d); };
    const observer=new ResizeObserver(redraw);chartObservers.set(root,observer); root.querySelectorAll('canvas').forEach(el=>observer.observe(el)); redraw();
  }
  function canvasContext(canvas) {
    const width=canvas.clientWidth,height=canvas.clientHeight;if(!width||!height)return null;
    const ratio=Math.min(window.devicePixelRatio||1,2);canvas.width=width*ratio;canvas.height=height*ratio;
    const ctx=canvas.getContext('2d');ctx.scale(ratio,ratio);ctx.font='11px system-ui';return {ctx,width,height};
  }
  function drawLine(canvas,d) {
    const surface=canvasContext(canvas);if(!surface)return;const {ctx,width:w,height:h}=surface;
    const left=58,right=14,top=18,bottom=30,pw=w-left-right,ph=h-top-bottom;
    const fields=['revenue_minor','expense_minor','profit_minor'],values=d.daily.flatMap(r=>fields.map(k=>r[k]));
    let low=Math.min(0,...values),high=Math.max(1,...values);const span=high-low;high+=span*.1;if(low<0)low-=span*.1;
    const y=v=>top+(high-v)/(high-low)*ph,x=i=>left+(d.daily.length===1?pw/2:i/(d.daily.length-1)*pw);
    const short=n=>new Intl.NumberFormat(document.documentElement.lang||'en',{notation:'compact',maximumFractionDigits:1}).format(d.currency==='MYR'?n/100:n);
    for(let i=0;i<=4;i++){const value=low+(high-low)*i/4,py=y(value);ctx.strokeStyle='#292929';ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(w-right,py);ctx.stroke();ctx.fillStyle='#a9b1bd';ctx.textAlign='right';ctx.fillText(short(value),left-8,py+4);}
    const step=Math.max(1,Math.ceil((d.daily.length-1)/4));ctx.textAlign='center';ctx.fillStyle='#a9b1bd';
    d.daily.forEach((r,i)=>{if(i%step===0||i===d.daily.length-1)ctx.fillText(r.day.slice(5),x(i),h-7);});
    fields.forEach((field,index)=>{ctx.strokeStyle=palette[index];ctx.lineWidth=2;ctx.lineJoin='round';ctx.beginPath();d.daily.forEach((r,i)=>i?ctx.lineTo(x(i),y(r[field])):ctx.moveTo(x(i),y(r[field])));ctx.stroke();if(d.daily.length===1){ctx.fillStyle=palette[index];ctx.beginPath();ctx.arc(x(0),y(d.daily[0][field]),3,0,Math.PI*2);ctx.fill();}});
  }
  function drawDonut(canvas,d) {
    const surface=canvasContext(canvas);if(!surface)return;const {ctx,width:w,height:h}=surface;const radius=Math.min(w,h)/2-12;
    ctx.lineWidth=23;let angle=-Math.PI/2;ctx.strokeStyle='#292929';ctx.beginPath();ctx.arc(w/2,h/2,radius,0,Math.PI*2);ctx.stroke();
    d.categories.forEach((r,i)=>{const arc=r.amount_minor/Math.max(1,d.expense_minor)*Math.PI*2;ctx.strokeStyle=palette[i%5];ctx.beginPath();ctx.arc(w/2,h/2,radius,angle,angle+arc);ctx.stroke();angle+=arc;});
  }
  function exportDaily(d) {
    const rows=[['date_utc','currency','book','revenue_minor','expense_minor','profit_minor'],...d.daily.map(r=>[r.day,d.currency,d.book,r.revenue_minor,r.expense_minor,r.profit_minor])];
    const blob=new Blob(['\ufeff'+rows.map(r=>r.join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');
    a.href=url;a.download=`sentryloot-${d.book}-${d.currency}-${d.start}-${d.end}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  function expenseForm(root,d,refresh) {
    const slot=root.querySelector('[data-ac-form-slot]');
    slot.innerHTML=`<dialog class="ac-dialog"><form data-ac-expense><div class="ac-card-heading"><h2>${tr('Xarajat qo‘shish','Добавить расход','Add expense')}</h2><button type="button" class="button-secondary" data-ac-close aria-label="${tr('Yopish','Закрыть','Close')}">${context.icon('x')}</button></div><p>${esc(d.currency)} · ${d.book==='live'?tr('Haqiqiy hisob','Реальный учёт','Live book'):esc(d.book)+' · TEST'}</p><div class="field"><label for="ac-expense-description">${tr('Tavsif','Описание','Description')}</label><input id="ac-expense-description" name="description" required minlength="3" maxlength="300" autocomplete="off"></div><div class="ac-form-pair"><div class="field"><label for="ac-expense-amount">${tr('Miqdor','Сумма','Amount')} (${esc(d.currency)})</label><input id="ac-expense-amount" name="amount" type="number" required min="${d.currency==='MYR'?'0.01':'1'}" max="${d.currency==='MYR'?'10000000000':'1000000000000'}" step="${d.currency==='MYR'?'0.01':'1'}" inputmode="decimal"></div><div class="field"><label for="ac-expense-date">${tr('Sana (UTC)','Дата (UTC)','Date (UTC)')}</label><input id="ac-expense-date" name="incurred_on" type="date" required min="2000-01-01" max="${today()}" value="${today()}"></div></div><div class="field"><label for="ac-expense-category">${tr('Kategoriya','Категория','Category')}</label><select id="ac-expense-category" name="category">${Object.keys(categories).map(k=>`<option value="${k}">${esc(label(k))}</option>`).join('')}</select></div><p class="ac-footnote">${tr('Bu amal xarajatni qayd etadi; bankdan pul yechmaydi.','Это запись расхода, а не списание денег со счёта.','This records an expense; it does not charge a bank account.')}</p><p class="ac-form-error" role="alert" tabindex="-1"></p><button class="button-primary" type="submit">${tr('Xarajatni saqlash','Сохранить расход','Save expense')}</button></form></dialog>`;
    const dialog=slot.querySelector('dialog'),form=slot.querySelector('form'),key=crypto.randomUUID();
    dialog.showModal();dialog.querySelector('[data-ac-close]').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{slot.innerHTML='';root.querySelector('[data-ac-add]').focus();},{once:true});
    form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;const fields=Object.fromEntries(new FormData(form)), amount=fields.amount.trim();
      try {if(!/^\d+(?:\.\d{1,2})?$/.test(amount)||(d.currency!=='MYR'&&amount.includes('.')))throw Error(tr('Miqdorni tekshiring.','Проверьте сумму.','Check the amount.'));
        const units=d.currency==='MYR'?Number(amount.split('.')[0])*100+Number((amount.split('.')[1]||'').padEnd(2,'0')):Number(amount);
        await context.api('/admin/expenses',{method:'POST',body:JSON.stringify({id:key,amount_minor:units,currency:d.currency,book:d.book,category:fields.category,description:fields.description,incurred_on:fields.incurred_on})});
        dialog.close();context.toast(tr('Xarajat saqlandi','Расход сохранён','Expense recorded'));await refresh();
      }catch(error){form.querySelector('[role=alert]').textContent=error.message;form.querySelector('[role=alert]').focus();}finally{button.disabled=false;}
    };
  }
  function voidForm(root,id,refresh) {
    const slot=root.querySelector('[data-ac-form-slot]');
    slot.innerHTML=`<dialog class="ac-dialog"><form><h2>${tr('Xarajatni bekor qilish','Аннулировать расход','Void expense')}</h2><p>${tr('Yozuv auditda saqlanadi, lekin foyda hisobidan chiqariladi.','Запись сохранится в аудите, но исключится из расчёта прибыли.','The record remains in the audit trail but is excluded from profit calculations.')}</p><div class="field"><label for="ac-void-reason">${tr('Sabab','Причина','Reason')}</label><textarea id="ac-void-reason" name="reason" required minlength="5" maxlength="300"></textarea></div><p role="alert" class="ac-form-error" tabindex="-1"></p><div class="actions"><button class="button-danger" type="submit">${tr('Bekor qilishni tasdiqlash','Подтвердить аннулирование','Confirm void')}</button><button class="button-secondary" type="button" data-ac-close>${tr('Yopish','Закрыть','Close')}</button></div></form></dialog>`;
    const dialog=slot.querySelector('dialog'),form=slot.querySelector('form');dialog.showModal();dialog.querySelector('[data-ac-close]').onclick=()=>dialog.close();dialog.onclose=()=>{slot.innerHTML='';root.querySelector('[data-ac-tab="expenses"]')?.focus();};
    form.onsubmit=async event=>{event.preventDefault();const button=form.querySelector('[type=submit]');if(button.disabled)return;button.disabled=true;try{await context.api('/admin/expenses/'+encodeURIComponent(id)+'/void',{method:'POST',body:JSON.stringify({reason:new FormData(form).get('reason')})});dialog.close();await refresh();}catch(error){form.querySelector('[role=alert]').textContent=error.message;form.querySelector('[role=alert]').focus();}finally{button.disabled=false;}};
  }
  async function mountFinance(root,o={}) {
    let filters={start:today().slice(0,8)+'01',end:today(),book:'live',currency:'UZS'},tab='analysis',request=0;
    const token=panelSequence;
    async function refresh() {
      const version=++request;root.setAttribute('aria-busy','true');
      if(!root.querySelector('[data-ac-filters]'))root.innerHTML=`<div class="loading" role="status">${tr('Moliyaviy hisobot yuklanmoqda…','Загрузка финансового отчёта…','Loading financial report…')}</div>`;
      try {
        const d=await context.api('/admin/finance?'+new URLSearchParams(filters));if(!root.isConnected||token!==panelSequence||version!==request)return;
        root.innerHTML=financeMarkup(d,o,filters);
        const selectTab=name=>{tab=name;root.querySelectorAll('[data-ac-pane]').forEach(el=>el.hidden=el.dataset.acPane!==name);root.querySelectorAll('[data-ac-tab]').forEach(el=>{const active=el.dataset.acTab===name;el.classList.toggle('is-active',active);el.setAttribute('aria-pressed',String(active));});if(name==='analysis')drawCharts(root,d);};
        root.querySelectorAll('[data-ac-tab]').forEach(el=>el.onclick=()=>selectTab(el.dataset.acTab));selectTab(tab);
        root.querySelector('[data-ac-filters]').onsubmit=event=>{event.preventDefault();filters=Object.fromEntries(new FormData(event.currentTarget));refresh();};
        root.querySelector('[data-ac-export]').onclick=()=>exportDaily(d);
        root.querySelector('[data-ac-add]').onclick=()=>expenseForm(root,d,refresh);
        root.querySelectorAll('[data-ac-void]').forEach(el=>el.onclick=()=>voidForm(root,el.dataset.acVoid,refresh));
      }catch(error){if(root.isConnected&&token===panelSequence&&version===request){const old=root.querySelector('.ac-report-error');old?.remove();root.insertAdjacentHTML('afterbegin',`<div class="notice error ac-report-error" role="alert">${esc(error.message)} <button type="button" class="button-secondary" data-ac-retry>${tr('Qayta urinish','Повторить','Retry')}</button></div>`);root.querySelector('[data-ac-retry]').onclick=refresh;}}
      finally{if(root.isConnected&&version===request)root.setAttribute('aria-busy','false');}
    }
    await refresh();
  }
  function management(root) {
    const cards=[['catalog-readiness','gamepad',tr('Katalog va sifat','Каталог и качество','Catalogue & quality'),tr('E’lonlar talablari, sotuvga tayyorlik va o‘yinlar kesimi.','Требования к объявлениям, готовность к продаже и игры.','Listing requirements, readiness and games.')],['top-up-admin','wallet','Top Up',tr('Paketlar, narxlar, qoldiq va yetkazib berish.','Пакеты, цены, остатки и доставка.','Packages, pricing, inventory and fulfilment.')],['admin-blog','box',tr('Kontent','Контент','Content'),tr('Uch tildagi maqolalarni yaratish va nashr qilish.','Создание и публикация статей на трёх языках.','Create and publish articles in three languages.')],['launch-settings','settings',tr('Biznes va jamoa','Бизнес и команда','Business & team'),tr('Ommaviy profil, yordam va xodim ruxsatlari.','Публичный профиль, поддержка и права сотрудников.','Public profile, support and staff permissions.')],['admin-support','message','Support',tr('Murojaatlar, javoblar va holatlarni boshqarish.','Обращения, ответы и статусы.','Manage requests, replies and status.')],['stripe-test','shield','Stripe sandbox',tr('Sinov integratsiyasi va to‘lov oqimi.','Тестовая интеграция и платёжный процесс.','Test integration and payment flow.')]];
    root.innerHTML=`<div class="ac-management">${cards.map(([route,glyph,title,copy])=>`<a class="ac-card" href="/#${route}">${context.icon(glyph)}<h2>${title}</h2><p>${copy}</p><span>${tr('Boshqarish','Управлять','Manage')} ${context.icon('arrow-up-right')}</span></a>`).join('')}</div>`;
  }
  async function audit(root) {
    const rows=await context.api('/admin/audit');if(!root.isConnected)return;
    root.innerHTML=`<article class="ac-card"><div class="ac-card-heading"><h2>${tr('Oxirgi 100 boshqaruv amali','Последние 100 действий','Latest 100 administrative actions')}</h2><button class="button-secondary" data-ac-refresh>${tr('Yangilash','Обновить','Refresh')}</button></div><label class="ac-audit-search">${tr('Amal yoki obyekt ID si','Действие или ID объекта','Action or entity ID')}<input type="search" name="audit_search" autocomplete="off" data-ac-audit-search></label><div data-ac-audit-results></div></article>`;
    const render=q=>{const filtered=rows.filter(r=>[r.action,r.entity_type,r.entity_id,r.actor_id].join(' ').toLowerCase().includes(q));root.querySelector('[data-ac-audit-results]').innerHTML=filtered.length?table([tr('Sana (UTC)','Дата (UTC)','Date (UTC)'),tr('Amal','Действие','Action'),tr('Obyekt','Объект','Entity'),tr('Admin ID','ID администратора','Admin ID')],filtered.map(r=>`<tr><td>${esc(r.created_at)}</td><td>${esc(r.action)}</td><td>${esc(r.entity_type)}<small>${esc(r.entity_id)}</small></td><td><code>${esc(r.actor_id||'system')}</code></td></tr>`).join('')):empty(tr('Yozuv topilmadi.','Записи не найдены.','No entries found.'));};
    render('');root.querySelector('[data-ac-audit-search]').oninput=e=>render(e.target.value.toLowerCase());root.querySelector('[data-ac-refresh]').onclick=async e=>{const button=e.currentTarget;button.disabled=true;try{await audit(root);}catch(error){context.toast(error.message,'error');button.disabled=false;}};
  }
  return {shell,stop,mountFinance,management,audit};
})();

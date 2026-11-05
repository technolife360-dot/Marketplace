/* The wheel displays a server-selected award; client animation never chooses prizes. */
window.SpinWin = (() => {
  const t=(uz,ru,en)=>adminText(uz,ru,en), h=v=>esc(v??''), post=(path,data)=>api(path,{method:'POST',body:JSON.stringify(data)});
  const money=minor=>'RM'+(Number(minor)/100).toFixed(2);
  const name=p=>p.kind==='none'?t('Bu safar sovrin yo‘q','В этот раз без приза','No prize this time'):p.name||p.prize_name;
  const date=value=>new Date(value).toLocaleString(typeof localeTag==='function'?localeTag():'en');
  const status=s=>({new:t('Yangi','Новый','New'),contacted:t('Bog‘lanildi','Связались','Contacted'),shipped:t('Yuborildi','Отправлен','Shipped'),delivered:t('Topshirildi','Вручён','Delivered'),saved_for_live_topup:t('Jonli Top Up uchun saqlandi','Сохранён для реального пополнения','Saved for live Top Up'),credited:t('Bonusga tushdi','Бонус начислен','Credited'),no_prize:t('Sovrinsiz','Без приза','No prize')})[s]||s;
  const mode=d=>d.test_only?`<p class="sw-test">${t('SINOV REJIMI · haqiqiy sovrin yoki pul berilmaydi','ТЕСТОВЫЙ РЕЖИМ · без реальных призов или денег','TEST MODE · no real prizes or money')}</p>`:'';
  const odds=prizes=>`<div class="sw-odds"><h2>${t('Yutish imkoniyatlari','Вероятности выигрыша','Prize probabilities')}</h2><p>${t('Budjetda kamida RM1 qolgan bo‘lsa, birinchi aylantirishda RM1 beriladi. Quyidagi ehtimollar odatdagi aylantirishlarga tegishli.','Если в бюджете осталось хотя бы RM1, первая попытка приносит RM1. Ниже указаны шансы для обычных попыток.','The first spin awards RM1 when at least RM1 remains in the budget. The odds below apply to regular spins.')}</p><ul>${prizes.map(p=>`<li><span>${h(name(p))}</span><b>${(p.weight/1000).toFixed(3)}%</b></li>`).join('')}</ul></div>`;
  function wheel(prizes,centerAction=''){
    const count=prizes.length, step=360/count;
    const art=prizes.map((p,i)=>{
      const a=(i*step-90)*Math.PI/180,b=((i+1)*step-90)*Math.PI/180;
      const fill=p.kind==='physical'?'#513322':p.kind==='none'?'#222128':i%2?'#352720':'#222a37';
      const path=count===1?'<circle cx="200" cy="200" r="177" fill="#222128"/>':
        `<path d="M200 200 L${200+177*Math.cos(a)} ${200+177*Math.sin(a)} A177 177 0 ${step>180?1:0} 1 ${200+177*Math.cos(b)} ${200+177*Math.sin(b)} Z" fill="${fill}" stroke="#c38a55" stroke-opacity=".55" stroke-width="1.5"/>`;
      const lines=p.kind==='none'?[t('Sovrin','Без','No'),t('yo‘q','приза','prize')]:
        p.id==='iphone'?['iPhone','18 Pro']:p.id==='ps5'?['PS5']:p.id==='tv'?['Smart','TV']:[name(p)];
      const angle=(i+.5)*step;
      const flip=angle>90&&angle<270?180:0;
      return path+`<text x="200" y="85" transform="rotate(${angle} 200 200) rotate(${flip} 200 80)" text-anchor="middle" fill="${p.kind==='physical'?'#ffcf93':'#fff5e8'}" font-size="16" font-weight="700">${lines.map((line,n)=>`<tspan x="200" y="${lines.length===1?85:77+n*16}">${h(line)}</tspan>`).join('')}</text>`;
    }).join('');
    const studs=Array.from({length:30},(_,i)=>{
      const angle=i*Math.PI/15;
      return `<circle cx="${200+187*Math.cos(angle)}" cy="${200+187*Math.sin(angle)}" r="2.4" fill="#f5c18a"/>`;
    }).join('');
    return `<div class="sw-wheel-wrap">
      <svg class="sw-pointer" viewBox="0 0 26 28" aria-hidden="true"><path d="M3 1h20a2 2 0 0 1 2 3L15 25a2 2 0 0 1-4 0L1 4a2 2 0 0 1 2-3Z" fill="#ffd39c"/></svg>
      <svg class="sw-wheel" viewBox="0 0 400 400" role="img" aria-label="${t('Sovrinlar g‘ildiragi','Колесо призов','Prize wheel')}">
        <circle cx="200" cy="200" r="194" fill="#382719" stroke="#e7aa69" stroke-width="2"/>
        ${studs}${art}<circle cx="200" cy="200" r="177" fill="none" stroke="#c38a55" stroke-width="2"/>
        ${centerAction?'':`<circle cx="200" cy="200" r="42" fill="#1a1515" stroke="#d49457" stroke-width="3"/>
        <circle cx="200" cy="200" r="34" fill="#f6b570"/>
        <text x="200" y="208" text-anchor="middle" fill="#25170f" font-size="25" font-weight="800">SL</text>`}
      </svg>
      ${centerAction}
    </div>`;
  }
  function prizeInstructions(record){
    if(record.kind!=='physical'||record.test_only)return '';
    if(record.status==='new')return t(
      'Sovrin raqamini saqlang. Yutuq tekshirilgach, SentryLoot jamoasi yetkazishni kelishish uchun tasdiqlangan emailingizga yozadi.',
      'Сохраните номер приза. После проверки выигрыша команда SentryLoot напишет на вашу подтверждённую почту, чтобы согласовать доставку.',
      'Keep your prize reference. After reviewing the win, the SentryLoot team will email your verified address to arrange delivery.');
    if(record.status==='contacted')return t(
      'Yetkazish bo‘yicha SentryLoot xabarini emailingizdan tekshiring.',
      'Проверьте почту: команда SentryLoot отправила инструкции по доставке.',
      'Check your inbox for delivery instructions from SentryLoot.');
    return '';
  }
  function result(record){
    if(!record)return '';
    const instruction=prizeInstructions(record);
    const description=instruction||(record.status==='saved_for_live_topup'
      ?t('Vaucher saqlandi. Jonli Top Up yoqilgach ishlatishingiz mumkin.','Ваучер сохранён. Его можно использовать после запуска реальных пополнений.','Voucher saved. You can use it when live Top Up payments are enabled.')
      :record.kind==='voucher'
        ?t('Bonus avtomatik Top Up balansiga tushdi.','Бонус автоматически зачислен для Top Up.','Your Top Up bonus was credited automatically.')
        :record.kind==='physical'
          ?t('Sovrin holati yangilandi.','Статус приза обновлён.','Your prize status is up to date.')
          :t('Keyingi kuni yana urinib ko‘ring.','Попробуйте снова завтра.','Try again tomorrow.'));
    const reference=record.kind==='physical'
      ?`<small>${t('Sovrin raqami','Номер приза','Prize reference')} ${h(record.id)} · ${h(status(record.status))}</small>`:'';
    return `<div class="sw-result" role="status"><b>${h(name(record))}</b><span>${h(description)}</span>${reference}</div>`;
  }
  function historyList(records){
    if(!records.length)return `<p>${t('Hali aylantirmadingiz.','Вы ещё не крутили колесо.','You have not spun yet.')}</p>`;
    return `<ul>${records.map(record=>{
      const instruction=prizeInstructions(record);
      return `<li>
      <div><b>${h(name(record))}</b><small>${h(date(record.created_at))} · ${h(record.id)}</small>${instruction?`<small>${h(instruction)}</small>`:''}</div>
      <span>${h(status(record.status))}</span>
    </li>`;
    }).join('')}</ul>`;
  }
  async function customer(){
    if(!me){location.hash='login';return;}
    const route=location.href,data=await api('/spin-win');if(location.href!==route)return;
    document.title='Spin & Win | SentryLoot';
    app.innerHTML=`<section class="page sw-page"><header class="sw-heading"><div><span class="sw-eyebrow">SENTRYLOOT REWARDS</span><h1>Spin & Win</h1><p>${t('Har kuni bitta bepul imkoniyat.','Одна бесплатная попытка каждый день.','One free chance every day.')}</p></div><a class="button-secondary" href="/#rewards">${t('Bonuslarim','Мои бонусы','My rewards')} →</a></header>${mode(data)}<div class="sw-layout"><section class="sw-play">${wheel(data.prizes)}<button type="button" class="button-primary sw-spin" ${data.can_spin?'':'disabled'}>${data.can_spin?t('Bepul aylantirish','Крутить бесплатно','Spin for free'):!data.enabled?t('Hozir sovrinlar mavjud emas','Сейчас призов нет','No prizes available right now'):t('Bugungi spin ishlatildi','Попытка на сегодня использована','Today’s spin is used')}</button><p class="sw-reset">${t('Keyingi yangilanish','Следующее обновление','Next reset')}: ${h(date(data.next_reset))}<br>00:00 Asia/Kuala_Lumpur</p><p class="sw-error" role="alert" hidden></p><div data-sw-result>${result(data.today)}</div></section></div><section class="sw-history"><h2>${t('Mening natijalarim','Мои результаты','My results')}</h2><div data-sw-history>${historyList(data.history)}</div></section></section>`;
    bindSpin(app.querySelector('.sw-page'),data);
  }
  function bindSpin(root,data){
    const button=root.querySelector('.sw-spin');
    if(!button||!data.can_spin)return;
    button.addEventListener('click',async()=>{
      button.disabled=true;
      const error=root.querySelector('.sw-error');
      error.hidden=true;
      try{
        const award=await post('/spin-win/spin',{});
        if(!root.isConnected)return;
        const index=data.prizes.findIndex(prize=>prize.id===award.prize_id);
        if(index>=0){
          root.querySelector('.sw-wheel').style.transform=`rotate(${1800-(index+.5)*360/data.prizes.length}deg)`;
          if(!matchMedia('(prefers-reduced-motion: reduce)').matches){
            await new Promise(resolve=>setTimeout(resolve,2450));
          }
        }
        if(!root.isConnected)return;
        root.querySelector('[data-sw-result]').innerHTML=result(award);
        const spinStatus=root.querySelector('[data-sw-state]')||button;
        spinStatus.textContent=t('Bugungi spin ishlatildi','Попытка на сегодня использована','Today’s spin is used');
        const history=root.querySelector('[data-sw-history]');
        if(history)history.innerHTML=historyList([award,...data.history.filter(record=>record.id!==award.id)].slice(0,30));
        if(award.kind==='physical'||award.kind==='voucher')celebrate(root);
      }catch(e){
        if(root.isConnected){
          error.textContent=e.message;
          error.hidden=false;
          button.disabled=false;
        }
      }
    });
  }
  function celebrate(root){
    if(!root?.isConnected)return;
    root.querySelector('.sw-result')?.classList.add('sw-result-won');
    if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
    const wheelFrame=root.querySelector('.sw-wheel-wrap');
    if(!wheelFrame)return;
    const confetti=document.createElement('div');
    confetti.className='sw-confetti';
    confetti.setAttribute('aria-hidden','true');
    const colors=['#ffc36f','#ff7ba7','#83e6c3','#a7a0ff','#73caff','#fff4d2'];
    for(let i=0;i<54;i++){
      const piece=document.createElement('i');
      const angle=i*2.39996;
      const distance=75+Math.random()*150;
      piece.style.setProperty('--x',`${Math.cos(angle)*distance}px`);
      piece.style.setProperty('--y',`${Math.sin(angle)*distance-70}px`);
      piece.style.setProperty('--fall',`${Math.sin(angle)*distance+70}px`);
      piece.style.setProperty('--turn',`${i%2?620:-620}deg`);
      piece.style.setProperty('--color',colors[i%colors.length]);
      piece.style.animationDelay=`${(i%6)*32}ms`;
      confetti.append(piece);
    }
    wheelFrame.append(confetti);
    setTimeout(()=>confetti.remove(),1900);
  }
  const dismissedFor=new Set();
  async function home(dialog){
    if(!dialog||!me?.email_verified)return;
    const visitor=me.id;
    if(dialog.open||dismissedFor.has(visitor))return;

    try{
      const data=await api('/spin-win');
      if(!dialog.isConnected||dialog.open||dismissedFor.has(visitor)||!data.enabled)return;

      const canSpin=data.can_spin;
      const spinLabel=t('Bepul aylantirish','Крутить бесплатно','Spin for free');
      const state=canSpin?'':t('Bugungi spin ishlatildi','Попытка на сегодня использована','Today’s spin is used');
      const centerAction=`<button class="sw-hub sw-spin" type="button" aria-label="${h(spinLabel)}" ${canSpin?'':'disabled'}>SPIN</button>`;
      const closeLabel=t('Oynani yopish','Закрыть окно','Close dialog');
      dialog.innerHTML=`
        <button class="sw-popup-close" type="button" aria-label="${h(closeLabel)}" autofocus>×</button>
        <span class="sw-popup-kicker">SENTRYLOOT REWARDS</span>
        <h2 id="home-spin-title">Spin <em>&amp; Win</em></h2>
        ${wheel(data.prizes,centerAction)}
        <p class="sw-popup-state" data-sw-state role="status">${h(state)}</p>
        <p class="sw-error" role="alert" hidden></p>
        <div data-sw-result>${result(data.today)}</div>`;
      const dismiss=()=>dismissedFor.add(visitor);
      dialog.addEventListener('cancel',dismiss,{once:true});
      dialog.querySelector('.sw-popup-close').addEventListener('click',()=>{
        dismiss();
        dialog.close();
      });
      bindSpin(dialog,data);
      dialog.showModal();
    }catch{
      // A temporary spin service failure must not block the storefront.
    }
  }
  async function admin(page=1){
    const route=location.href,data=await api('/admin/spin-win?page='+page);if(location.href!==route)return;
    document.title='Spin & Win Admin | SentryLoot';
    const config=data.settings,totals=data.counters;
    app.innerHTML=`<section class="page sw-page sw-admin"><header class="sw-heading"><div><span class="sw-eyebrow">SENTRYLOOT ADMIN</span><h1>Spin & Win</h1><p>${t('Aksiya va katta sovrin g‘oliblari','Кампания и победители крупных призов','Campaign and grand-prize winners')}</p></div><a href="/#admin-rewards">${t('Bonus boshqaruvi','Управление бонусами','Rewards settings')} →</a></header>${mode(data)}<div class="sw-admin-layout"><section class="sw-panel"><h2>${t('Aksiya sozlamalari','Настройки кампании','Campaign settings')}</h2><form class="sw-form"><label class="sw-toggle"><input type="checkbox" name="enabled" ${config.enabled?'checked':''}> ${t('Aksiya faol','Кампания активна','Campaign enabled')}</label><label>${t('Jami vaucher budjeti (RM)','Общий бюджет ваучеров (RM)','Total voucher budget (RM)')}<input name="budget" type="number" min="${totals.spent_minor/100}" max="100000" step="0.01" value="${config.budget_minor/100}" required></label><p>${t('Berilgan vaucherlar','Выдано ваучеров','Vouchers issued')}: <b>${money(totals.spent_minor)}</b></p>${[['iphone','iPhone 18 Pro'],['ps5','PlayStation 5'],['tv','Smart TV']].map(([id,label])=>`<label>${label} · ${t('jami zaxira','общий запас','total stock')}<input type="number" name="${id}" min="${totals.awarded[id]}" max="1000" step="1" value="${config.stock[id]}" required><small>${t('Yutilgan','Выиграно','Awarded')}: ${totals.awarded[id]}</small></label>`).join('')}<p>${t('Faqat mavjud, topshirishga tayyor sovrinlar sonini kiriting. Budjet va zaxira bu rejimdagi barcha vaqtni qamraydi.','Укажите только реальные призы, готовые к вручению. Лимиты накопительные для этого режима.','Enter only real prizes ready to fulfil. Budget and stock are lifetime totals for this mode.')}</p><p class="sw-error" role="alert" hidden></p><button class="button-primary" type="submit">${t('Saqlash','Сохранить','Save')}</button></form></section><section class="sw-panel">${odds(data.prizes)}<p>${t('Katta sovrin yutilsa, faol administratorlar sayt ichida xabar oladi. Jonli yutuq uchun tasdiqlangan admin emailiga ham xabar yuboriladi.','При выигрыше крупного приза активные администраторы получат уведомление на сайте. О реальном выигрыше также придёт письмо на подтверждённую почту.','Active administrators receive a site notification. For a live grand-prize win, they also receive an alert at their verified email address.')}</p></section></div><section class="sw-panel sw-winners"><h2>${t('G‘oliblar','Победители','Winners')} (${data.total})</h2><p>${t('Akkaunt ID orqali xaridorni aniqlang va tasdiqlangan emaili orqali bog‘laning. Ma’lumotlar faqat administratorga ko‘rinadi.','Найдите покупателя по ID аккаунта и свяжитесь по подтверждённой почте. Данные видны только администраторам.','Identify the buyer by account ID and contact their verified email. Details are visible only to administrators.')}</p>${data.winners.length?data.winners.map(w=>`<article class="sw-winner"><div><h3>${h(w.prize_name)}</h3><p>${h(w.user.display_name)} · <a href="mailto:${h(w.user.email)}">${h(w.user.email)}</a></p><small>${t('Akkaunt','Аккаунт','Account')}: ${h(w.uid)}<br>${t('Sovrin raqami','Номер приза','Prize reference')}: ${h(w.id)}<br>${h(date(w.created_at))}</small><details><summary>${t('Holat tarixi','История статусов','Status history')}</summary>${w.status_history.map(s=>`<p>${h(status(s.status))} · ${h(date(s.at))}</p>`).join('')}</details></div><form data-sw-winner="${h(w.id)}"><label for="sw-${h(w.id)}">${t('Topshirish holati','Статус вручения','Fulfilment status')}</label><select id="sw-${h(w.id)}" name="status">${['new','contacted','shipped','delivered'].map(s=>`<option value="${s}" ${w.status===s?'selected':''}>${h(status(s))}</option>`).join('')}</select><p class="sw-error" role="alert" hidden></p><button class="button-secondary" type="submit">${t('Yangilash','Обновить','Update')}</button></form></article>`).join(''):`<p>${t('Hali katta sovrin g‘olibi yo‘q.','Победителей крупных призов пока нет.','No grand-prize winners yet.')}</p>`}<div class="sw-pages"><button data-sw-prev ${page===1?'disabled':''}>←</button><span>${page}</span><button data-sw-next ${page*50>=data.total?'disabled':''}>→</button></div></section></section>`;
    const root=app.querySelector('.sw-admin');
    function bind(form,handler){form.addEventListener('submit',async event=>{event.preventDefault();if(!form.reportValidity())return;const button=event.submitter,error=form.querySelector('.sw-error');button.disabled=true;error.hidden=true;try{await handler(new FormData(form));if(root.isConnected)await admin(page);}catch(e){if(root.isConnected){error.textContent=e.message;error.hidden=false;button.disabled=false;}}});}
    bind(root.querySelector('.sw-form'),async f=>post('/admin/spin-win/settings',{enabled:f.get('enabled')==='on',budget_minor:window.RewardsUI.amountToMinor(f.get('budget'),'MYR'),stock:Object.fromEntries(['iphone','ps5','tv'].map(id=>[id,Number(f.get(id))]))}));
    root.querySelectorAll('[data-sw-winner]').forEach(form=>bind(form,async f=>post('/admin/spin-win/winners/'+encodeURIComponent(form.dataset.swWinner),{status:f.get('status')})));
    root.querySelector('[data-sw-prev]').onclick=()=>admin(page-1);root.querySelector('[data-sw-next]').onclick=()=>admin(page+1);window.SelectMenus?.refresh?.(root);
  }
  return {customer,admin,home,wheel};
})();

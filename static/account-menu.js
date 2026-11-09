/* Shared account identity and menu for Marketplace and Community. */
(()=>{'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function marketAvatarMarkup(name,avatar='',className='market-seller-avatar',owner=''){
 const initials=String(name||'').trim().split(/\s+/u).slice(0,2).map(part=>Array.from(part)[0]||'').join('').toLocaleUpperCase()||'?';
 const photo=typeof avatar==='string'&&/^https:\/\//i.test(avatar)?avatar:'';
 return `<span class="${className} user-avatar" data-avatar-owner="${esc(owner)}" aria-hidden="true"><span>${esc(initials)}</span>${photo?`<img data-seller-avatar src="${esc(photo)}" alt="" width="64" height="64" loading="lazy" decoding="async" referrerpolicy="no-referrer">`:''}</span>`;
}
function menu(me,{t,icon,created}){
 const menuRow=(href,glyph,title,description)=>`<a class="profile-menu-row" href="${href}"><span class="profile-menu-icon" aria-hidden="true">${icon(glyph)}</span><span class="profile-menu-copy"><b>${title}</b><small>${description}</small></span><span class="profile-menu-end" aria-hidden="true">${icon('arrow-up-right')}</span></a>`;
 return `<button class="profile-backdrop" type="button" data-profile-close aria-label="${t('Menyuni yopish','Закрыть меню','Close menu')}"></button><aside class="profile-dropdown" id="profile-dropdown" role="dialog" aria-label="${t('Profil menyusi','Меню профиля','Profile menu')}" tabindex="-1"><div class="profile-shell">
  <header class="profile-hero"><button type="button" class="profile-glass-close" data-profile-close aria-label="${t('Menyuni yopish','Закрыть меню','Close menu')}"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 6 8 8m0-8-8 8"/></svg></button><div class="profile-identity">${marketAvatarMarkup(me.display_name||me.email,me.avatar_url,'profile-avatar',me.id)}<div class="profile-person"><span class="profile-eyebrow">SENTRYLOOT · ${t('HISOB','АККАУНТ','ACCOUNT')}</span><h2>${esc(me.display_name)}</h2><p>${esc(me.email)}</p></div></div><div class="profile-badges"><span class="profile-badge ${me.email_verified?'is-verified':'is-pending'}"><span></span>${me.email_verified?t('Email tasdiqlangan','Email подтверждён','Email verified'):t('Email tasdiqlanmagan','Email не подтверждён','Email not verified')}</span><span class="profile-badge">${me.seller?t('Sotuvchi','Продавец','Seller'):t('Xaridor','Покупатель','Buyer')}</span></div></header>
  <div class="profile-content">
   <div class="profile-account-card"><span class="profile-account-icon" aria-hidden="true">${icon('shield')}</span><div><b>${t('Hisob holati','Статус аккаунта','Account status')}</b><small>${t('A’zo bo‘lgan sana','Дата регистрации','Member since')} · ${esc(created)}</small></div><span class="profile-account-status">${me.email_verified?t('Faol','Активен','Active'):t('Tekshiring','Проверьте','Action needed')}</span></div>
   <div class="profile-points-line"><span>${t('Eski bonus ballar','Прежние бонусные баллы','Legacy bonus points')}</span><b id="profile-bonus-balance" aria-live="polite">${t('Yuklanmoqda…','Загрузка…','Loading…')}</b></div>
   <nav class="profile-menu" aria-label="${t('Hisob sozlamalari','Настройки аккаунта','Account settings')}">
    ${menuRow('/#account','settings',t('Hisob sozlamalari','Настройки аккаунта','Account settings'),t('Profil, xavfsizlik va sozlamalar','Профиль, безопасность и настройки','Profile, security and preferences'))}
    ${menuRow('/#rewards','ticket',t('Bonus va vaucherlar','Бонусы и ваучеры','Rewards & vouchers'),t('Xarid uchun bonus krediti','Бонусы на покупки','Your promotional purchase credit'))}
    ${me.seller?menuRow('/#wallet','wallet',t('Hamyon','Кошелёк','Wallet'),t('Sotuvchi mablag‘lari','Средства продавца','Seller funds'))+menuRow('/#payout-options','arrow-up-right',t('Pul yechish','Вывод средств','Payout options'),t('Mablag‘ yechish sozlamalari','Настройки вывода средств','Payout settings')):''}
    ${me.email_verified?`<button class="profile-menu-row profile-menu-button" type="button" data-action="link-facebook"><span class="profile-menu-icon" aria-hidden="true"><span class="facebook-mark">f</span></span><span class="profile-menu-copy"><b>${t('Facebook’ni ulash','Подключить Facebook','Link Facebook')}</b><small>${t('Hisobingizga xavfsiz ulash','Безопасное подключение аккаунта','Securely connect your account')}</small></span></button>`:''}
   </nav>
   <nav class="profile-menu profile-account-actions" aria-label="${t('Yordam va hisob','Помощь и аккаунт','Help and account')}">
    <button class="profile-menu-row profile-menu-button" type="button" data-open-support-chat><span class="profile-menu-icon" aria-hidden="true">${icon('message')}</span><span class="profile-menu-copy"><b>${t('Yordam chatini ochish','Открыть чат поддержки','Open support chat')}</b><small>${t('Savolingiz bo‘lsa, bizga yozing','Напишите нам, если нужна помощь','Send us a message if you need help')}</small></span></button>
    <button class="profile-menu-row profile-menu-button profile-sign-out" type="button" data-action="logout"><span class="profile-menu-icon" aria-hidden="true">${icon('arrow-up-right')}</span><span class="profile-menu-copy"><b>${t('Hisobdan chiqish','Выйти из аккаунта','Sign out')}</b></span></button>
   </nav>
  </div></div></aside>`;
}

function positionMenu(root){
 if(root.hidden)return;
 const avatar=document.querySelector('#account-button .account-avatar');
 if(!avatar?.getClientRects().length){
  root.style.removeProperty('--profile-menu-top');
  root.style.removeProperty('--profile-menu-right');
  return;
 }
 const rect=avatar.getBoundingClientRect();
 root.style.setProperty('--profile-menu-top',`${rect.bottom+8}px`);
 root.style.setProperty('--profile-menu-right',`${Math.max(0,root.clientWidth-rect.right)}px`);
}

if(window.ResizeObserver){
 const root=document.getElementById('profile-menu-root');
 if(root)new ResizeObserver(()=>{
  if(!root.hidden)requestAnimationFrame(()=>positionMenu(root));
 }).observe(root);
}
window.SentryLootAccount=Object.freeze({avatar:marketAvatarMarkup,menu});
})();

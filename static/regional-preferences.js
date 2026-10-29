/* Global browsing preferences. Settlement always uses the original listing currency. */
(function (root) {
 'use strict';
 const KEY='sentryloot-region-v1', FXKEY='sentryloot-fx-v1';
 const moneyTokens=new Map();
 let state={country:'US',currency:'USD',language:'en',source:'default'},markets=[],options={},fx=null,flight=null,bound=false;
 const read=(store,key)=>{try{return JSON.parse(store.getItem(key)||'null')}catch{return null}};
 const write=(store,key,value)=>{try{store.setItem(key,JSON.stringify(value))}catch{}};
 const valid=(value)=>value&&markets.some(row=>row.country===value.country)&&markets.some(row=>row.currency===value.currency);
 function apply(server,user){
  const saved=read(root.localStorage,KEY);
  const next=user?{...server,...user,source:'profile'}:valid(saved)?{...saved,source:'manual'}:server;
  const preferredLanguage=user?.language||(valid(saved)?saved.language:options.getLanguage?.()||next?.language);
  if(valid(next))state={country:next.country,currency:next.currency,language:languageRows().some(item=>item.code===preferredLanguage)?preferredLanguage:'en',source:next.source};
  sync();return {...state};
 }
 function languageRows(){return root.SENTRYLOOT_LANGUAGE_DATA?.languages||[{code:'en',name:'English'},{code:'uz',name:'O‘zbekcha'},{code:'ru',name:'Русский'}]}
 function translate(text,language){return root.SENTRYLOOT_LANGUAGE_DATA?.messages?.[language]?.[text]||null}
 function money(amount,currency,original){
  const rendered=estimate(amount,currency)||original;
  if(moneyTokens.size>1000)moneyTokens.clear();
  moneyTokens.set(original,{amount,currency,rendered,original});return rendered;
 }
 function refreshMoney(){
  const parent=root.document?.getElementById('app');if(!parent||!moneyTokens.size||!root.document.createTreeWalker)return;
  const tokens=new Map();for(const [original,item] of moneyTokens){tokens.set(original,item);tokens.set(item.rendered,item)}
  const escaped=[...tokens.keys()].sort((a,b)=>b.length-a.length).map(value=>[...value].map(char=>('^$.*+?()[]{}|'+String.fromCharCode(92)).includes(char)?String.fromCharCode(92)+char:char).join(''));
  if(!escaped.length)return;
  const pattern=new RegExp('(?<![0-9])(?:'+escaped.join('|')+')(?![0-9])','gu');
  const walker=root.document.createTreeWalker(parent,4);let node;
  while((node=walker.nextNode())){
   if(node.parentElement?.closest('[data-original-currency],.admin-portal,.product-title,.detail-desc,[data-user-content],.bubble,input,textarea,select,script,style'))continue;
   node.data=node.data.replace(pattern,match=>{const item=tokens.get(match);if(!item)return match;const output=estimate(item.amount,item.currency)||item.original;item.rendered=output;return output});
  }
 }
 function numberLocale(language){return `${language||state.language||'en'}-${state.country}`}
 function estimate(amount,currency){
  if(!fx?.rates||Date.now()/1000-fx.updated_at>172800||currency===state.currency)return null;
  const from=Number(fx.rates[currency]),to=Number(fx.rates[state.currency]);
  if(!Number.isFinite(from)||from<=0||!Number.isFinite(to)||to<=0)return null;
  // Existing marketplace ledger: MYR cents, UZS whole som. Never reinterpret it.
  const major=Number(amount)/(currency==='MYR'?100:1);
  if(!Number.isFinite(major))return null;
  try{return '≈ '+new Intl.NumberFormat(numberLocale(),{style:'currency',currency:state.currency}).format(major/from*to)}catch{return null}
 }
 function refreshPrices(){
  refreshMoney();
  root.document?.querySelectorAll('[data-region-source]').forEach(node=>{node.hidden=!estimate(node.dataset.regionAmount,node.dataset.regionCurrency)});
  root.document?.querySelectorAll('[data-region-price]').forEach(node=>{
   const text=estimate(node.dataset.regionAmount,node.dataset.regionCurrency);
   node.textContent=text||'';node.hidden=!text;
   node.title=options.translate?.('Taxminiy kurs. To‘lov asl valyutada.','Приблизительный курс. Оплата в исходной валюте.','Estimated exchange rate. Payment uses the original currency.')||'';
  });
 }
 async function loadRates(){
  if(flight)return flight;
  const cached=read(root.sessionStorage,FXKEY);
  if(cached?.expires_at*1000>Date.now()&&cached.rates){fx=cached;refreshPrices();return fx}
  flight=(async()=>{try{
   const response=await fetch('/api/exchange-rates',{credentials:'omit',signal:AbortSignal.timeout(5000)});
   if(!response.ok)return null;
   const data=await response.json();
   if(data?.rates&&Object.keys(data.rates).length){fx=data;if(!data.stale)write(root.sessionStorage,FXKEY,data);refreshPrices()}
  }catch{}finally{flight=null}return fx})();
  return flight;
 }
 function sync(){refreshPrices()}
 function captureTopupDraft(){const form=root.document.querySelector('#topup-checkout-form');return form?{url:root.location.pathname+root.location.hash,quantity:root.document.getElementById('tu-quantity')?.value,player:form.querySelector('[name=player_id]')?.value}:null}
 function restoreTopupDraft(draft){if(!draft||draft.url!==root.location.pathname+root.location.hash)return;const quantity=root.document.getElementById('tu-quantity'),player=root.document.querySelector('#topup-checkout-form [name=player_id]');if(player&&draft.player)player.value=draft.player;if(quantity&&draft.quantity){quantity.value=draft.quantity;quantity.dispatchEvent(new Event('input',{bubbles:true}))}}
 function open(){
  if(root.document.querySelector('.region-preferences-dialog'))return;
  root.document.getElementById('language-menu').hidden=true;
  root.document.getElementById('language-toggle').setAttribute('aria-expanded','true');
  const t=options.translate,dialog=root.document.createElement('dialog');dialog.className='region-preferences-dialog';dialog.id='region-preferences-dialog';
  dialog.innerHTML=`<form><div class="region-preferences-heading"><h2 id="region-preferences-title"></h2><button type="button" data-region-close aria-label="Close"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg></button></div><p data-region-description></p><div class="field"><label for="region-country"></label><select id="region-country" name="country" required></select></div><div class="field"><label for="region-currency"></label><select id="region-currency" name="currency" required></select></div><div class="field"><label for="region-language"></label><select id="region-language" name="language"></select></div><small data-region-note></small><p data-region-error role="alert" hidden></p><button class="button-primary" type="submit"></button></form>`;
  dialog.setAttribute('aria-labelledby','region-preferences-title');
  dialog.querySelector('h2').textContent=t('Region sozlamalari','Региональные настройки','Regional preferences');
  dialog.querySelector('[data-region-description]').textContent=t('Mamlakat, ko‘rsatish valyutasi va interfeys tilini tanlang.','Выберите страну, валюту отображения и язык интерфейса.','Choose your country, display currency and interface language.');
  dialog.querySelector('[data-region-note]').textContent=t('Kurs bo‘yicha narxlar taxminiy. Buyurtma asl valyutada to‘lanadi. ','Пересчитанные цены приблизительны. Оплата — в валюте заказа.','Converted prices are estimates. Orders are paid in their original currency.');
  const country=dialog.querySelector('#region-country'),currency=dialog.querySelector('#region-currency'),language=dialog.querySelector('#region-language');
  for(const [name,uz,ru,en] of [['country','Mamlakat yoki hudud','Страна или регион','Country or region'],['currency','Ko‘rsatish valyutasi','Валюта отображения','Display currency'],['language','Interfeys tili','Язык интерфейса','Interface language']])dialog.querySelector(`label[for="region-${name}"]`).textContent=t(uz,ru,en);
  const names=new Intl.DisplayNames([numberLocale(options.getLanguage())],{type:'region'}),englishNames=new Intl.DisplayNames(['en'],{type:'region'}),currencyNames=new Intl.DisplayNames([numberLocale(options.getLanguage())],{type:'currency'});
  for(const row of [...markets].sort((a,b)=>names.of(a.country).localeCompare(names.of(b.country))))country.add(new Option(`${names.of(row.country)}${names.of(row.country)!==englishNames.of(row.country)?' · '+englishNames.of(row.country):''} (${row.country})`,row.country));
  for(const code of [...new Set(markets.map(row=>row.currency))].sort())currency.add(new Option(`${code} · ${currencyNames.of(code)}`,code));
  for(const item of languageRows())language.add(new Option(item.name,item.code));
  country.value=state.country;currency.value=state.currency;language.value=options.getLanguage();
  country.addEventListener('change',()=>{const row=markets.find(row=>row.country===country.value);if(!row)return;currency.value=row.currency;const suggested=row.language||'en';language.value=languageRows().some(item=>item.code===suggested)?suggested:'en';currency.dispatchEvent(new Event('change',{bubbles:true}));language.dispatchEvent(new Event('change',{bubbles:true}))});
  const submit=dialog.querySelector('[type=submit]');submit.textContent=t('Saqlash','Сохранить','Save preferences');
  dialog.querySelector('[data-region-close]').setAttribute('aria-label',t('Yopish','Закрыть','Close'));
  dialog.querySelector('[data-region-close]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();root.document.getElementById('language-toggle')?.setAttribute('aria-expanded','false');root.document.getElementById('language-toggle')?.focus()},{once:true});
  dialog.querySelector('form').onsubmit=async event=>{
   event.preventDefault();submit.disabled=true;const error=dialog.querySelector('[data-region-error]');error.hidden=true;
   const next={country:country.value,currency:currency.value,language:language.value,source:'manual'},draft=captureTopupDraft();
   try{if(options.getUser())await options.saveUser(next);state=next;write(root.localStorage,KEY,next);await options.onChange(next);restoreTopupDraft(draft);sync();dialog.close();loadRates()}
   catch(e){error.textContent=e.message;error.hidden=false}finally{submit.disabled=false}
  };
  root.document.body.append(dialog);root.SelectMenus?.enhanceAll?.(dialog);
  dialog.querySelectorAll('select').forEach(select=>root.SelectMenus?.enhance(select));dialog.showModal();country.nextElementSibling?.querySelector('button')?.focus();
 }
 function init(config){options=config;markets=config.markets;if(!bound&&root.document?.addEventListener){root.document.addEventListener('click',event=>{if(event.target.closest('[data-region-open]'))open()});bound=true}sync();loadRates()}
 const api={init,apply,open,money,translate,numberLocale,estimate,refreshPrices,loadRates,get state(){return {...state}}};
 root.RegionPreferences=api;
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);

/* Global browsing preferences. Settlement always uses the original listing currency. */
(function (root) {
 'use strict';
 const KEY='sentryloot-region-v1', FXKEY='sentryloot-fx-v1';
 let state={country:'US',currency:'USD',language:'en',source:'default'},markets=[],options={},fx=null,flight=null;
 const read=(store,key)=>{try{return JSON.parse(store.getItem(key)||'null')}catch{return null}};
 const write=(store,key,value)=>{try{store.setItem(key,JSON.stringify(value))}catch{}};
 const valid=(value)=>value&&markets.some(row=>row.country===value.country)&&markets.some(row=>row.currency===value.currency);
 function apply(server,user){
  const saved=read(root.localStorage,KEY);
  const next=user?{...server,...user,source:'profile'}:valid(saved)?{...saved,source:'manual'}:server;
  if(valid(next))state={country:next.country,currency:next.currency,language:options.getLanguage?.()||(['en','uz','ru'].includes(next.language)?next.language:'en'),source:next.source};
  sync();return {...state};
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
 function sync(){
  const button=root.document?.getElementById('region-preferences-button');
  if(button){const name=new Intl.DisplayNames([numberLocale()],{type:'region'}).of(state.country);button.textContent=`${options.translate('Region','Регион','Region')} · ${name} · ${state.currency}`}
  refreshPrices();
 }
 function open(){
  if(root.document.querySelector('.region-preferences-dialog'))return;
  root.document.getElementById('language-menu').hidden=true;
  root.document.getElementById('language-toggle').setAttribute('aria-expanded','false');
  const t=options.translate,dialog=root.document.createElement('dialog');dialog.className='region-preferences-dialog';
  dialog.innerHTML=`<form><div class="region-preferences-heading"><h2 id="region-preferences-title"></h2><button type="button" data-region-close aria-label="Close">×</button></div><p data-region-description></p><div class="field"><label for="region-country"></label><select id="region-country" name="country" required></select></div><div class="field"><label for="region-currency"></label><select id="region-currency" name="currency" required></select></div><div class="field"><label for="region-language"></label><select id="region-language" name="language"><option value="en">English</option><option value="uz">O‘zbekcha</option><option value="ru">Русский</option></select></div><small data-region-note></small><p data-region-error role="alert" hidden></p><button class="button-primary" type="submit"></button></form>`;
  dialog.setAttribute('aria-labelledby','region-preferences-title');
  dialog.querySelector('h2').textContent=t('Region sozlamalari','Региональные настройки','Regional preferences');
  dialog.querySelector('[data-region-description]').textContent=t('Mamlakat, ko‘rsatish valyutasi va interfeys tilini tanlang.','Выберите страну, валюту отображения и язык интерфейса.','Choose your country, display currency and interface language.');
  dialog.querySelector('[data-region-note]').textContent=t('Kurs bo‘yicha narxlar taxminiy. Buyurtma asl valyutada to‘lanadi. Hozir interfeys 3 tilda mavjud.','Пересчитанные цены приблизительны. Оплата — в валюте заказа. Интерфейс доступен на 3 языках.','Converted prices are estimates. Orders are paid in their original currency. The interface currently supports 3 languages.');
  const country=dialog.querySelector('#region-country'),currency=dialog.querySelector('#region-currency'),language=dialog.querySelector('#region-language');
  for(const [name,uz,ru,en] of [['country','Mamlakat yoki hudud','Страна или регион','Country or region'],['currency','Ko‘rsatish valyutasi','Валюта отображения','Display currency'],['language','Interfeys tili','Язык интерфейса','Interface language']])dialog.querySelector(`label[for="region-${name}"]`).textContent=t(uz,ru,en);
  const names=new Intl.DisplayNames([numberLocale()],{type:'region'});
  for(const row of [...markets].sort((a,b)=>names.of(a.country).localeCompare(names.of(b.country))))country.add(new Option(names.of(row.country),row.country));
  for(const code of [...new Set(markets.map(row=>row.currency))].sort())currency.add(new Option(code,code));
  country.value=state.country;currency.value=state.currency;language.value=options.getLanguage();
  country.addEventListener('change',()=>{currency.value=markets.find(row=>row.country===country.value).currency;currency.dispatchEvent(new Event('change',{bubbles:true}))});
  const submit=dialog.querySelector('[type=submit]');submit.textContent=t('Saqlash','Сохранить','Save preferences');
  dialog.querySelector('[data-region-close]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{dialog.remove();root.document.getElementById('language-toggle')?.focus()},{once:true});
  dialog.querySelector('form').onsubmit=async event=>{
   event.preventDefault();submit.disabled=true;const error=dialog.querySelector('[data-region-error]');error.hidden=true;
   const next={country:country.value,currency:currency.value,language:language.value,source:'manual'};
   try{if(options.getUser())await options.saveUser(next);state=next;write(root.localStorage,KEY,next);await options.onChange(next);sync();dialog.close();loadRates()}
   catch(e){error.textContent=e.message;error.hidden=false}finally{submit.disabled=false}
  };
  root.document.body.append(dialog);root.SelectMenus?.enhanceAll?.(dialog);
  dialog.querySelectorAll('select').forEach(select=>root.SelectMenus?.enhance(select));dialog.showModal();country.nextElementSibling?.querySelector('button')?.focus();
 }
 function init(config){options=config;markets=config.markets;let button=root.document.getElementById('region-preferences-button');
  if(!button){button=root.document.createElement('button');button.id='region-preferences-button';button.type='button';button.setAttribute('role','menuitem');button.onclick=open;root.document.getElementById('language-menu')?.append(button)}sync();loadRates();
 }
 const api={init,apply,open,numberLocale,estimate,refreshPrices,loadRates,get state(){return {...state}}};
 root.RegionPreferences=api;
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);

const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
function fixture(){const stored=new Map(),storage={getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v)};const root={document:{getElementById:()=>({}),querySelectorAll:()=>[]},localStorage:storage,sessionStorage:storage,SENTRYLOOT_LANGUAGE_DATA:JSON.parse(fs.readFileSync('static/regional-languages.json','utf8')),Intl,Date,module:{exports:{}},fetch:async()=>({ok:true,json:async()=>({rates:{USD:1,UZS:12000,MYR:4,GBP:.75},updated_at:Date.now()/1000,expires_at:Date.now()/1000+3600})}),AbortSignal};vm.createContext(root);vm.runInContext(fs.readFileSync('static/regional-preferences.js','utf8'),root);return {api:root.RegionPreferences,stored,root}}
const markets=[{country:'US',currency:'USD'},{country:'GB',currency:'GBP'},{country:'DE',currency:'EUR'},{country:'MY',currency:'MYR'}];
test('explicit guest preference wins over detection, authenticated profile wins over guest',()=>{const {api,stored}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});stored.set('sentryloot-region-v1',JSON.stringify({country:'GB',currency:'GBP',language:'en'}));assert.equal(api.apply({country:'MY',currency:'MYR'},null).country,'GB');assert.equal(api.apply(null,{country:'DE',currency:'EUR',language:'en'}).country,'DE');assert.equal(api.numberLocale('en'),'en-DE')});
test('corrupted storage falls back to valid detected region',()=>{const {api,stored}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});stored.set('sentryloot-region-v1','bad-json');assert.equal(api.apply({country:'MY',currency:'MYR',language:'en'},null).currency,'MYR')});
test('FX converts legacy UZS whole units and MYR cents without changing source amounts',async()=>{const {api}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});await api.loadRates();assert.equal(api.estimate(12000,'UZS'),'£0.75');assert.equal(api.estimate(400,'MYR'),'£0.75');assert.equal(api.estimate(20,'UNKNOWN'),null);assert.equal(api.estimate(1,'GBP'),null)});

test('core UI has real translations for all newly offered languages',()=>{const {api}=fixture();assert.equal(api.translate('Regional preferences','de'),'Regionale Einstellungen');const data=JSON.parse(fs.readFileSync('static/regional-languages.json','utf8'));assert.equal(data.languages.length,14);for(const item of data.languages.filter(x=>!['en','uz','ru'].includes(x.code))){for(const key of ['Country or region','Display currency','Interface language','Save preferences','Marketplace','Original payment amount'])assert.ok(api.translate(key,item.code),item.code+': '+key)}});
test('regional formatter is shared across catalogue, details and checkout while ledger units stay intact',async()=>{const {api}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});assert.equal(api.money(12000,'UZS','12,000 UZS'),'12,000 UZS');await api.loadRates();assert.equal(api.money(12000,'UZS','12,000 UZS'),'£0.75');assert.equal(api.money(400,'MYR','RM 4.00'),'£0.75');assert.equal(api.money(1,'UNKNOWN','1 UNKNOWN'),'1 UNKNOWN')});
test('Top Up package, quantity total and shared fmt convert; raw settlement stays original',async()=>{
 const {api}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});await api.loadRates();
 const app=fs.readFileSync('static/app.js','utf8'),detail=fs.readFileSync('static/topup-detail.js','utf8');
 const context={Intl,RegionPreferences:api,localeTag:()=> 'en-GB',adminText:(_uz,_ru,en)=>en};vm.createContext(context);
 vm.runInContext(app.match(/function fmt\(n,c='UZS'\)\{[^\n]+/)[0]+detail.slice(detail.indexOf('function topupDetailPrice'),detail.indexOf('function renderTopUpDetail')),context);
 assert.equal(context.fmt(12000,'UZS'),'£0.75');assert.equal(context.fmt(12000,'UZS',true),'12,000 UZS');
 assert.equal(context.fmt(499,'USD'),'£3.74');assert.equal(context.fmt(499,'USD',true),'4.99 USD');
 assert.equal(context.topupDetailPrice({price_minor:12000},3),'£2.25');assert.equal(context.topupDetailPrice({price_minor:0}),'Price not set');
});

test('late FX response updates displayed amounts without changing forms or original payment disclosure',async()=>{
 const {api,root}=fixture(),nodes=[{data:'Total: 12,000 UZS',parentElement:{closest:()=>false}},{data:'112,000 UZS',parentElement:{closest:()=>false}},{data:'12,000 UZS',parentElement:{closest:()=>true}}];
 root.document.createTreeWalker=()=>{let i=0;return {nextNode:()=>nodes[i++]||null}};
 api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});api.money(12000,'UZS','12,000 UZS');await api.loadRates();
 assert.equal(nodes[0].data,'Total: £0.75');assert.equal(nodes[1].data,'112,000 UZS');assert.equal(nodes[2].data,'12,000 UZS');api.apply({country:'MY',currency:'MYR',language:'en'});assert.equal(nodes[0].data,'Total: RM 4.00');
});
test('MYR listing binds main and mobile totals to UZS and GBP, including quantity totals',async()=>{
 const {api,root}=fixture();const nodes=[{dataset:{regionAmount:'30000',regionCurrency:'MYR'},textContent:'RM 300.00'},{dataset:{regionAmount:'60000',regionCurrency:'MYR'},textContent:'RM 600.00'}];
 root.document.querySelectorAll=selector=>selector==='[data-region-money]'?nodes:[];
 api.init({markets:[...markets,{country:'UZ',currency:'UZS'}],translate:(_uz,_ru,en)=>en});api.apply({country:'UZ',currency:'UZS',language:'en'});await api.loadRates();
 assert.match(nodes[0].textContent,/900,000/);assert.match(nodes[0].textContent,/UZS/);assert.match(nodes[1].textContent,/1,800,000/);
 api.apply({country:'GB',currency:'GBP',language:'en'});assert.equal(nodes[0].textContent,'£56.25');assert.equal(nodes[1].textContent,'£112.50');
});
test('incomplete cached FX snapshots are refreshed instead of pinning listing prices to MYR',async()=>{
 const {api,stored}=fixture();stored.set('sentryloot-fx-v2',JSON.stringify({rates:{USD:1},updated_at:Date.now()/1000,expires_at:Date.now()/1000+3600}));api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});await api.loadRates();assert.equal(api.estimate(30000,'MYR'),'£56.25');
});

test('supplier USD cents convert once for region currency and refresh after rates load',async()=>{
 const {api,root}=fixture();
 const source=fs.readFileSync('static/topup.js','utf8');
 const context={RegionPreferences:api,esc:String};vm.createContext(context);
 vm.runInContext(source.slice(source.indexOf('function topupSupplierBasePrice('),source.indexOf('async function renderTopUpSupplierBrand(')),context);
 const pack={selling_price_cents:499,selling_currency:'USD'};
 const nodes=[{dataset:{regionAmount:'499',regionCurrency:'USD',regionOriginal:'$4.99'},textContent:'$4.99'}];
 root.document.querySelectorAll=selector=>selector==='[data-region-money]'?nodes:[];
 api.init({markets:[...markets,{country:'UZ',currency:'UZS'}],translate:(_uz,_ru,en)=>en});api.apply({country:'MY',currency:'MYR',language:'en'});
 assert.equal(context.topupSupplierPrice(pack),'$4.99');
 assert.match(context.topupSupplierPriceAttributes(pack),/data-region-amount="499"/);
 await api.loadRates();
 assert.equal(context.topupSupplierPrice(pack),'RM 19.96');
 assert.equal(nodes[0].textContent,'RM 19.96');
 api.apply({country:'GB',currency:'GBP',language:'en'});
 assert.equal(nodes[0].textContent,'£3.74');
 api.apply({country:'UZ',currency:'UZS',language:'en'});
 assert.match(nodes[0].textContent,/59,880/);
 api.apply({country:'DE',currency:'EUR',language:'en'});
 assert.equal(context.topupSupplierPrice(pack),'$4.99');
 assert.equal(nodes[0].textContent,'$4.99');
 api.apply({country:'US',currency:'USD',language:'en'});
 assert.equal(context.topupSupplierPrice(pack),'$4.99');
 assert.equal(nodes[0].textContent,'$4.99');
 assert.equal(pack.selling_price_cents,499);
 assert.equal(context.topupSupplierPrice({}),'');
});

test('every selectable display currency formats all three stored money units',async()=>{
 const {api,root}=fixture();
 const allMarkets=JSON.parse(fs.readFileSync('static/asia-markets.json','utf8'));
 const currencies=[...new Set(allMarkets.map(row=>row.currency))];
 const rates=Object.fromEntries(currencies.map((currency,index)=>[currency,2+index/10]));
 Object.assign(rates,{USD:1,MYR:4,UZS:12000});
 root.fetch=async()=>({ok:true,json:async()=>({rates,updated_at:Date.now()/1000})});
 api.init({markets:allMarkets,translate:(_uz,_ru,en)=>en});
 await api.loadRates();
 for(const currency of currencies){
   const country=allMarkets.find(row=>row.currency===currency).country;
   api.apply({country,currency,language:'en'});
   const expected=new Intl.NumberFormat(`en-${country}`,{style:'currency',currency}).format(rates[currency]);
   for(const [amount,source] of [[100,'USD'],[400,'MYR'],[12000,'UZS']]){
     assert.equal(api.estimate(amount,source),currency===source?null:expected,`${source} → ${currency}`);
   }
 }
});

test('saving preferences preserves the selected supplier package and player ID after rerender',async()=>{
 const {api,root,stored}=fixture();
 root.location={href:'https://local.test/top-up/pubg-mobile'};
 let form={id:'tus-checkout-form',elements:{player_id:{value:'12345678'},quantity:{value:'2'}}};
 const selection={dataset:{supplierPackage:'4'}};
 let restoredPackage,quantityUpdated=false;
 root.Event=Event;
 root.document.querySelector=selector=>{
   if(selector.includes('#tus-checkout-form'))return form;
   if(selector.includes('aria-pressed'))return selection;
   if(selector==='[data-supplier-package="4"]')return {click(){restoredPackage=4;}};
   return null;
 };
 root.document.getElementById=id=>id===form.id?form:null;
 api.init({markets,getUser:()=>null,onChange:async()=>{
   form={id:'tus-checkout-form',elements:{player_id:{value:''},quantity:{value:'1',dispatchEvent(){quantityUpdated=true;}}}};
 }});
 await api.save({country:'MY',currency:'GBP',language:'fr'});
 assert.equal(restoredPackage,4);
 assert.equal(form.elements.player_id.value,'12345678');
 assert.equal(form.elements.quantity.value,'2');
 assert.equal(quantityUpdated,true);
 assert.equal(api.state.language,'fr');
 assert.equal(JSON.parse(stored.get('sentryloot-region-v1')).currency,'GBP');
});

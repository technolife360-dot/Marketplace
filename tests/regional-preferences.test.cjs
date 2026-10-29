const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');
function fixture(){const stored=new Map(),storage={getItem:k=>stored.get(k)||null,setItem:(k,v)=>stored.set(k,v)};const root={document:{getElementById:()=>({}),querySelectorAll:()=>[]},localStorage:storage,sessionStorage:storage,SENTRYLOOT_LANGUAGE_DATA:JSON.parse(fs.readFileSync('static/regional-languages.json','utf8')),Intl,Date,module:{exports:{}},fetch:async()=>({ok:true,json:async()=>({rates:{USD:1,UZS:12000,MYR:4,GBP:.75},updated_at:Date.now()/1000,expires_at:Date.now()/1000+3600})}),AbortSignal};vm.createContext(root);vm.runInContext(fs.readFileSync('static/regional-preferences.js','utf8'),root);return {api:root.RegionPreferences,stored,root}}
const markets=[{country:'US',currency:'USD'},{country:'GB',currency:'GBP'},{country:'DE',currency:'EUR'},{country:'MY',currency:'MYR'}];
test('explicit guest preference wins over detection, authenticated profile wins over guest',()=>{const {api,stored}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});stored.set('sentryloot-region-v1',JSON.stringify({country:'GB',currency:'GBP',language:'en'}));assert.equal(api.apply({country:'MY',currency:'MYR'},null).country,'GB');assert.equal(api.apply(null,{country:'DE',currency:'EUR',language:'en'}).country,'DE');assert.equal(api.numberLocale('en'),'en-DE')});
test('corrupted storage falls back to valid detected region',()=>{const {api,stored}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});stored.set('sentryloot-region-v1','bad-json');assert.equal(api.apply({country:'MY',currency:'MYR',language:'en'},null).currency,'MYR')});
test('FX converts legacy UZS whole units and MYR cents without changing source amounts',async()=>{const {api}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});await api.loadRates();assert.equal(api.estimate(12000,'UZS'),'≈ £0.75');assert.equal(api.estimate(400,'MYR'),'≈ £0.75');assert.equal(api.estimate(20,'UNKNOWN'),null);assert.equal(api.estimate(1,'GBP'),null)});

test('core UI has real translations for all newly offered languages',()=>{const {api}=fixture();assert.equal(api.translate('Regional preferences','de'),'Regionale Einstellungen');const data=JSON.parse(fs.readFileSync('static/regional-languages.json','utf8'));assert.equal(data.languages.length,14);for(const item of data.languages.filter(x=>!['en','uz','ru'].includes(x.code))){for(const key of ['Country or region','Display currency','Interface language','Save preferences','Marketplace','Original payment amount'])assert.ok(api.translate(key,item.code),item.code+': '+key)}});
test('regional formatter is shared across catalogue, details and checkout while ledger units stay intact',async()=>{const {api}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});assert.equal(api.money(12000,'UZS','12,000 UZS'),'12,000 UZS');await api.loadRates();assert.equal(api.money(12000,'UZS','12,000 UZS'),'≈ £0.75');assert.equal(api.money(400,'MYR','RM 4.00'),'≈ £0.75');assert.equal(api.money(1,'UNKNOWN','1 UNKNOWN'),'1 UNKNOWN')});
test('Top Up package, quantity total and shared fmt convert; raw settlement stays original',async()=>{
 const {api}=fixture();api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});await api.loadRates();
 const app=fs.readFileSync('static/app.js','utf8'),detail=fs.readFileSync('static/topup-detail.js','utf8');
 const context={Intl,RegionPreferences:api,localeTag:()=> 'en-GB',adminText:(_uz,_ru,en)=>en};vm.createContext(context);
 vm.runInContext(app.match(/function fmt\(n,c='UZS'\)\{[^\n]+/)[0]+detail.slice(detail.indexOf('function topupDetailPrice'),detail.indexOf('function renderTopUpDetail')),context);
 assert.equal(context.fmt(12000,'UZS'),'≈ £0.75');assert.equal(context.fmt(12000,'UZS',true),'12,000 UZS');
 assert.equal(context.topupDetailPrice({price_minor:12000},3),'≈ £2.25');assert.equal(context.topupDetailPrice({price_minor:0}),'Price not set');
});

test('late FX response updates displayed amounts without changing forms or original payment disclosure',async()=>{
 const {api,root}=fixture(),nodes=[{data:'Total: 12,000 UZS',parentElement:{closest:()=>false}},{data:'112,000 UZS',parentElement:{closest:()=>false}},{data:'12,000 UZS',parentElement:{closest:()=>true}}];
 root.document.createTreeWalker=()=>{let i=0;return {nextNode:()=>nodes[i++]||null}};
 api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});api.money(12000,'UZS','12,000 UZS');await api.loadRates();
 assert.equal(nodes[0].data,'Total: ≈ £0.75');assert.equal(nodes[1].data,'112,000 UZS');assert.equal(nodes[2].data,'12,000 UZS');api.apply({country:'MY',currency:'MYR',language:'en'});assert.equal(nodes[0].data,'Total: ≈ RM 4.00');
});
test('MYR listing binds main and mobile totals to UZS and GBP, including quantity totals',async()=>{
 const {api,root}=fixture();const nodes=[{dataset:{regionAmount:'30000',regionCurrency:'MYR'},textContent:'RM 300.00'},{dataset:{regionAmount:'60000',regionCurrency:'MYR'},textContent:'RM 600.00'}];
 root.document.querySelectorAll=selector=>selector==='[data-region-money]'?nodes:[];
 api.init({markets:[...markets,{country:'UZ',currency:'UZS'}],translate:(_uz,_ru,en)=>en});api.apply({country:'UZ',currency:'UZS',language:'en'});await api.loadRates();
 assert.match(nodes[0].textContent,/900,000/);assert.match(nodes[0].textContent,/UZS/);assert.match(nodes[1].textContent,/1,800,000/);
 api.apply({country:'GB',currency:'GBP',language:'en'});assert.equal(nodes[0].textContent,'≈ £56.25');assert.equal(nodes[1].textContent,'≈ £112.50');
});
test('incomplete cached FX snapshots are refreshed instead of pinning listing prices to MYR',async()=>{
 const {api,stored}=fixture();stored.set('sentryloot-fx-v2',JSON.stringify({rates:{USD:1},updated_at:Date.now()/1000,expires_at:Date.now()/1000+3600}));api.init({markets,translate:(_uz,_ru,en)=>en});api.apply({country:'GB',currency:'GBP',language:'en'});await api.loadRates();assert.equal(api.estimate(30000,'MYR'),'≈ £56.25');
});

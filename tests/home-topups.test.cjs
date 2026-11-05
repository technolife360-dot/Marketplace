const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/topup.js', 'utf8').split('const TOPUP_CATALOG_IMAGE_FALLBACKS')[0];
function fixture(api) {
  const retry = {};
  const host = {isConnected:true, innerHTML:'', attributes:{}, setAttribute(k,v){this.attributes[k]=v;}, querySelector(){return retry;}};
  const context = {api, adminText:(uz,ru,en)=>en, encodeURIComponent, esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
  vm.createContext(context); vm.runInContext(source,context);
  return {host,retry,load:()=>context.loadHomeTopups(host)};
}
test('home top-up cards use real supplier slugs and escape API labels', async()=>{
  const f=fixture(async route=>{assert.equal(route,'/top-up/home');return [{slug:'h2h-613-genshin-impact-global-7',name:'<img src=x>',subtitle:'Genesis Crystals',image_url:'https://images.gamestorehub.com/a.webp',image_width:640,image_height:853}];});
  await f.load();
  assert.match(f.host.innerHTML,/href="\/top-up\/h2h-613-genshin-impact-global-7"/);
  assert.match(f.host.innerHTML,/&lt;img src=x>/);
  assert.equal(f.host.attributes['aria-busy'],'false');
});
test('failed home top-ups can recover without replacing other home content',async()=>{
  let calls=0;
  const f=fixture(async()=>{if(!calls++)throw Error('offline');return [];});
  await f.load(); assert.match(f.host.innerHTML,/data-home-topups-retry/);
  await f.retry.onclick(); assert.match(f.host.innerHTML,/No top ups available yet/);
  assert.equal(f.host.attributes['aria-busy'],'false');
});
test('a slow response cannot write into a home section after navigation',async()=>{
  let finish; const f=fixture(()=>new Promise(resolve=>{finish=resolve;}));
  const pending=f.load(); f.host.isConnected=false; finish([]); await pending;
  assert.equal(f.host.innerHTML,'');
});

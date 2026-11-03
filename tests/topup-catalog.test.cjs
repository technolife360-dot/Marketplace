const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function fixture() {
  const context = {adminText: (uz, ru, en) => en};
  vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../static/topup.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('function topupApplyFilters('), source.indexOf('function topupCatalogCard(')), context);
  const cards = Array.from({length: 120}, (_, i) => ({
    dataset: {topupCategoryCard: i < 100 ? 'game' : 'gift-card'}, hidden: false,
    querySelector: () => ({textContent: i < 100 ? 'Game ' + i : 'Steam Gift Card ' + i})
  }));
  const elements = Object.fromEntries(['[data-topup-category-empty]', '[data-topup-result-count]', '[data-topup-load-more]'].map(key => [key, {}]));
  const page = {dataset: {}, querySelectorAll: () => cards, querySelector: key => elements[key]};
  return {apply: () => context.topupApplyFilters(page), page, cards, elements};
}

test('All counts every product but initially displays only 48, then shows the next batch', () => {
  const f = fixture(); f.apply();
  assert.equal(f.cards.filter(card => !card.hidden).length, 48);
  assert.equal(f.elements['[data-topup-result-count]'].textContent, '120 products');
  assert.equal(f.elements['[data-topup-load-more]'].hidden, false);
  f.page.dataset.topupLimit = '96'; f.apply();
  assert.equal(f.cards.filter(card => !card.hidden).length, 96);
});

test('category and search include matching cards beyond the first batch', () => {
  const f = fixture();
  f.page.dataset.activeTopupCategory = 'gift-card'; f.page.dataset.topupQuery = 'Steam'; f.apply();
  assert.equal(f.cards.filter(card => !card.hidden).length, 20);
  assert.equal(f.elements['[data-topup-load-more]'].hidden, true);
  f.page.dataset.activeTopupCategory = 'game'; f.apply();
  assert.equal(f.cards.filter(card => !card.hidden).length, 0);
  assert.equal(f.elements['[data-topup-category-empty]'].hidden, false);
  f.page.dataset.activeTopupCategory = 'all'; f.apply();
  assert.equal(f.cards.filter(card => !card.hidden).length, 20);
});

test('supplier product types remain separate while original SKU indexes survive interleaved server rows', () => {
  const context = {}; vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../static/topup.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('), source.indexOf('async function renderTopUpSupplierBrand(')), context);
  const packs = [
    {name:'60 UC', type_name:'Currency', server_name:'Server 1', status:'active'},
    {name:'Weekly Pass', type_name:'Membership', server_name:'Server 1', status:'active'},
    {name:'325 UC', type_name:'Currency', server_name:'Server 2', status:'active'},
    {name:'Special bundle', type_name:'', status:'active'}
  ];
  const groups = JSON.parse(JSON.stringify(context.topupSupplierGroups(packs)));
  assert.deepEqual(groups.map(g => g.name), ['Currency','Membership','Other']);
  assert.deepEqual(groups[0].items.map(item => item.index), [0,2]);
  assert.equal(groups[1].items[0].index, 1);
  assert.equal(groups[0].items[1].pack.server_name, 'Server 2');
  assert.equal(packs.length, 4);
});


test('supplier cards show one available variant per product within each type', () => {
  const context = {}; vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../static/topup.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('), source.indexOf('async function renderTopUpSupplierBrand(')), context);
  const packs = [
    {name:'60 UC',type_name:'Currency',status:'out_of_stock'},
    {name:'60 UC',type_name:'Currency',status:'active',server_name:'Server 2'},
    {name:'60 UC',type_name:'Currency',status:'active',server_name:'Server 3'},
    {name:'325 UC',type_name:'Currency',status:'out_of_stock'},
    {name:'60 UC',type_name:'Bonus',status:'active'},
    {name:' 60   UC ',type_name:'Currency',status:'active'}
  ];
  const groups = JSON.parse(JSON.stringify(context.topupSupplierGroups(packs)));
  assert.deepEqual(groups.map(g=>g.name),['Currency','Bonus']);
  assert.deepEqual(groups[0].items.map(x=>x.index),[1]);
  assert.deepEqual(groups[1].items.map(x=>x.index),[4]);
  assert.equal(packs.length,6);
});


test('supplier quantities sort ascending including thousands separators and bonus totals', () => {
  const context = {}; vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../static/topup.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('), source.indexOf('async function renderTopUpSupplierBrand(')), context);
  const names = ['10.920 UC','660 + 120 UC','60 UC','1,800 UC','720 UC','325 UC','4.000 UC','8100 UC'];
  const packs = names.map(name=>({name,type_name:'UC',status:'active'}));
  const result = JSON.parse(JSON.stringify(context.topupSupplierGroups(packs)))[0].items;
  assert.deepEqual(result.map(x=>x.pack.name),['60 UC','325 UC','720 UC','660 + 120 UC','1,800 UC','4.000 UC','8100 UC','10.920 UC']);
  assert.equal(result[0].index,2);
  assert.deepEqual(packs.map(p=>p.name),names);
});

test('PUBG UC shortlist preserves real SKUs and represents bonuses without changing totals', () => {
  const context = {esc:String}; vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../static/topup.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('), source.indexOf('async function renderTopUpSupplierBrand(')), context);
  const totals = [60,120,325,660,1800,3850,8100,16200,24300,32400,40500];
  const skuFor = n => n===60 ? 'pubgmgl60eu-s2' : n===325 ? 'pubgmgl325u-s7' : n===660 ? 'pubgmgl660u-s7' : n===1800 ? 'pubgmgl1800u-s7' : n===3850 ? 'pubgmgl3850u-s7' : n===8100 ? 'pubgmgl8100uco-s11' : n===16200 ? 'pubgmgl16200uco-s11' : n===24300 ? 'pubgmgl24300uco-s11' : n===32400 ? 'pubgmgl32400uco-s11' : n===40500 ? 'pubgmgl40500uco-s11' : 'sku-'+n;
  const packs = [...totals,385,780].map(n=>({sku:skuFor(n),name:n+' Unknown Cash',type_name:'Unknown Cash',status:'active'}));
  packs.push({sku:'pass',name:'Weekly Pass',type_name:'Membership',status:'active'});
  const result = JSON.parse(JSON.stringify(context.topupSupplierPresentationPackages('pubg-mobile',packs)));
  assert.equal(result.length,12);
  result.slice(0,11).forEach((pack,i)=>{
    assert.equal(pack.sku,skuFor(totals[i]));
    assert.equal(pack.name.replace(/ UC$/, '').split('+').reduce((sum,n)=>sum+Number(n),0),totals[i]);
  });
  const cents = [99,198,499,899,2499,4999,9999,18999,28999,37999,46999];
  result.slice(0,11).forEach((pack,i)=>{
    assert.equal(pack.selling_price_cents,cents[i]);
    assert.equal(pack.selling_currency,'USD');
    assert.equal(context.topupSupplierPrice(pack),'$'+(cents[i]/100).toFixed(2));
  });
  assert.equal(context.topupSupplierPrice(result[11]),'');
  assert.equal(result[4].name,'1500 + 300 UC');
  assert.equal(result[11].sku,'pass');
  assert.equal(packs[0].name,'60 Unknown Cash');
  assert.match(context.topupSupplierPackageLabel(result[2]),/tus-pack-bonus/);
  assert.equal(context.topupSupplierPackageLabel(result[0]),'60<span class="tus-pack-unit" data-currency-unit="UC">UC</span>');
});


test('PUBG uses the specified Server 7 SKU for 300+25 without falling back to another server', () => {
  const context = {}; vm.createContext(context);
  const source = fs.readFileSync(path.join(__dirname, '../static/topup.js'), 'utf8');
  vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('), source.indexOf('async function renderTopUpSupplierBrand(')), context);
  const packs = [
    {sku:'pubgmgl325eu-s2',name:'325 UC',type_name:'UC',status:'active'},
    {sku:'pubgmgl325u-s7',name:'325 UC',type_name:'UC',status:'active'}
  ];
  const result = JSON.parse(JSON.stringify(context.topupSupplierPresentationPackages('pubg-mobile',packs)));
  assert.equal(result.length,1);
  assert.equal(result[0].sku,'pubgmgl325u-s7');
  assert.equal(result[0].name,'300 + 25 UC');
  const unavailable = packs.map(p=>({...p,status:p.sku.endsWith('s7')?'out_of_stock':'active'}));
  assert.equal(context.topupSupplierGroups(context.topupSupplierPresentationPackages('pubg-mobile',unavailable)).length,0);
});


test('PUBG Elite Pass cards use only approved SKU variants and USD prices', () => {
  const context={esc:String};vm.createContext(context);
  const source=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8');
  vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('),source.indexOf('async function renderTopUpSupplierBrand(')),context);
  const packs=[
    {sku:'other-server',name:'Elite Pass LV1-50 UC',type_name:'Battle Pass',status:'active'},
    {sku:'pubgmel5ucbp-s101',name:'Elite Pass LV1-50 UC',type_name:'Battle Pass',status:'active'},
    {sku:'pubgmel1ucbp-s101',name:'Elite Pass LV1-100 UC',type_name:'Battle Pass',status:'active'},
    {sku:'pubgmepl1ucbp-s10',name:'Elite Pass Plus',type_name:'Battle Pass',status:'active'}
  ];
  const result=context.topupSupplierPresentationPackages('pubg-mobile',packs);
  assert.equal(result.length,3);
  assert.deepEqual(Array.from(result,p=>context.topupSupplierPrice(p)),['$5.49','$10.79','$26.99']);
  assert.deepEqual(Array.from(result,p=>p.sku),packs.slice(1).map(p=>p.sku));
});


test('Coins keep per-package R2 artwork, exact SKU and their own approved USD prices',()=>{
 const context={esc:String};vm.createContext(context);
 const source=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8');
 vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('),source.indexOf('async function renderTopUpSupplierBrand(')),context);
 const totals=[60,325,660,1800,3850,8100];
 const packs=totals.map(n=>({sku:`pubgm${n}wc-s101`,name:`${n} WOW Coins`,type_name:'Coins',status:'active'}));
 const result=context.topupSupplierPresentationPackages('pubg-mobile',packs);
 assert.deepEqual(Array.from(result,p=>p.name),['60 Coins','300 + 25 Coins','600 + 60 Coins','1500 + 300 Coins','3000 + 850 Coins','6000 + 2100 Coins']);
 assert.deepEqual(Array.from(result,p=>p.selling_price_cents),[99,499,999,2499,4999,9999]);
 assert.equal(new Set(result.map(p=>p.image_url)).size,6);
 result.forEach((p,i)=>{assert.equal(p.sku,packs[i].sku);assert.match(p.image_url,/^https:\/\/images\.gamestorehub\.com\/site-assets\/topup\/pubg-mobile\/coins-/)});
 assert.match(context.topupSupplierPackageLabel(result[1]),/tus-pack-bonus/);
 assert.match(context.topupSupplierPackageLabel(result[1]),/>Coins<\/span>/);
 assert.equal(context.topupSupplierPrice(result[2]),'$9.99');
});


test('First Purchase Pack has the approved price and R2 banner and included rewards',()=>{
 const context={esc:String};vm.createContext(context);
 const source=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8');
 vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('),source.indexOf('async function renderTopUpSupplierBrand(')),context);
 const result=context.topupSupplierPresentationPackages('pubg-mobile',[
  {sku:'pubgmucfpp-s101',name:'First Purchase Pack UC',type_name:'First Purchase Pack',status:'active'},
  {sku:'other',name:'First Purchase Pack UC',type_name:'First Purchase Pack',status:'active'}
 ]);
 assert.equal(result.length,1);assert.equal(context.topupSupplierPrice(result[0]),'$0.89');
 assert.deepEqual(Array.from(result[0].included_items,p=>p.name),['100 AG','90 UC']);
 for(const url of [result[0].image_url,result[0].detail_banner,...result[0].included_items.map(p=>p.image_url)]) {
  assert.ok(url.startsWith('https://images.gamestorehub.com/site-assets/topup/pubg-mobile/first-purchase-'));
 }
});

test('Mythic Emblem Pack shares the detail layout data with its own rewards and price',()=>{
 const context={esc:String};vm.createContext(context);
 const source=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8');
 vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('),source.indexOf('async function renderTopUpSupplierBrand(')),context);
 const result=context.topupSupplierPresentationPackages('pubg-mobile',[
  {sku:'pubgmucmep-s101',name:'Mythic Emblem Pack UC',type_name:'Mythic Emblem Pack',status:'active'},
  {sku:'other',name:'Mythic Emblem Pack UC',type_name:'Mythic Emblem Pack',status:'active'}
 ]);
 assert.equal(result.length,1);assert.equal(context.topupSupplierPrice(result[0]),'$4.45');
 assert.equal(result[0].display_name,'Mythic Emblem Pack');assert.equal(result[0].max_quantity,1);
 assert.deepEqual(Array.from(result[0].included_items,p=>p.name),['15 Mythic Emblem Fragment','300 UC']);
 assert.ok(result[0].detail_banner.includes('/mythic-emblem-banner-'));
 assert.ok(result[0].description.en.includes('limited to one purchase per UID'));
});


test('PUBG Prime and Prime Plus share one tab without losing either variant',()=>{
 const context={};vm.createContext(context);
 const source=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8');
 vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('),source.indexOf('async function renderTopUpSupplierBrand(')),context);
 const packs=[
  {name:'1 Month',type_name:'Prime',sku:'prime',status:'active'},
  {name:'60 UC',type_name:'UC',sku:'uc',status:'active'},
  {name:'1 Month',type_name:'Prime Plus',sku:'prime-plus',status:'active'}
 ];
 const groups=JSON.parse(JSON.stringify(context.topupSupplierGroups(packs,'pubg-mobile')));
 assert.deepEqual(groups.map(g=>g.name),['Shop','UC']);
 assert.deepEqual(groups[0].items.map(i=>i.index),[0,2]);
 assert.deepEqual(groups[0].items.map(i=>i.pack.sku),['prime','prime-plus']);
 assert.deepEqual(packs.map(p=>p.type_name),['Prime','UC','Prime Plus']);
});

test('all eight Prime memberships have matching R2 detail images and approved prices',()=>{
 const context={esc:String};vm.createContext(context);
 const source=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8');
 vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('),source.indexOf('async function renderTopUpSupplierBrand(')),context);
 const rows=[['pubgmmucp-s101','Prime',1,89],['pubgmmucpb-s101','Prime',3,269],['pubgmmucpc-s101','Prime',6,539],['pubgmmucpa-s101','Prime',12,1079],['pubgmmucpp-s101','Prime Plus',1,899],['pubgmmucppb-s101','Prime Plus',3,2699],['pubgmmucppc-s101','Prime Plus',6,5399],['pubgmmucppa-s101','Prime Plus',12,10799]];
 const packs=rows.map(([sku,type_name,months])=>({sku,type_name,name:`${type_name} (${months} Months) UC`,status:'active'}));
 const result=context.topupSupplierPresentationPackages('pubg-mobile',packs);
 assert.equal(result.length,8);assert.equal(new Set(result.map(p=>p.detail_banner)).size,8);
 result.forEach((pack,i)=>{assert.equal(pack.sku,rows[i][0]);assert.equal(pack.selling_price_cents,rows[i][3]);assert.equal(pack.membership,true);assert.equal(pack.max_quantity,1);assert.ok(pack.detail_banner.includes('/membership-'));assert.ok(!pack.display_name.endsWith(' UC'));});
 const groups=context.topupSupplierGroups(result,'pubg-mobile');
 assert.equal(groups.length,1);assert.equal(groups[0].name,'Shop');
 assert.deepEqual(Array.from(groups[0].items,item=>item.pack.sku),rows.map(row=>row[0]));
});

test('generic game template separates conditional bonus offers and Shop while sorting Diamonds',()=>{
 const context={};vm.createContext(context);
 const source=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8');
 vm.runInContext(source.slice(source.indexOf('function topupSupplierGroups('),source.indexOf('async function renderTopUpSupplierBrand(')),context);
 const packages=[
 {sku:'d257',name:'257 Diamonds',type_name:'Diamonds',status:'active'},
 {sku:'pass',name:'Weekly Diamond Pass x2',type_name:'Diamonds',status:'active'},
 {sku:'d86',name:'86 Diamonds',type_name:'Diamonds',status:'active'},
 {sku:'bonus',name:'50 + 5 Diamonds (First Top-Up Bonus)',type_name:'Diamonds',status:'active'}
 ];
 const result=context.topupSupplierPresentationPackages('mobile-legends',packages);
 const groups=context.topupSupplierGroups(result,'mobile-legends');
 assert.deepEqual(Array.from(groups,g=>g.name),['Diamonds','First Top-Up Bonus','Shop']);
 assert.deepEqual(Array.from(groups[0].items,i=>i.pack.sku),['d86','d257']);
 assert.equal(groups[2].items[0].pack.sku,'pass');
 assert.equal(packages[1].type_name,'Diamonds');
});

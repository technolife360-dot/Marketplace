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
  assert.equal(context.topupSupplierPackageLabel(result[0]),'60<span class="tus-pack-unit">UC</span>');
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

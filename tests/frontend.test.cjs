const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');

function localeContext() {
  const context = {window: {}, locale: 'en'};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/locales.js'), 'utf8'), context);
  const start = source.indexOf('function translateSource(');
  vm.runInContext(source.slice(start, source.indexOf('function adminText(', start)), context);
  return context;
}

test('dynamic account and order copy is translated in English and Russian', () => {
  const context = localeContext();
  for (const [input, english, russian] of [
    ['Buyurtma BG-123', 'Order BG-123', 'Заказ BG-123'],
    ['Salom, Buyer', 'Hello, Buyer', 'Здравствуйте, Buyer'],
    ['4 dona', '4 items', '4 шт.'],
    ['Yetkazish usuli: manual', 'Delivery method: manual', 'Способ доставки: manual'],
    ['To‘lov: sandbox · pending. Sandbox natijasi real pul o‘tkazmasi emas.', 'Payment: sandbox · pending. Sandbox does not transfer real money.', 'Оплата: sandbox · pending. Тестовый режим не переводит реальные деньги.'],
  ]) {
    assert.equal(context.localized(input, 'en'), english);
    assert.equal(context.localized(input, 'ru'), russian);
    assert.equal(context.localized(input, 'uz'), input);
  }
  assert.equal(context.localized('Player-supplied text', 'en'), 'Player-supplied text');
});

test('failed asynchronous page requests render an error instead of leaving the loading state', async () => {
  const start = source.indexOf('async function navigate(');
  const navigateSource = source.slice(start, source.indexOf('\nfunction renderHeroBlank(', start));
  for (const [route, renderer] of [['listing/test', 'renderListing'], ['messages', 'renderMessages'], ['cart', 'renderCart'], ['unknown', 'renderHome']]) {
    const context = {
      location: {hash: '#' + route, pathname: '/', search: ''},
      history: {state: null, replaceState() {}},
      app: {classList: {remove() {}}, innerHTML: ''},
      document: {body: {classList: {remove() {}}}}, window: {},
      currentPageAnchor: () => '', updateRouteMetadata() {}, syncRouteBack() {}, stopHomeCanvas() {},
      pageTitle: text => '<h1>' + text + '</h1>', esc: text => String(text),
      [renderer]: async () => {throw new Error('Test API request failed');},
    };
    vm.createContext(context);
    vm.runInContext(navigateSource, context);
    await assert.doesNotReject(context.navigate(), route);
    assert.match(context.app.innerHTML, /Test API request failed/, route);
    assert.doesNotMatch(context.app.innerHTML, /class="loading"/, route);
  }
});


test('SQLite and PostgreSQL dates keep their timezone and render the same instant', () => {
  const context = {};
  vm.createContext(context);
  const start = source.indexOf('function parseServerDate(');
  vm.runInContext(source.slice(start, source.indexOf('function localeTag(', start)), context);
  for (const input of ['2026-10-19 08:00:00', '2026-10-19T08:00:00Z', '2026-10-19 08:00:00+00', '2026-10-19 08:00:00+00:00', '2026-10-19T16:00:00+08:00']) {
    assert.equal(context.parseServerDate(input).toISOString(), '2026-10-19T08:00:00.000Z', input);
  }
  assert.equal(context.parseServerDate('2026-10-19').toISOString(), '2026-10-19T00:00:00.000Z');
  assert.ok(Number.isNaN(+context.parseServerDate(null)));
});

test('marketplace UX loads before app globals and parses multilingual delivery windows',()=>{
 const context={window:{},encodeURIComponent,console};vm.createContext(context);
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/marketplace-ux.js'),'utf8'),context);
 const ux=context.window.MarketUX;
 for(const [value,minutes]of [['5 minutes',5],['1 hour',60],['24 soat',1440],['1 kun',1440],['Instant',1],['Ask seller',null]])assert.equal(ux.duration(value),minutes);
});


test('account tools initialize before app globals',()=>{
 const context={window:{},encodeURIComponent};vm.createContext(context);
 assert.doesNotThrow(()=>vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/account-operations.js'),'utf8'),context));
 assert.equal(typeof context.window.OperationsUX.account,'function');
});


test('top-up totals reject invalid quantities and never invent an unset price', () => {
  const context={adminText:(_uz,_ru,en)=>en,fmt:(amount,currency)=>amount+' '+currency};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/topup-detail.js'),'utf8'),context);
  for(const invalid of ['',0,-1,1.5,100,'abc',Infinity])assert.equal(context.topupQuantity(invalid),null);
  assert.equal(context.topupQuantity('1'),1);assert.equal(context.topupQuantity('99'),99);
  assert.equal(context.topupDetailPrice({price_minor:125000},3),'375000 UZS');
  assert.equal(context.topupDetailPrice({price_minor:0},3),'Price not set');
});

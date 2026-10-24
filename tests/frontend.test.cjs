const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');

test('admin navigation uses the server role for every administrator email', () => {
  const definition = source.match(/function syncAdminLink\(\)\{[^\n]*/)[0];
  for (const [user, hidden] of [
    [{is_admin:true,email:'admin@gamestore.com'},false],
    [{is_admin:true,email:'sentryloot@gamestorehub.com'},false],
    [{is_admin:false,email:'admin@gamestore.com'},true],
    [null,true],
  ]) {
    const link = {setAttribute(){}};
    const context = {me:user,$:()=>link,adminText:(_uz,_ru,en)=>en};
    vm.createContext(context);
    vm.runInContext(definition+';syncAdminLink()',context);
    assert.equal(link.hidden,hidden);
  }
});

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
      app: {classList: {remove() {}, toggle() {}}, innerHTML: ''}, me: null,
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

test('order guidance shows only the server-owned next step and treats cancellation as terminal',()=>{
 const context={window:{},encodeURIComponent,adminText:(_uz,_ru,en)=>en,esc:value=>String(value??''),me:{id:'buyer'},icon:name=>`<svg data-icon="${name}"></svg>`,$:()=>null};
 let html='';
 const page={querySelector:selector=>selector==='.page-header'?{insertAdjacentHTML:(_where,value)=>{html=value}}:null};
 context.app={querySelector:selector=>selector==='.page'?page:null,querySelectorAll:()=>[]};
 vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/marketplace-ux.js'),'utf8'),context);
 context.window.MarketUX.order({id:'cancelled-order',buyer_id:'buyer',status:'cancelled',items:[]});
 assert.match(html,/Order cancelled/);
 assert.match(html,/There are no further steps/);
 assert.doesNotMatch(html,/Next to act|>—</);
 assert.doesNotMatch(html,/data-order-continue/);
 html='';
 context.window.MarketUX.order({id:'paid-order',buyer_id:'buyer',status:'paid',items:[]});
 assert.match(html,/Payment/);assert.match(html,/Delivery/);assert.match(html,/Nothing you need to do right now/);
 assert.doesNotMatch(html,/data-order-continue|ux-order-checks|Next to act/);
 html='';context.me={id:'seller'};
 context.window.MarketUX.order({id:'paid-order',buyer_id:'buyer',status:'paid',items:[]});
 assert.match(html,/Continue to delivery/);assert.match(html,/data-order-continue/);
});

test('order payment notice explains outcomes without exposing provider status codes',()=>{
 const start=source.indexOf('function orderPaymentNotice(');
 const end=source.indexOf('\nasync function renderOrder(',start);
 const context={adminText:(uz,ru,en)=>en};vm.createContext(context);
 vm.runInContext(source.slice(start,end),context);
 const failed=context.orderPaymentNotice({status:'cancelled',payment:{provider:'stripe_test',status:'failed'}});
 assert.match(failed,/Payment was not completed/);
 assert.match(failed,/Try again from your cart/);
 assert.doesNotMatch(failed,/stripe_test|failed/);
 const pending=context.orderPaymentNotice({status:'pending_payment',payment:{status:'pending'}});
 assert.match(pending,/Next: complete payment/);
});

test('Buy Now sets the selected cart quantity while Add to Cart remains additive',()=>{
 assert.match(source,/if\(a==='buy-now'\)[\s\S]{0,220}mode:'set'/);
 assert.match(source,/if\(a==='add-cart'\)[\s\S]{0,180}quantity:ExperienceUX\.quantity\(\)\}\)\}\);toast/);
});

test('expired Stripe test orders explain the cart recovery path and refresh after checkout conflicts',()=>{
 assert.match(source,/order\.status==='cancelled'&&payment\.status==='expired'[\s\S]{0,700}href="#cart"/);
 assert.match(source,/if\(error\.status===409\)await renderOrder\(id\)/);
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

function sidebarMarkup(user) {
  const context = {me: user, adminText: (_uz, _ru, en) => en, icon: name => `<svg data-icon="${name}"></svg>`};
  vm.createContext(context);
  const start = source.indexOf('function marketSidebarMarkup(');
  vm.runInContext(source.slice(start, source.indexOf('\nfunction marketBannerMarkup(', start)), context);
  return context.marketSidebarMarkup({});
}

test('sidebar shows guests a sign-in route without personal or seller links', () => {
  const html = sidebarMarkup(null);
  assert.match(html, /href="\/#login"/);
  assert.doesNotMatch(html, /href="\/#(?:messages|orders|wallet|payout-options|admin)"/);
  assert.doesNotMatch(html, /market-sidebar-games/);
});

test('buyer sidebar exposes conversations and purchases using the primary navigation component', () => {
  const html = sidebarMarkup({id: 'buyer', seller: null, is_admin: false});
  for (const route of ['messages', 'orders', 'favorites', 'my-reviews', 'requests']) {
    assert.ok(html.includes(`href="/#${route}"`), `Missing ${route} route`);
  }
  assert.match(html, /class="market-sidebar-main market-sidebar-personal"/);
  assert.doesNotMatch(html, /href="\/#(?:seller|wallet|payout-options|admin)"/);
});

test('seller wallet links remain role-specific without seller dashboard or admin sidebar links', () => {
  const seller = sidebarMarkup({seller: {id: 'seller'}, is_admin: false});
  assert.match(seller, /href="\/#wallet"/);
  assert.match(seller, /href="\/#payout-options"/);
  assert.doesNotMatch(seller, /href="\/#(?:seller|admin)"/);
  assert.doesNotMatch(sidebarMarkup({seller: null, is_admin: true}), /href="\/#(?:seller|admin)"/);
});

test('home cards show verified seller reputation and sales without inventing ratings', () => {
  const start = source.indexOf('function marketSellerIdentity(');
  const context = {
    adminText: (_uz, _ru, en) => en, esc: value => String(value ?? ''),
    icon: name => `<svg data-icon="${name}"></svg>`, fmt: value => String(value), categoryLabel: value => value,
  };
  vm.createContext(context);
  vm.runInContext(source.slice(start, source.indexOf('\nfunction setupMarketSidebarToggle(', start)), context);
  const item = {id: 'listing', title: 'Game item', available: 1, stock: 1, reserved: 0, status: 'published', attributes: {}, seller_rating: 4.9, review_count: 200};
  const empty=context.marketCard(item);
  assert.match(empty,/Not rated yet/);
  assert.doesNotMatch(empty,/4\.9/);
  const rated = context.marketCard({...item, product_type:'account', seller_card_review_count:28, seller_card_rating:4.9, seller_sales_count:42, product_review_count:3, product_rating:4.3});
  assert.match(rated, /4\.9\s*<small>\(28\)<\/small>/);
  assert.match(rated,/42 accounts sold/);
  assert.doesNotMatch(rated, /4\.3/);
  assert.match(context.marketCard({...item,product_type:'account',seller_sales_count:1}),/1 account sold/);
  assert.match(context.marketCard({...item,product_type:'item',seller_sales_count:7}),/7 sold/);
});

test('market cards show the actual owner name and photo with a safe initials fallback', () => {
  const start=source.indexOf('function marketSellerIdentity(');
  const context={adminText:(_uz,_ru,en)=>en,esc:value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),icon:name=>`<svg data-icon="${name}"></svg>`,fmt:()=> 'RM 129.90',categoryLabel:value=>value};
  vm.createContext(context);
  vm.runInContext(source.slice(start,source.indexOf('\nasync function showMarketListingDetails(',start)),context);
  const item={id:'offer',seller_id:'actual-owner',title:'Level 65 account',product_type:'account',game_name:'PUBG Mobile',platform:'Android / iOS',attributes:{original_email_included:'yes'},seller_name:'A shop name',seller_display_name:'Shuxrat Aliev',seller_avatar_url:'https://images.example.com/owner.webp',available:1};
  const html=context.marketCard(item);
  assert.match(html,/Shuxrat Aliev/);
  assert.match(html,/src="https:\/\/images.example.com\/owner.webp"/);
  assert.match(html,/href="\/store\/actual-owner"/);
  assert.doesNotMatch(html,/A shop name|SentryLoot|No reviews|Min\./);
  assert.match(html,/Android \/ iOS/);
  assert.match(html,/Email included/);
  const noPhoto=context.marketCard({...item,seller_avatar_url:''});
  assert.doesNotMatch(noPhoto,/data-seller-avatar/);
  assert.match(noPhoto,/>SA<\/span>/);
  const unsafe=context.marketCard({...item,seller_display_name:'<script>alert(1)</script>',seller_avatar_url:'javascript:alert(1)'});
  assert.doesNotMatch(unsafe,/<script|src="javascript:/);
  assert.match(unsafe,/&lt;script&gt;/);
  const sold=context.marketCard({...item,available:0,is_favorite:true});
  assert.equal(sold,'');
  assert.equal(context.marketCard({...item,status:'sold_out',available:1}),'');
});

test('Top Up admin excludes deleted packages until the hidden filter is selected', () => {
  const topupSource=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8');
  const start=topupSource.indexOf('function topupAdminMatchesStatus(');
  const context={};vm.createContext(context);
  vm.runInContext(topupSource.slice(start,topupSource.indexOf('async function renderTopUpAdmin(',start)),context);
  const active={enabled:1,price_minor:100,stock_on_hand:5,stock_reserved:5};
  const hidden={...active,enabled:0};
  assert.equal(context.topupAdminMatchesStatus(active,''),true);
  assert.equal(context.topupAdminMatchesStatus(active,'empty'),true);
  assert.equal(context.topupAdminMatchesStatus(active,'stock'),false);
  assert.equal(context.topupAdminMatchesStatus(active,'hidden'),false);
  for(const filter of ['', 'priced','needs-price','stock','empty'])assert.equal(context.topupAdminMatchesStatus(hidden,filter),false,filter);
  assert.equal(context.topupAdminMatchesStatus(hidden,'hidden'),true);
  assert.equal(context.topupAdminMatchesStatus({...active,price_minor:0},'needs-price'),true);
  assert.equal(context.topupAdminMatchesStatus({...active,stock_reserved:2},'stock'),true);
  assert.equal(context.topupAdminMatchesStatus(null,''),false);
});


test('Top Up create reuses the existing game name and suggests its common unit',()=>{
  const topupSource=fs.readFileSync(path.join(__dirname,'../static/topup.js'),'utf8'),context={};
  const start=topupSource.indexOf('function topupAdminExistingGame(');vm.createContext(context);
  vm.runInContext(topupSource.slice(start,topupSource.indexOf('function topupAdminMatchesStatus(',start)),context);
  const packages=[{game_slug:'pubg-mobile',game_name:'PUBG Mobile',currency:'Pass'},{game_slug:'pubg-mobile',game_name:'PUBG Mobile',currency:'UC'},{game_slug:'pubg-mobile',game_name:'PUBG Mobile',currency:'UC'}];
  const game=context.topupAdminExistingGame(packages,' PUBG-MOBILE ');
  assert.equal(game.game_name,'PUBG Mobile');assert.equal(game.currency,'UC');
  assert.equal(context.topupAdminExistingGame(packages,'new-game'),null);
});

test('Top Up creation errors follow the selected English or Russian language',()=>{
  const context=localeContext();
  for(const message of ['Bu o‘yin manzili uchun nom va valyuta avvaldan belgilangan.','Bu paket manzili allaqachon mavjud. Mavjud paketni tahrirlang yoki yashirilgan paketlar ichidan tiklang.','Valyuta turi harf va raqamlardan iborat bo‘lsin.','O‘yin nomi: uzunligi 2–100 belgi bo‘lishi kerak.']){
    assert.notEqual(context.localized(message,'en'),message);
    assert.notEqual(context.localized(message,'ru'),message);
    assert.equal(context.localized(message,'uz'),message);
  }
});

test('shared form errors translate both the main alert and field notes',()=>{
  const context=localeContext();
  context.document={createElement(){return {setAttribute(){}}}};
  const experience=fs.readFileSync(path.join(__dirname,'../static/experience.js'),'utf8'),start=experience.indexOf('function fail(');
  vm.runInContext(experience.slice(start,experience.indexOf('function bind(',start)),context);
  for(const [language,expected,expectedNote] of [['en','These details conflict with an existing record. Check the values you entered.','Enter 2–100 characters.'],['ru','Данные конфликтуют с существующей записью. Проверьте введённые значения.','Введите 2–100 символов.']]){
    context.locale=language;const alerts=[],notes=[];
    const input={setAttribute(){},after(note){notes.push(note)}};
    const form={isConnected:true,querySelectorAll(){return []},prepend(box){alerts.push(box)},elements:{namedItem(){return input}}};
    context.fail(form,{message:'Ma’lumotlar to‘qnashuvi yuz berdi. Kiritilgan qiymatlarni tekshiring.',fields:{game_name:'2–100 belgi kiriting.'}});
    assert.equal(alerts[0].textContent,expected);assert.equal(notes[0].textContent,expectedNote);
  }
});

test('stored security notifications render in the current language',()=>{
  const context=localeContext();
  for(const [message,en,ru] of [
    ['Ikki bosqichli kirish yoqildi','Two-step verification enabled','Двухэтапная проверка включена'],
    ['Ikki bosqichli kirish o‘chirildi','Two-step verification disabled','Двухэтапная проверка отключена'],
    ['Hisob paroli yangilandi','Account password changed','Пароль аккаунта изменён'],
    ['Hisob email manzili yangilandi','Account email address changed','Email аккаунта изменён'],
    ['Bu amalni siz bajarmagan bo‘lsangiz, yordam xizmatiga murojaat qiling.','If you did not make this change, contact support.','Если это сделали не вы, обратитесь в службу поддержки.'],
  ]){
    assert.equal(context.localized(message,'en'),en);
    assert.equal(context.localized(message,'ru'),ru);
    assert.equal(context.localized(message,'uz'),message);
  }
});

test('home paints banner and search before slow catalogue responses; abandoned requests cannot replace another page', async()=>{
 const start=source.indexOf('async function renderHome(filters={}){');
 const homeSource=source.slice(start,source.indexOf('\nasync function renderComparison',start));
 for(const abandoned of [false,true]){
  const pending=[];const slot={innerHTML:'',setAttribute(){}};
  const root={isConnected:true},category={insertAdjacentHTML(){}};
  const context={app:{innerHTML:'',classList:{add(){}}},document:{body:{classList:{add(){}}}},
   bootstrapSessionReady:null,URLSearchParams,Promise,marketGameLinks:[],
   api:()=>new Promise(resolve=>pending.push(resolve)),adminText:(uz,ru,en)=>en,
   syncRouteBack(){},marketSidebarMarkup:()=>'<aside></aside>',esc:String,icon:()=>'',
   setupMarketBanner(){},marketCard:item=>'<article>'+item.title+'</article>',
   MarketUX:{home(){}},openBrowse(){},
   $:selector=>selector==='#hero-search-form'?{}:selector==='.home-storefront'?root:selector==='[data-home-listings]'?slot:selector==='#home-category'?category:null};
  vm.createContext(context);vm.runInContext(homeSource,context);
  const loading=context.renderHome();
  assert.match(context.app.innerHTML,/home-intro-image/);
  assert.match(context.app.innerHTML,/hero-search-input/);
  assert.match(context.app.innerHTML,/Loading listings/);
  assert.doesNotMatch(context.app.innerHTML,/New listings are on the way/);
  if(abandoned)root.isConnected=false;
  pending[0]({items:[{id:'one',title:'Real listing'}]});pending[1]([]);
  await loading;
  if(abandoned)assert.equal(slot.innerHTML,'');else assert.match(slot.innerHTML,/Real listing/);
 }
});

test('home bootstrap does not wait for account collections before showing the page',async()=>{
 const start=source.indexOf('let bootstrapSessionReady=null;');
 const bootstrapSource=source.slice(start,source.indexOf('\nfunction updateRouteMetadata',start));
 // Extract only bootstrap, without adjacent unrelated route helpers.
 const stop=bootstrapSource.indexOf('\n}',bootstrapSource.indexOf('async function bootstrap'))+2;
 let sessionResolve,painted=false;
 const context={window:{},localStorage:{getItem:()=>null},localeKey:'language',supportedLocales:new Set(['en']),
  location:{pathname:'/',hash:'',search:''},loadAsiaMarkets:async()=>{},
  api:()=>new Promise(resolve=>sessionResolve=resolve),
  navigate:async()=>{painted=true},ExperienceUX:{sync:()=>new Promise(()=>{})},
  document:{documentElement:{}},URLSearchParams,
  syncProfileTrigger(){},syncLanguageMenu(){},syncSellItemButton(){},syncAdminLink(){},
  renderSupportWidget(){},localizeDOM(){},refreshCart(){},refreshNotifications(){}};
 vm.createContext(context);vm.runInContext(bootstrapSource.slice(0,stop),context);
 const loading=context.bootstrap();
 assert.equal(painted,true,'public shell must paint before /me responds');
 await new Promise(setImmediate);
 sessionResolve({user:null,csrf:''});
 await loading;
});

test('admin loads only the requested section and deduplicates pending requests',async()=>{
 const start=source.indexOf('const adminViewRequests=');
 const end=source.indexOf('\nasync function renderAdmin(){',start);
 const panels=new Map(['overview','listings','settings','users','reports'].map(name=>[name,{innerHTML:'',setAttribute(){},querySelector:()=>({})}]));
 const root={isConnected:true,querySelector:selector=>panels.get(selector.match(/"([a-z-]+)"/)[1]),querySelectorAll:()=>[]};
 const requests=[];const pending=[];
 const context={Promise,Map,adminPage:{root,data:{},loaded:new Set(),pending:new Map(),resources:new Map()},
  api:path=>{requests.push(path);return new Promise((resolve,reject)=>pending.push({resolve,reject}))},
  adminLoadingMarkup:()=>'<p>Loading</p>',adminViewMarkup:name=>'<p>'+name+'</p>',
  bindAdminForms(){},localizeDOM(){},window:{},esc:String,adminText:(uz,ru,en)=>en};
 vm.createContext(context);vm.runInContext(source.slice(start,end),context);
 const first=context.loadAdminView('overview'),second=context.loadAdminView('overview');
 assert.strictEqual(first,second);
 assert.deepEqual(requests,['/admin/overview']);
 pending[0].resolve({mode:'production'});await first;
 await context.loadAdminView('settings');
 assert.equal(requests.length,1,'settings must reuse overview within this portal visit');
 const listing=context.loadAdminView('listings');
 assert.deepEqual(requests,['/admin/overview','/admin/listings?summary=1']);
 pending[1].resolve([]);await listing;
 await context.loadAdminView('listings');assert.equal(requests.length,2);
 const reports=context.loadAdminView('reports');pending[2].reject(new Error('Temporary failure'));await reports;
 assert.match(panels.get('reports').innerHTML,/Temporary failure/);
 const retry=context.loadAdminView('reports',true);pending[3].resolve([]);await retry;
 assert.match(panels.get('reports').innerHTML,/reports/);
 const users=context.loadAdminView('users');root.isConnected=false;
 pending[4].resolve([]);pending[5].resolve([]);await users;
 assert.equal(panels.get('users').innerHTML,'<p>Loading</p>','late responses cannot fill a replaced page');
});

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/mobile-site.js', 'utf8');
function harness({url='http://localhost/',user=null,mobile=true,reduced=false,stored=false}={}) {
  const location = new URL(url), nodes=[], timers=[];
  const storedValues=new Map(stored?[['sentryloot-mobile-welcome:v1','1']]:[]);
  const node=()=>({className:'',dataset:{},hidden:false,children:[],classList:{toggle(){},remove(){},add(){}},setAttribute(){},querySelectorAll(){return []},querySelector(){return null},append(...children){this.children.push(...children)},remove(){nodes.splice(nodes.indexOf(this),1)}});
  const body=node();body.append=(element)=>nodes.push(element);
  const document={body,createElement:node,addEventListener(){},querySelector(selector){return nodes.find(n=>selector==='.'+n.className)||null}};
  const app={querySelector(){return null},querySelectorAll(){return []}};
  const context={URLSearchParams,window:{scrollTo(){}},document,app,location,me:user,locale:'en',adminText:(u,r,e)=>e,icon:()=>'<svg/>',esc:String,currentPageAnchor:()=>/^#purchase-reviews-topup-/.test(location.hash)?location.hash.slice(1):'',matchMedia:q=>({matches:q.includes('reduced-motion')?reduced:mobile,addEventListener(){}}),sessionStorage:{getItem:k=>storedValues.get(k),setItem:(k,v)=>storedValues.set(k,v)},setTimeout:(callback,ms)=>{timers.push({callback,ms});return timers.length},clearTimeout(){},requestAnimationFrame:cb=>cb(),MutationObserver:class{observe(){}},setLanguage(){},navigate(){}};
  vm.createContext(context);vm.runInContext(source,context);
  return {site:context.window.MobileSite,location,nodes,timers,context};
}
test('explicit welcome preview can replay the approved animation',()=>{
  const h=harness({url:'http://localhost/?intro=1'});h.site.init();h.site.sessionReady();
  assert.equal(h.nodes.filter(n=>n.className==='mobile-welcome').length,1);
  assert.deepEqual(h.timers.map(t=>t.ms),[2800,3400]);
  h.timers[0].callback();assert.equal(h.location.hash,'');
  h.timers[1].callback();assert.equal(h.location.hash,'#login');
  assert.equal(h.nodes.filter(n=>n.className==='mobile-welcome').length,0);
});
test('the welcome never redirects signed-in accounts',()=>{
  const h=harness({url:'http://localhost/?intro=1',user:{id:'buyer'}});h.site.init();h.site.sessionReady();h.timers.forEach(t=>t.callback());assert.equal(h.location.hash,'');
});
test('payment, verification and order deep links are never intercepted',()=>{
  for(const url of ['http://localhost/?payment=success#order/abc','http://localhost/#verify/abc','http://localhost/#order/abc','http://localhost/top-up/pubg-mobile','http://localhost/#login']){
    const h=harness({url});h.site.init();h.site.sessionReady();assert.equal(h.timers.length,0,url);assert.equal(h.location.href,url);
  }
});
test('welcome does not replay in the same session or on desktop',()=>{
  for(const options of [{stored:true},{mobile:false}]){const h=harness({url:'http://localhost/?intro=1',...options});h.site.init();assert.equal(h.timers.length,0);}
});
test('leaving home while the session resolves preserves the chosen route',()=>{
  const h=harness({url:'http://localhost/?intro=1'});h.site.init();h.location.hash='browse';h.site.sessionReady();h.timers.forEach(t=>t.callback());assert.equal(h.location.hash,'#browse');
});
test('reduced motion uses a short static welcome',()=>{
  const h=harness({url:'http://localhost/?intro=1',reduced:true});h.site.init();assert.deepEqual(h.timers.map(t=>t.ms),[150,150]);
});
test('page anchors keep Top Up selected and purchase routes hide the dock',()=>{
  const h=harness({url:'http://localhost/top-up/pubg-mobile#purchase-reviews-topup-pubg-mobile'});h.site.init();assert.equal(h.context.document.body.dataset.mobileRoute,'top-up/pubg-mobile');
  for(const route of ['cart','order/abc','listing/abc','conversation/abc','admin','top-up-admin'])assert.equal(h.site.navHidden(route),true,route);
  for(const [route,key] of [['home','home'],['browse?sort=price_asc','browse'],['top-up/pubg-mobile','topup'],['messages','messages'],['wallet','account']])assert.equal(h.site.navKey(route),key);
});

test('welcome restores keyboard access after its overlay closes',()=>{
  const h=harness({url:'http://localhost/?intro=1'}),underlay={inert:false};h.context.document.body.children.push(underlay);
  h.site.init();assert.equal(underlay.inert,true);h.timers[1].callback();assert.equal(underlay.inert,false);
});

test('opening the mobile message list does not read an unopened conversation',async()=>{
  const calls=[],form={addEventListener(){}};
  const context={window:{MobileSite:{isMobile:()=>true}},me:{id:'buyer'},URLSearchParams,clearTimeout(){},document:{addEventListener(){},querySelector(){return null},body:{classList:{remove(){}}}},app:{innerHTML:''},$:()=>form,adminText:(u,r,e)=>e,esc:String,icon:()=>'',pageTitle:title=>'<h1>'+title+'</h1>',empty:()=>'',api:async path=>{calls.push(path);if(path.startsWith('/conversations?'))return [{id:'unread-chat',other_name:'Seller',unread:2}];throw new Error('An unopened conversation was fetched')}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('static/experience.js','utf8'),context);
  await context.window.ExperienceUX.messages();
  assert.equal(calls.length,1);assert.match(context.app.innerHTML,/#conversation\/unread-chat/);assert.match(context.app.innerHTML,/>2<\/span>/);
});

test('verification waiting screen masks the local part of the email',()=>{
  const {site}=harness();
  assert.equal(site.maskVerificationEmail('shuxrat@example.com'),'sh***@example.com');
  assert.equal(site.maskVerificationEmail('a@example.com'),'a***@example.com');
  assert.equal(site.maskVerificationEmail(''),'');
});
test('registration retains waiting context across refresh without persisting the verification token',()=>{
  const h=harness();h.site.registrationSubmitted('preview@example.com',{verification_token:'local-test-token'});
  assert.equal(h.location.hash,'#check-email');
  const stored=JSON.parse(h.context.sessionStorage.getItem('sentryloot-pending-verification:v1'));
  assert.deepEqual(stored,{email:'preview@example.com',development:true});
  assert.equal(JSON.stringify(stored).includes('local-test-token'),false);
  assert.equal(h.site.navHidden('check-email'),true);
});
test('opening the waiting screen without a registration does not claim an email was sent',()=>{
  const h=harness({url:'http://localhost/#check-email'});h.site.emailCheck();assert.equal(h.location.hash,'#register');
});

test('the menu requires sign-in and has no second bottom navigation',async()=>{
  const h=harness({url:'http://localhost/#menu'});await h.site.menu();assert.equal(h.location.hash,'#login');assert.equal(h.site.navHidden('menu'),true);
});
test('the menu uses the signed-in profile and keeps admin navigation role-specific',async()=>{
  for(const isAdmin of [false,true]){
    const h=harness({user:{id:'profile-1',display_name:'Actual profile',email:'person@example.com',is_admin:isAdmin}});
    h.context.marketAvatarMarkup=()=>'<span class="user-avatar"></span>';
    await h.site.menu();const html=h.context.app.innerHTML;
    assert.ok(html.includes('Actual profile'));assert.ok(html.includes('pe***@example.com'));
    assert.equal(html.includes('href="/#admin"'),isAdmin);
    for(const route of ['orders','favorites','messages','my-reviews','saved-searches','requests'])assert.ok(html.includes('/#'+route),route);
    assert.ok(html.includes('data-action="logout"'));assert.ok(html.includes('data-action="link-facebook"'));
  }
});

test('mobile search finds catalogue aliases and normalizes spaces and accents without mutating the catalogue',()=>{
  const {site}=harness(),games=[{id:'fc-mobile',name:'EA Sports FC Mobile',aliases:['FIFA Mobile']},{id:'pubg-mobile',name:'PUBG Mobile',aliases:['PUBGM']},{id:'cafe',name:'Café game',aliases:[]}];
  assert.equal(site.matchingSearchGames(games,'FIFA')[0].id,'fc-mobile');
  assert.equal(site.matchingSearchGames(games,'PUBG  mobile')[0].id,'pubg-mobile');
  assert.equal(site.matchingSearchGames(games,'cafe')[0].id,'cafe');
  assert.equal(site.matchingSearchGames(games,'unknown game').length,0);
  assert.equal(site.matchingSearchGames(games)[0].id,'pubg-mobile');
  assert.equal(games[0].id,'fc-mobile');
});

test('mobile notifications preserve real links and read state, and filter without mutating API data',()=>{
  const h=harness(),ctx=h.context;
  ctx.localized=String;ctx.notificationRoute=href=>href.replace(/^\/?#?/,'');ctx.parseServerDate=value=>new Date(value);ctx.localeTag=()=> 'en-US';
  ctx.esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const items=[{id:'unread-real',kind:'delivery',title:'Actual delivery',body:'<script>unsafe</script>',href:'/order/actual-order',created_at:'2026-10-26T00:00:00Z',read_at:null},{id:'read-real',kind:'verification',title:'Actual decision',body:'Reviewed documents',href:'/#seller',created_at:'2026-10-25T00:00:00Z',read_at:'2026-10-26T00:01:00Z'}],before=JSON.stringify(items);
  h.site.notifications(items);
  assert.match(ctx.app.innerHTML,/data-route="order\/actual-order"/);
  assert.match(ctx.app.innerHTML,/data-id="unread-real"/);
  assert.match(ctx.app.innerHTML,/&lt;script&gt;unsafe&lt;\/script&gt;/);
  assert.equal((ctx.app.innerHTML.match(/class="mobile-notification-dot"/g)||[]).length,1);
  h.site.notifications(items,'unread');
  assert.match(ctx.app.innerHTML,/Actual delivery/);assert.doesNotMatch(ctx.app.innerHTML,/Actual decision/);
  assert.match(ctx.app.innerHTML,/id="notification-tab-unread" role="tab" aria-selected="true"/);
  assert.equal(JSON.stringify(items),before);
  h.site.notifications(items.filter(item=>item.read_at),'unread');assert.match(ctx.app.innerHTML,/No unread notifications/);
  assert.equal(h.site.navHidden('notifications'),true);
});

test('mobile notification icons and ages follow real notification metadata',()=>{
  const h=harness();h.context.parseServerDate=value=>new Date(value);h.context.localeTag=()=> 'en-US';
  for(const [kind,glyph] of [['verification','shield'],['listing','box'],['delivery','truck'],['wallet','wallet'],['message','chat'],['review','star'],['unknown','bell']])assert.equal(h.site.notificationGlyph({kind}),glyph);
  assert.equal(h.site.notificationAge('2026-10-26T00:00:00Z',Date.parse('2026-10-26T02:00:00Z')),'2h ago');
  assert.equal(h.site.notificationAge('invalid date'),'');
});

test('purchase cards filter the buyer orders by real status and retain item snapshots and totals',()=>{
  const h=harness({url:'http://localhost/?intro=1',user:{id:'buyer'}}),ctx=h.context;
  ctx.parseServerDate=value=>new Date(value);ctx.localeTag=()=> 'en-US';ctx.fmt=(n,c)=>c+' '+(n/100).toFixed(2);
  ctx.marketGameLinks=[['pubg-mobile','PUBG Mobile','https://images.gamestorehub.com/site-assets/market-game-pubg-mobile.png']];
  ctx.window.OrderFlow={statusLabel:status=>({paid:'Payment confirmed',completed:'Completed',refunded:'Refunded'}[status]||status)};
  ctx.esc=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const item={title:'Actual purchased item',quantity:2,snapshot:{game_id:'pubg-mobile',product_type:'item',image_url:'https://example.com/item.png'}};
  const data=[{id:'actual-active',reference:'BG-ACTIVE',buyer_id:'buyer',status:'paid',currency:'MYR',total_minor:27279,created_at:'2026-10-26T00:00:00Z',items:[item]}, {id:'actual-completed',reference:'BG-COMPLETE',buyer_id:'buyer',status:'completed',currency:'MYR',total_minor:13639,created_at:'2026-10-25T00:00:00Z',items:[item]}, {id:'actual-refund',reference:'BG-REFUND',buyer_id:'buyer',status:'refunded',currency:'MYR',total_minor:13639,created_at:'2026-10-24T00:00:00Z',items:[item]}, {id:'seller-order',reference:'SOLD-ORDER',buyer_id:null,status:'paid',currency:'MYR',total_minor:1,created_at:'2026-10-26T00:00:00Z',items:[item]}];
  const before=JSON.stringify(data);
  h.site.orders(data,[{id:'pubg-mobile',name:'PUBG Mobile'}]);
  assert.match(ctx.app.innerHTML,/href="\/#order\/actual-active"/);
  assert.match(ctx.app.innerHTML,/MYR 272.79/);assert.match(ctx.app.innerHTML,/PUBG Mobile · Item × 2/);
  assert.match(ctx.app.innerHTML,/market-game-pubg-mobile.png/);
  assert.doesNotMatch(ctx.app.innerHTML,/BG-COMPLETE|BG-REFUND|SOLD-ORDER/);
  h.site.orders(data,[],'completed');assert.match(ctx.app.innerHTML,/BG-COMPLETE/);assert.doesNotMatch(ctx.app.innerHTML,/BG-ACTIVE|BG-REFUND/);
  h.site.orders(data,[],'cancelled');assert.match(ctx.app.innerHTML,/BG-REFUND/);assert.doesNotMatch(ctx.app.innerHTML,/BG-ACTIVE|BG-COMPLETE/);
  assert.equal(JSON.stringify(data),before);
  assert.equal(h.site.purchaseGroup({status:'refund_pending'}),'active');
  assert.equal(h.site.purchaseGroup({status:'cancelled'}),'cancelled');
  assert.equal(h.site.navHidden('orders'),true);
});

test('the header menu replaces the bottom dock on every mobile route',()=>{
  const h=harness(),classes=new Map();let removed=false;
  h.context.document.body.classList.toggle=(name,value)=>classes.set(name,value);
  h.nodes.push({className:'ux-mobile-nav',remove(){removed=true;h.nodes.splice(h.nodes.indexOf(this),1)}});
  for(const route of ['home','browse','account','messages','top-up','orders','cart']){
    h.site.syncNavigation(route);
    assert.equal(h.site.navHidden(route),true,route);
    assert.equal(classes.get('mobile-has-dock'),false,route);
  }
  assert.equal(removed,true);assert.equal(h.nodes.some(node=>node.className==='ux-mobile-nav'),false);
});

test('normal mobile and desktop visits have no welcome delay or forced login',()=>{
 for(const mobile of [true,false])for(const user of [null,{id:'buyer'}]){const h=harness({mobile,user});h.site.init();h.site.sessionReady();assert.equal(h.timers.length,0);assert.equal(h.nodes.some(n=>n.className==='mobile-welcome'),false);assert.equal(h.location.hash,'');}
});

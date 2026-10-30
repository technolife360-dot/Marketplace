const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function rewards(overrides={}){
 const context={window:{},adminText:(_u,_r,en)=>en,esc:v=>String(v??'').replaceAll('<','&lt;').replaceAll('"','&quot;'),fmt:(n,c,native)=>`${c} ${c==='MYR'?n/100:n}${native?' native':''}`,icon:()=>'<svg></svg>',Intl,Date,...overrides};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/rewards.js','utf8'),context);return context.window.RewardsUI;
}
function root(){const elements=new Map();const get=selector=>{if(!elements.has(selector))elements.set(selector,{value:'',checked:false,textContent:'',innerHTML:'',disabled:false,hidden:false,events:{},addEventListener(event,callback){this.events[event]=callback}});return elements.get(selector)};return {isConnected:true,innerHTML:'',querySelector:get,get};}
const quote=(id='one')=>({id,expires_at:new Date(Date.now()+60000).toISOString(),currency:'MYR',subtotal_minor:1000,fee_minor:100,gross_total_minor:1100,discount_minor:100,bonus_minor:100,total_minor:900,earn_micro:10000,test_only:true});
test('campaign monetary input converts exact currency minor units without rounding float cents',()=>{
 const ui=rewards();assert.equal(ui.amountToMinor('0.29','USD'),29);assert.equal(ui.amountToMinor('19.99','MYR'),1999);assert.equal(ui.amountToMinor('12500','UZS'),12500);assert.equal(ui.percentToBps('0.50'),50);assert.equal(ui.percentToBps('20'),2000);
 for(const input of ['0.001','1e3','-1','Infinity',''])assert.throws(()=>ui.amountToMinor(input,'USD'));
 assert.throws(()=>ui.amountToMinor('1.50','UZS'));assert.throws(()=>ui.amountToMinor('999999999999999999','USD'));
});
test('wallet uses microUSD and server rate instead of treating credits as seller money',()=>{
 const ui=rewards();assert.match(ui.micro(1000000,{display_currency:'MYR',rates:{MYR:4.2}}),/4\.20/);assert.match(ui.micro(1000000,{display_currency:'UZS',rates:{UZS:12500}}),/12,500/);assert.match(ui.micro(1000000,{display_currency:'MYR',rates:{}}),/\$1\.00/);
});
test('wallet displays distinct spendable amounts for scoped gifts',async()=>{
 const el=root(),ui=rewards({me:{id:'buyer'},location:{href:'http://local/#rewards'},app:el,api:async()=>({settings:{credit_expiry_days:180},display_currency:'MYR',rates:{MYR:4},available_micro:2000000,pending_micro:0,debt_micro:0,usable_for:{account:2000000,topup:0},test_only:true,history:[]})});await ui.customer();assert.match(el.innerHTML,/rw-scope-balances/);assert.match(el.innerHTML,/Accounts <b>MYR.8\.00/);assert.match(el.innerHTML,/Top Up <b>MYR.0\.00/);assert.match(el.innerHTML,/cannot be withdrawn or transferred/);
});
test('quote totals use regional display formatting and separate platform coupon/rewards',()=>{
 const html=rewards().quoteTotals(quote());assert.match(html,/Platform coupon/);assert.match(html,/Rewards used/);assert.match(html,/MYR 9/);assert.doesNotMatch(html,/native/);assert.doesNotMatch(html,/MYR 11/);
});
test('quote display respects selected currency without changing native quote amounts',async()=>{
 const calls=[],ui=rewards({fmt:(amount,currency,forceNative)=>{calls.push({amount,currency,forceNative});return '€'+(amount/100).toFixed(2)},api:async()=>({...quote(),display_currency:'MYR',rates:{MYR:4}})}),el=root(),controller=ui.mountQuote(el,{context:()=>({kind:'account'})});await controller.update();assert.match(el.get('[data-rw-result]').innerHTML,/€9\.00/);assert.match(el.get('[data-rw-result]').innerHTML,/MYR.0\.04/);assert.equal(controller.checkout().total_minor,900);assert.equal(controller.checkout().currency,'MYR');assert.ok(calls.every(call=>call.forceNative===undefined));
});
test('quote binds only actual package context and handles expired or changed benefits explicitly',async()=>{
 const requests=[],ui=rewards({api:async(path,options)=>{requests.push([path,JSON.parse(options.body)]);return quote()}}),el=root();let current={kind:'topup',package_id:'pack-a',quantity:2};const controller=ui.mountQuote(el,{context:()=>current});
 assert.equal(controller.checkout(),null);el.get('[name=platform_coupon]').value='WELCOME';el.get('[name=use_bonus]').checked=true;await controller.update();
 assert.equal(requests[0][0],'/rewards/quote');assert.deepEqual(requests[0][1],{kind:'topup',package_id:'pack-a',quantity:2,coupon_code:'WELCOME',use_bonus:true});assert.equal(controller.checkout().total_minor,900);
 current={...current,quantity:3};assert.throws(()=>controller.checkout(),/Update your rewards quote/);controller.invalidate();assert.throws(()=>controller.checkout());
 el.get('[data-rw-clear]').events.click();assert.equal(controller.checkout(),null);assert.equal(el.get('[name=platform_coupon]').value,'');assert.equal(el.get('[name=use_bonus]').checked,false);
});
test('automatic quotes make ordinary eligible purchases earn and block payment while pending',async()=>{
 let resolveQuote,calls=0;const ui=rewards({api:()=>{calls++;return new Promise(resolve=>{resolveQuote=resolve})}}),el=root(),controller=ui.mountQuote(el,{context:()=>({kind:'account'}),auto:true});assert.throws(()=>controller.checkout(),/Update your rewards quote/);await Promise.resolve();assert.equal(calls,1);assert.throws(()=>controller.checkout());resolveQuote(quote());await new Promise(setImmediate);assert.equal(controller.checkout().earn_micro,10000);
});
test('Unix-second quote expiry stays valid and account summary can omit duplicate totals',async()=>{
 const ui=rewards({api:async()=>({...quote(),expires_at:Math.floor(Date.now()/1000)+300})}),el=root(),controller=ui.mountQuote(el,{context:()=>({kind:'account'}),showTotals:false});await controller.update();assert.equal(controller.checkout().id,'one');assert.doesNotMatch(el.get('[data-rw-result]').innerHTML,/rw-quote-totals/);assert.match(el.get('[data-rw-result]').innerHTML,/Test credits/);
});
test('out-of-order quote responses never replace the newest quote',async()=>{
 const resolvers=[],ui=rewards({api:()=>new Promise(resolve=>resolvers.push(resolve))}),el=root(),controller=ui.mountQuote(el,{context:()=>({kind:'account'})});
 const old=controller.update(),latest=controller.update();resolvers[1](quote('latest'));await latest;resolvers[0](quote('old'));await old;assert.equal(controller.checkout().id,'latest');
});
test('input edits, expired quote and quote failures block payment until cleared or updated',async()=>{
 let response=quote(),ui=rewards({api:async()=>response}),el=root(),controller=ui.mountQuote(el,{context:()=>({kind:'account'})});
 await controller.update();el.get('[name=platform_coupon]').events.input();assert.throws(()=>controller.checkout());response={...quote(),expires_at:new Date(Date.now()-1000).toISOString()};await controller.update();assert.throws(()=>controller.checkout());
 ui=rewards({api:async()=>{throw new Error('FX unavailable')}});el=root();controller=ui.mountQuote(el,{context:()=>({kind:'account'})});await controller.update();assert.equal(el.get('[data-rw-error]').textContent,'FX unavailable');assert.throws(()=>controller.checkout());el.get('[data-rw-clear]').events.click();assert.equal(controller.checkout(),null);
});
test('seller coupons cannot silently stack with platform benefits',async()=>{
 let calls=0;const ui=rewards({api:async()=>{calls++;return quote()}}),el=root(),controller=ui.mountQuote(el,{context:()=>({kind:'account'}),blocked:()=>true});await controller.update();assert.equal(calls,0);assert.match(el.get('[data-rw-error]').textContent,/Remove the seller coupon/);assert.throws(()=>controller.checkout());
});
test('account and Top Up payment requests carry quote ID and server net total; API routes are registered',()=>{
 const cart=fs.readFileSync('static/order-process.js','utf8'),topup=fs.readFileSync('static/topup-detail.js','utf8'),app=fs.readFileSync('static/app.js','utf8'),index=fs.readFileSync('static/index.html','utf8');assert.match(cart,/rewards_quote_id:promotion\.id/);assert.match(cart,/expected_total_minor:promotion\?promotion\.total_minor:c\.total_minor/);assert.match(cart,/rewardsEligible=c\.items\.every\(i=>i\.product_type==='account'\)/);assert.match(topup,/auto:true,context:/);assert.match(topup,/fmt\(quote\.total_minor,quote\.currency\)/);assert.doesNotMatch(topup,/fmt\(quote\.total_minor,quote\.currency,true\)/);assert.match(cart,/rewards\?\.checkout\(\)/);assert.match(topup,/rewards_quote_id:promotion\.id,expected_total_minor:promotion\.total_minor/);assert.match(topup,/function updateTotal\(\)\{rewards\?\.invalidate\(\)/);assert.match(app,/route==='rewards'/);assert.match(app,/route==='admin-rewards'/);assert.match(index,/rewards\.js\?v=/);assert.match(index,/rewards\.css\?v=/);
});

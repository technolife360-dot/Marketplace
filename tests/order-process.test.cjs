const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function flow(overrides={}){
 const context={window:{},document:{addEventListener(){}},adminText:(_u,_r,en)=>en,esc:v=>String(v??'').replaceAll('<','&lt;').replaceAll('"','&quot;'),fmt:(n,c)=>`${c} ${n/100}`,icon:n=>`<svg data-icon="${n}"></svg>`,...overrides};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/order-process.js','utf8'),context);return context.window.OrderFlow;
}
test('buyer/seller stages derive from server state, including terminal exceptions',()=>{
 const f=flow();
 for(const [state,buyer,seller] of [['pending_payment',1,0],['paid',2,0],['awaiting_delivery',2,1],['delivered',2,2],['under_review',2,2],['completed',3,3],['disputed',-1,-1],['refund_pending',-1,-1],['refunded',-1,-1],['cancelled',-1,-1]]){
  assert.equal(f.phase({status:state},true),buyer);assert.equal(f.phase({status:state},false),seller);
 }
});
test('checkout summary displays the actual server fee and total',()=>{
 const html=flow().totals({subtotal_minor:12990,commission_minor:649,total_minor:13639,currency:'MYR'});
 assert.match(html,/MYR 129.9/);assert.match(html,/MYR 6.49/);assert.match(html,/MYR 136.39/);
});
test('unpaid orders cannot expose delivery or completion controls',()=>{
 const html=flow().stageMarkup({status:'pending_payment',payment:{provider:'stripe_test'},total_minor:12990,currency:'MYR'}, {is_paused:false},true);
 assert.match(html,/data-of-pay/);assert.doesNotMatch(html,/data-of-complete|data-of-seller-delivery/);
});
test('cancelled, disputed and refund orders expose no advancing action',()=>{
 for(const status of ['cancelled','disputed','refund_pending','refunded']){
  const html=flow().stageMarkup({status}, {is_paused:false},true);
  assert.doesNotMatch(html,/data-of-complete|data-of-pay\b|data-of-prepare/);
 }
});
test('an older request cannot replace the page after the buyer navigates away',async()=>{
 for(const method of ['cart','wallet']){
  let resolve;const location={href:'http://localhost/#'+method},app={innerHTML:'New page'};
  const f=flow({location,app,me:{id:'buyer'},api:()=>new Promise(r=>resolve=r)});
  const request=f[method]();location.href='http://localhost/#home';resolve({items:[],balances:[]});await request;
  assert.equal(app.innerHTML,'New page');
 }
});
test('checkout retries preserve compatibility warnings and replace only action errors',async()=>{
 const source=fs.readFileSync('static/order-process.js','utf8');
 const definition=source.slice(source.indexOf('  async function action('),source.indexOf('  function bind('));
 const warning={className:'ex-compat-warning of-error',hidden:true},children=[warning];
 const root={querySelector(selector){return children.find(node=>node.className.split(' ').includes(selector.slice(1)))||null},append(node){children.push(node)}};
 const document={createElement(){return {setAttribute(){},remove(){children.splice(children.indexOf(this),1)}}}};
 const action=vm.runInNewContext('('+definition+')',{document,app:root});
 const button={disabled:false,isConnected:true,closest:()=>root};
 for(let attempt=0;attempt<2;attempt++){
  await action(button,async()=>{
   const retained=root.querySelector('.ex-compat-warning');
   retained.hidden=false;
   throw Error('Check the platform and region compatibility.');
  });
  assert.equal(children.includes(warning),true);
  assert.equal(children.filter(node=>node.className.includes('of-action-error')).length,1);
  assert.equal(children.at(-1).textContent,'Check the platform and region compatibility.');
  assert.equal(button.disabled,false);
 }
 let continued=false;await action(button,async()=>{root.querySelector('.ex-compat-warning').hidden=true;continued=true});
 assert.equal(continued,true);assert.deepEqual(children,[warning]);
});
test('review requires an explicit 1–5 rating and a nonblank review before saving',()=>{
 const source=fs.readFileSync('static/order-process.js','utf8');
 const definition=source.slice(source.indexOf('  function reviewReady('),source.indexOf('  function requireReview('));
 const valid=vm.runInNewContext('('+definition+')');
 const form=(rating,body)=>({elements:{rating:{value:rating},body:{value:body}}});
 for(const rating of ['',0,6,2.5,'not-a-rating'])assert.equal(valid(form(rating,'A useful review.')),false);
 for(const body of ['', '     ', ' bad '])assert.equal(valid(form('5',body)),false);
 for(const rating of [1,2,3,4,5])assert.equal(valid(form(String(rating),'An honest review.')),true);
});
test('required review survives navigation attempts without erasing the typed draft',async()=>{
 const location={href:'http://localhost/#home',pathname:'/',hash:'#home'};
 let calls=0,focused=false;
 const form={draft:'My unsaved review',scrollIntoView(){},querySelector:()=>({focus(){focused=true}})};
 const app={innerHTML:'Draft is still rendered',querySelector:selector=>selector==='#of-test-review'?form:{dataset:{ofOrder:'pending-review'}}};
 const history={state:null,replaceState(_s,_title,path){location.hash=path.slice(1);location.href='http://localhost'+path}};
 const f=flow({location,app,history,me:{id:'buyer'},toast(){},api:async path=>{assert.equal(path,'/orders/review-required');calls++;return {order_id:'pending-review'}}});
 assert.equal(await f.guardNavigation(),true);
 assert.equal(location.hash,'#order/pending-review');assert.equal(f.reviewRequired(),true);
 assert.equal(app.innerHTML,'Draft is still rendered');assert.equal(form.draft,'My unsaved review');assert.equal(focused,true);
 location.hash='#orders';assert.equal(await f.guardNavigation(),true);assert.equal(calls,1);
 location.hash='#order/pending-review';assert.equal(await f.guardNavigation(),false);
});
test('users without a pending review can navigate normally',async()=>{
 const location={href:'http://localhost/#home',pathname:'/',hash:'#home'};
 const f=flow({location,me:{id:'buyer'},api:async()=>({order_id:null})});
 assert.equal(await f.guardNavigation(),false);assert.equal(f.reviewRequired(),false);
 const guest=flow({location,me:null,api:()=>{throw Error('Guest must not query private orders')}});
 assert.equal(await guest.guardNavigation(),false);
});

test('buyer payment and refund amounts never show the seller net earnings',()=>{
 const order={status:'delivered',currency:'MYR',total_minor:13639,payment:{status:'succeeded',amount_minor:13639},funds:{state:'pending',seller_net_minor:12341}};
 let html=flow().funds(order,true);assert.match(html,/Payment received/);assert.match(html,/MYR 136.39/);assert.doesNotMatch(html,/MYR 123.41|Pending order earnings/);
 html=flow().funds({...order,status:'refunded',payment:{...order.payment,status:'refunded'},funds:{...order.funds,state:'refunded'}},true);
 assert.match(html,/Payment refunded/);assert.match(html,/MYR 136.39/);assert.doesNotMatch(html,/MYR 123.41|Unavailable while delivery/);
});

test('released order earnings are historical amounts rather than the current wallet balance',()=>{
 const html=flow().funds({status:'completed',currency:'MYR',payment:{status:'succeeded',amount_minor:13639},funds:{state:'available',seller_net_minor:12341}},false);
 assert.match(html,/Order earnings released/);assert.match(html,/MYR 123.41/);assert.match(html,/current balance after payouts and adjustments/);assert.doesNotMatch(html,/>Available balance</);
 const refunded=flow().funds({status:'refunded',currency:'MYR',payment:{status:'refunded'},funds:{state:'refunded',seller_net_minor:12341}},false);
 assert.match(refunded,/Earnings reversed/);assert.match(refunded,/no longer contributes/);
});

test('cart quantity controls respect stock and minimum quantities',()=>{
 const f=flow();
 const single=f.cartQuantity({id:'one',quantity:1,min_quantity:1,available:1});
 assert.match(single,/data-delta="-1"[^>]+disabled/);assert.match(single,/data-delta="1"[^>]+disabled/);
 const pack=f.cartQuantity({id:'pack',quantity:5,min_quantity:5,available:10});
 assert.match(pack,/data-delta="-1"[^>]+disabled/);assert.doesNotMatch(pack,/data-delta="1"[^>]+disabled/);
 const middle=f.cartQuantity({id:'middle',quantity:6,min_quantity:5,available:10});
 assert.doesNotMatch(middle,/disabled/);assert.match(middle,/>6<\/output>/);
});

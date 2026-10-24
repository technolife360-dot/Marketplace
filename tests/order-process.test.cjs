const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function flow(overrides={}){
 const context={window:{},adminText:(_u,_r,en)=>en,esc:v=>String(v??'').replaceAll('<','&lt;').replaceAll('"','&quot;'),fmt:(n,c)=>`${c} ${n/100}`,icon:n=>`<svg data-icon="${n}"></svg>`,...overrides};
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

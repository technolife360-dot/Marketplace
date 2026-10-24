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

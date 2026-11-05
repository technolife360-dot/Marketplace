const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function fixture(data){
 const button={addEventListener(){}};
 const root={isConnected:true,querySelector:()=>button};
 const app={innerHTML:'',querySelector:()=>root};
 const context={window:{},me:{id:'test'},api:async()=>data,location:{href:'http://local/#spin-win'},document:{title:''},app,Date,adminText:(_uz,_ru,en)=>en,esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/spin-win.js','utf8'),context);
 return {ui:context.window.SpinWin,app};
}
test('customer page keeps the wheel without probabilities or explanatory panels',async()=>{
 const f=fixture({test_only:true,can_spin:true,enabled:true,prizes:[{id:'none',kind:'none',name:'No prize',weight:100000}],next_reset:'2026-11-06T00:00:00+08:00',history:[]});
 await f.ui.customer();
 assert.match(f.app.innerHTML,/class="sw-wheel"/);assert.match(f.app.innerHTML,/Spin for free/);
 assert.doesNotMatch(f.app.innerHTML,/Prize probabilities|How does it work|sw-details|sw-rules|Segment sizes/);
});
test('wheel escapes labels received from the server',()=>{
 const f=fixture({});
 const html=f.ui.wheel([{id:'x',kind:'voucher',name:'<script>alert(1)</script>',weight:1}]);
 assert.match(html,/&lt;script>/);assert.doesNotMatch(html,/<script>/);
});
test('home does not open or fetch the spin popup for a guest',async()=>{
 const root={isConnected:true,innerHTML:'',showModal(){assert.fail('Guest popup opened');}};
 const context={window:{},me:null,api:async()=>assert.fail('Guest spin request')};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/spin-win.js','utf8'),context);
 await context.window.SpinWin.home(root);
 assert.equal(root.innerHTML,'');
});
test('home spin keeps the wheel in place and celebrates only winning results',async()=>{
 for(const kind of ['voucher','none']){
  let click;
  const button={addEventListener(_event,handler){click=handler;}};
  const wheel={style:{}};
  const frame={children:[],append(child){this.children.push(child);}};
  const result={innerHTML:''};
  const elements={'.sw-popup-close':{addEventListener(){}},'.sw-spin':button,'.sw-wheel':wheel,'.sw-error':{},'[data-sw-result]':result,'.sw-wheel-wrap':frame};
  const root={isConnected:true,innerHTML:'',addEventListener(){},showModal(){this.open=true;},querySelector:selector=>elements[selector]};
  const prizes=[{id:'bonus',kind:'voucher',name:'RM1'},{id:'none',kind:'none',name:'No prize'}];
  const award={prize_id:kind==='voucher'?'bonus':'none',prize_name:'RM1',kind};
  const context={window:{},me:{email_verified:true},adminText:(_uz,_ru,en)=>en,esc:String,
   api:async path=>path==='/spin-win/spin'?award:{enabled:true,can_spin:true,prizes},
   matchMedia:()=>({matches:false}),setTimeout:(callback,delay)=>{if(delay===2450)callback();},
   document:{createElement:()=>({style:{setProperty(){}},children:[],setAttribute(){},append(child){this.children.push(child);}})}};
  vm.createContext(context);vm.runInContext(fs.readFileSync('static/spin-win.js','utf8'),context);
  await context.window.SpinWin.home(root);
  const markup=root.innerHTML;
  assert.equal(root.open,true);
  assert.match(markup,/class="sw-hub sw-spin"/);
  await click();
  assert.equal(root.innerHTML,markup);
  assert.equal(wheel.style.transform,kind==='voucher'?'rotate(1710deg)':'rotate(1530deg)');
  assert.equal(button.disabled,true);
  assert.equal(frame.children.length,kind==='voucher'?1:0);
  if(kind==='voucher')assert.equal(frame.children[0].children.length,54);
 }
});

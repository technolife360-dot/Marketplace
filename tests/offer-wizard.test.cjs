const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/offer-wizard.js'),'utf8');
function payload(values){
  class FormValues {constructor(form){this.values=form.values;}[Symbol.iterator](){return Object.entries(this.values)[Symbol.iterator]();}getAll(key){const value=this.values[key];return value===undefined?[]:Array.isArray(value)?value:[value];}}
  const context={window:{},FormData:FormValues,adminText:(_uz,_ru,en)=>en};
  vm.createContext(context);vm.runInContext(source,context);
  return context.window.OfferWizard.payload({values:{game_name:'PUBG Mobile',category_id:'accounts',title:'Level 65 Ace account',description:'Accurate description',stock:'1',price_major:'129.90',platform:'Android / iOS',region:'Global',delivery_eta:'15 minutes',...values},elements:{accept_account_terms:{checked:true}}});
}
test('seller price uses exact MYR minor units without currency conversion',()=>{
  for(const [price,minor]of [['129.90',12990],['0.01',1],['10',1000],['10.5',1050],['10000000000.00',1000000000000]]){
    const result=payload({price_major:price});assert.equal(result.price_minor,minor);assert.equal(result.currency,'MYR');assert.equal(result.submit_for_review,true);
  }
});
test('invalid prices cannot silently round, overflow or become zero',()=>{
  for(const price of ['0','-1','1.234','1e2','Infinity','NaN','','10000000000.01'])assert.throws(()=>payload({price_major:price}),undefined,price);
});
test('submission only contains known offer fields and separates public attributes from providers',()=>{
  const result=payload({game_attr_account_level:'65',game_attr_original_email_included:'yes',linked_accounts:['google'],confirm_accuracy:'on',password:'not-persisted',csrf:'not-persisted'});
  assert.equal(result.attributes.account_level,'65');assert.equal(result.attributes.original_email_included,'yes');assert.deepEqual(Array.from(result.linked_accounts),['google']);assert.equal(result.password,undefined);assert.equal(result.csrf,undefined);assert.equal(result.confirm_accuracy,undefined);
});
test('MYR is displayed as ringgit on cards and order pages while legacy UZS keeps its unit',()=>{
 const app=fs.readFileSync(require('node:path').join(__dirname,'../static/app.js'),'utf8');
 const fn=app.match(/function fmt\(n,c='UZS'\)\{[^\n]+/)[0];
 const ctx={Intl,localeTag:()=> 'en-US'};vm.createContext(ctx);vm.runInContext(fn,ctx);
 assert.equal(ctx.fmt(12990,'MYR'),'RM 129.90');assert.equal(ctx.fmt(200000,'UZS'),'200,000 UZS');
});
function resultContext(api){
 const ctx={window:{},adminText:(_uz,_ru,en)=>en,esc:value=>String(value??'').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),icon:()=>'',fmt:()=> 'RM 129.90',me:{id:'seller'},api};
 const button={disabled:false,innerHTML:'Refresh status',textContent:'',isConnected:true};
 const error={hidden:true,textContent:''};
 ctx.app={innerHTML:'',querySelector:s=>s==='[data-review-refresh]'?button:s==='[data-review-error]'?error:{focus(){}}};
 vm.createContext(ctx);vm.runInContext(source,ctx);return {ctx,button,error};
}
const submitted={id:'real-offer-id',status:'pending_review',title:'PUBG Mobile account',currency:'MYR',price_minor:12990,game_name:'PUBG Mobile'};
test('submission result distinguishes a queued offer from publication and uses the listings dashboard',()=>{
 const {ctx}=resultContext();
 for(const status of ['pending_review','approved_private','published','rejected']){
  const html=ctx.window.OfferWizard.submissionMarkup({...submitted,status,title:'<script>bad</script>'});
  assert.ok(html.includes('#seller/dashboard'));assert.ok(html.includes('real-offer-id'));assert.ok(!html.includes('<script>'));
  assert.equal(html.includes('Your offer is now visible to buyers.'),status==='published');
  assert.equal(html.includes('No further action is needed'),status==='pending_review');
  assert.equal(html.includes('/listing/real-offer-id'),status==='published');
 }
});
test('failed result refresh keeps the current result visible and allows retry',async()=>{
 let calls=0;const {ctx,button,error}=resultContext(async()=>{if(calls++)throw Error('Connection lost');return submitted;});
 await ctx.window.OfferWizard.review(submitted.id);const initial=ctx.app.innerHTML;
 await button.onclick();assert.equal(ctx.app.innerHTML,initial);assert.equal(button.disabled,false);assert.equal(error.hidden,false);assert.equal(error.textContent,'Connection lost');
});
test('refresh reads the current server review status',async()=>{
 let calls=0;const {ctx,button}=resultContext(async()=>({...submitted,status:calls++?'approved_private':'pending_review'}));
 await ctx.window.OfferWizard.review(submitted.id);await button.onclick();
 assert.ok(ctx.app.innerHTML.includes('Your offer is approved. It will become visible when sales open.'));
});

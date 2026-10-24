const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/listing-detail.js'),'utf8');
function detail(){
  const ctx={window:{},adminText:(_uz,_ru,en)=>en,esc:v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
    icon:name=>`<svg data-icon="${name}"></svg>`,fmt:(n,c)=>`${c} ${n/100}`,categoryLabel:v=>v,listingProviders:[['google','Google']],
    marketSellerIdentity:i=>({name:i.seller_display_name||i.seller_name||'Seller',avatar:i.seller_avatar_url||''}),
    listingAttributeFacts:i=>i.product_type==='currency'?[['Amount',i.attributes.amount],['Currency',i.attributes.unit]]:[],listingDetailGallery:()=>'<div class="test-gallery"></div>',marketCard:()=>''};
  vm.createContext(ctx);vm.runInContext(source,ctx);return ctx.window.ListingDetail;
}
const item={id:'offer',seller_id:'seller',game_name:'PUBG Mobile',game_slug:'pubg-mobile',product_type:'account',category_id:'accounts',title:'Level 65 Ace account',description:'Actual seller description',price_minor:12990,currency:'MYR',available:1,status:'published',seller_display_name:'Real Seller',attributes:{account_level:'65',tier:'Ace',original_email_included:'yes',linked_accounts:['google']},seller:{total_sales:0}};
test('public page uses real identity and does not invent reputation or verification',()=>{
  const html=detail().markup({...item,seller_name:'Wrong shop title',seller_rating:4.9,review_count:28,verification_status:'verified'});
  assert.ok(html.includes('Real Seller'));assert.ok(!html.includes('Wrong shop title'));
  assert.ok(html.includes('No reviews yet'));assert.ok(!html.includes('4.9'));
  assert.ok(!html.includes('Identity verified'));assert.ok(html.includes('0</b> sales'));
  const verified=detail().markup({...item,identity_verified:true,seller_card_rating:4.8,seller_card_review_count:12,product_review_count:3});
  assert.ok(verified.includes('Identity verified'));assert.ok(verified.includes('4.8'));assert.ok(verified.includes('Reviews (3)'));
});
test('unavailable, reserved and vacation listings cannot expose an enabled purchase button',()=>{
  for(const overrides of [{status:'sold_out'},{status:'paused'},{available:0},{min_quantity:2},{availability:{vacation:true}}]){
    assert.match(detail().markup({...item,...overrides}),/data-action="buy-now"[^>]*disabled/);
  }
  assert.doesNotMatch(detail().markup(item),/data-action="buy-now"[^>]*disabled/);
});
test('seller chat is offered to buyers and cannot open a conversation with yourself',()=>{
  const buyer=detail().markup(item);
  assert.match(buyer,/data-action="contact-seller" data-id="offer"/);
  assert.ok(buyer.includes('Message seller'));
  const owner=detail().markup({...item,is_owner:true});
  assert.ok(owner.includes('Message seller'));
  assert.ok(owner.includes('This is your own listing'));
  assert.ok(!owner.includes('data-action="contact-seller"'));
  assert.ok(!owner.includes('Buyer messages'));
});
test('account and currency specifications keep their own product data',()=>{
  const account=detail().facts(item);
  assert.ok(account.some(([k,v])=>k==='Account level'&&v==='65'));
  assert.ok(account.some(([k,v])=>k==='Original email'&&v==='Included'));
  assert.ok(account.some(([k,v])=>k==='Linked services'&&v==='Google'));
  const currency=detail().facts({...item,product_type:'currency',attributes:{amount:'325',unit:'UC'}});
  assert.ok(currency.some(([k,v])=>k==='Amount'&&v==='325'));
  assert.ok(!currency.some(([k])=>k==='Account level'));
});
test('untrusted titles, descriptions, identities and attributes remain text',()=>{
  const html=detail().markup({...item,title:'<script>bad</script>',description:'<img src=x onerror=bad()>',seller_display_name:'<b>Seller</b>',attributes:{account_level:'<img src=x>'}});
  assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img src=x'));
  assert.ok(html.includes('&lt;b&gt;Seller&lt;/b&gt;'));
  assert.ok(html.includes('&lt;img src=x&gt;'));
});

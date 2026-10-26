const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const appSource=fs.readFileSync('static/app.js','utf8');
const selectSource=fs.readFileSync('static/select-menu.js','utf8');

test('an unchanged dropdown does not write observed attributes and restart its observer',()=>{
 let disabled=false,hidden=true,writes=0;
 const trigger={setAttribute(){}};Object.defineProperty(trigger,'disabled',{get:()=>disabled,set:v=>{disabled=v;writes++;}});
 const search={placeholder:'Search options…',setAttribute(){}};Object.defineProperty(search,'hidden',{get:()=>hidden,set:v=>{hidden=v;writes++;}});
 const context={picker:{isConnected:true},label(){},trigger,search,select:{disabled:false,required:false,selectedOptions:[],options:[],multiple:false},value:{textContent:'Choose an option'},signature:'[]',text:(_u,_r,en)=>en,empty:{textContent:'No options found'},active:null,state:{}};
 vm.createContext(context);vm.runInContext(selectSource.slice(selectSource.indexOf('  function sync(){'),selectSource.indexOf('  function close(')),context);
 context.sync();context.sync();assert.equal(writes,0);
 context.select.disabled=true;context.sync();context.sync();assert.equal(writes,1);assert.equal(disabled,true);
});

test('dropdown mutation filtering ignores picker output while preserving native select changes',()=>{
 const root={},context={document:{documentElement:root}};vm.createContext(context);
 vm.runInContext(selectSource.slice(selectSource.indexOf(' function relevantMutation('),selectSource.indexOf('\n const observer=',selectSource.indexOf(' function relevantMutation('))),context);
 const node=tag=>({nodeType:1,matches:selector=>selector.split(',').includes(tag),querySelector:()=>null,closest:selector=>selector.split(',').includes(tag)?{}:null});
 assert.equal(context.relevantMutation({type:'attributes',target:node('input')}),false);
 assert.equal(context.relevantMutation({type:'attributes',target:node('select')}),true);
 assert.equal(context.relevantMutation({type:'attributes',target:root}),true);
 assert.equal(context.relevantMutation({type:'childList',target:node('div'),addedNodes:[node('button')],removedNodes:[]}),false);
 assert.equal(context.relevantMutation({type:'childList',target:node('select'),addedNodes:[node('option')],removedNodes:[]}),true);
 assert.equal(context.relevantMutation({type:'childList',target:node('div'),addedNodes:[{...node('section'),querySelector:()=>({})}],removedNodes:[]}),true);
});

function apiHarness(){
 let count=0,now=0;const context={window:{},csrf:'',localized:String,Date:{now:()=>now},fetch:async(url,opt)=>{count++;return {ok:true,json:async()=>({url,method:opt.method||'GET',items:[{name:'Original'}]})};}};
 vm.createContext(context);const start=appSource.indexOf('const referenceCache=');const end=appSource.indexOf('\nfunction ',appSource.indexOf('async function apiRequest(',start));vm.runInContext(appSource.slice(start,end),context);
 return {context,count:()=>count,tick:()=>{now+=60001;}};
}
test('public reference requests share one fetch, expire, and invalidate on writes',async()=>{
 const h=apiHarness();const [first,second]=await Promise.all([h.context.api('/games'),h.context.api('/games')]);assert.equal(h.count(),1);
 first.items[0].name='Changed';assert.equal(second.items[0].name,'Original');assert.equal((await h.context.api('/games')).items[0].name,'Original');assert.equal(h.count(),1);
 h.tick();await h.context.api('/games');assert.equal(h.count(),2);
 await h.context.api('/profile',{method:'POST'});await h.context.api('/games');assert.equal(h.count(),4);
});
test('private data and live prices never use the public reference cache',async()=>{
 const h=apiHarness();for(const route of ['/me','/cart','/orders','/notifications','/listings?limit=12']){await h.context.api(route);await h.context.api(route);}assert.equal(h.count(),10);
});

test('account rendering does not wait for non-critical collection synchronization',async()=>{
 let finishCollections,navigations=0;
 const context={window:{MobileSite:{sessionReady(){}}},location:{hash:'#account',pathname:'/',search:''},localStorage:{getItem:()=>null},localeKey:'language',supportedLocales:new Set(['en']),loadAsiaMarkets:async()=>{},api:async()=>({user:{id:'buyer'},csrf:'test'}),syncProfileTrigger(){},syncLanguageMenu(){},syncSellItemButton(){},syncAdminLink(){},renderSupportWidget(){},document:{documentElement:{}},isHomeLocation:()=>false,navigate:async()=>{navigations++;},ExperienceUX:{sync:()=>new Promise(resolve=>{finishCollections=resolve;})},URLSearchParams,localizeDOM(){},refreshCart(){},refreshNotifications(){}};
 vm.createContext(context);const start=appSource.indexOf('async function bootstrap(){');vm.runInContext(appSource.slice(start,appSource.indexOf('\n}',start)+2),context);
 const pending=context.bootstrap();await new Promise(resolve=>setImmediate(resolve));assert.equal(navigations,1);finishCollections();await pending;
});

test('localization writes the language only when it changes, breaking the Crisp observer cycle',()=>{
 let language='en',direction='ltr',writes=0;
 const html={};for(const [key,get,set] of [['lang',()=>language,v=>language=v],['dir',()=>direction,v=>direction=v]])Object.defineProperty(html,key,{get,set:v=>{writes++;set(v);}});
 const context={locale:'en',document:{body:{},documentElement:html,createTreeWalker:()=>({nextNode:()=>null})},NodeFilter:{SHOW_TEXT:4},$$:()=>[],$:()=>null,syncLanguageMenu(){}};
 vm.createContext(context);vm.runInContext(appSource.slice(appSource.indexOf('function localizeDOM('),appSource.indexOf('\nlet localizeQueued=')),context);
 context.localizeDOM();context.localizeDOM();assert.equal(writes,0);
 context.locale='uz';context.localizeDOM();context.localizeDOM();assert.equal(writes,1);assert.equal(language,'uz');
 context.locale='ar';context.localizeDOM();context.localizeDOM();assert.equal(writes,3);assert.equal(direction,'rtl');
});

test('Crisp labels stay unchanged on repeated language notifications but update for a new language',()=>{
 const source=fs.readFileSync('static/crisp-loader.js','utf8');let writes=0,copy=['Need a hand?','Send us your question.','Open chat','Open support chat','Close'];
 const nodes=Object.fromEntries(['strong','p','.support-hint-open'].map((selector,index)=>{let value=copy[index];return [selector,Object.defineProperty({},'textContent',{get:()=>value,set:v=>{writes++;value=v;}})];}));
 nodes['.support-hint-dismiss']={setAttribute(){}};
 const context={words:()=>copy,hint:{querySelector:selector=>nodes[selector]},launcher:{setAttribute(){}},document:{documentElement:{dataset:{}}}};
 vm.createContext(context);vm.runInContext(source.slice(source.indexOf('  function syncLabels()'),source.indexOf('  function dismissHint()')),context);
 context.syncLabels();context.syncLabels();assert.equal(writes,0);
 copy=['Yordam kerakmi?','Savolingizni bizga yozing.','Chatni ochish','Yordam chatini ochish','Yopish'];context.syncLabels();context.syncLabels();assert.equal(writes,3);assert.equal(nodes.strong.textContent,copy[0]);
});

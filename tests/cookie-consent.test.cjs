const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const tick=()=>new Promise(r=>setImmediate(r));
function fixture({saved=null,failSave=false}={}){
 const nodes=new Map(),listeners={},events=[],storage=new Map([['sentryloot-cookie-consent-v1',JSON.stringify({analytics:true,support:true})]]),requests=[];
 const document={getElementById:id=>nodes.get(id),createElement:()=>({setAttribute(){},remove(){nodes.delete(this.id)}}),body:{append(n){nodes.set(n.id,n)}},querySelectorAll:()=>[],addEventListener(name,fn){listeners[name]=fn}};
 const context={document,localStorage:{setItem:(k,v)=>storage.set(k,v),getItem:k=>storage.get(k),removeItem:k=>storage.delete(k)},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},location:{reload(){events.push('reload')}},fetch:async(url,options={})=>{requests.push([url,options]);return {ok:!(failSave&&options.method==='POST'),json:async()=>url==='/api/me'?{csrf:'csrf-test'}:{consent:options.method==='POST'?{...JSON.parse(options.body),receipt_id:'receipt',policy_version:'2026-10-30.1'}:saved}}}};
 context.window={addEventListener(){},dispatchEvent:e=>events.push(e)};
 vm.createContext(context);vm.runInContext(fs.readFileSync('static/cookie-consent.js','utf8'),context);
 return {api:context.window.CookieConsent,requests,storage,nodes,events,async click(attribute){listeners.click({preventDefault(){},target:{closest(){return{hasAttribute:k=>k===attribute}}}});await tick();await tick();}};
}
test('a cached or legacy choice cannot enable services without a server receipt',async()=>{
 const f=fixture();assert.equal(f.api.allows('analytics'),false);await tick();assert.equal(f.api.ready(),true);assert.equal(f.api.allows('support'),false);assert.equal(f.nodes.has('cookie-notice'),true);
});
test('Accept all records the choice with CSRF before enabling integrations',async()=>{
 const f=fixture();await tick();await f.click('data-cookie-accept');
 const post=f.requests.find(([,o])=>o.method==='POST');assert.equal(post[1].headers['X-CSRF-Token'],'csrf-test');assert.equal(post[1].headers['X-Consent-Request'],'1');
 assert.equal(f.api.allows('analytics'),true);assert.equal(f.api.allows('support'),true);assert.equal(f.nodes.has('cookie-notice'),false);assert.equal(JSON.parse(f.storage.get('sentryloot-cookie-consent-v1')).receipt_id,'receipt');
});
test('Reject optional is persisted and failed saves never enable services',async()=>{
 const f=fixture();await tick();await f.click('data-cookie-reject');assert.equal(f.api.allows('analytics'),false);assert.equal(f.api.get().support,false);assert.equal(f.nodes.has('cookie-notice'),false);
 const failed=fixture({failSave:true});await tick();await failed.click('data-cookie-accept');assert.equal(failed.api.allows('analytics'),false);assert.equal(failed.nodes.has('cookie-notice'),true);
});
test('analytics scripts load only after opt-in and only once',()=>{
 let allowed=false;const appended=[],listeners={};const window={CookieConsent:{allows:()=>allowed},addEventListener:(name,fn)=>listeners[name]=fn};
 const document={createElement:()=>({dataset:{}}),head:{append:s=>appended.push(s.src)}};
 vm.runInNewContext(fs.readFileSync('static/vercel-insights.js','utf8'),{window,document});assert.deepEqual(appended,[]);
 allowed=true;listeners['sentryloot:consent']();listeners['sentryloot:consent']();assert.deepEqual(appended,['/_vercel/insights/script.js','/_vercel/speed-insights/script.js']);
});

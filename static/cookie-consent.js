/* Optional integrations remain off until a valid server receipt is returned. */
(() => {
  const cacheKey='sentryloot-cookie-consent-v1';
  let consent=null, busy=false, initialized=false;
  const allowed=category=>Boolean(consent?.[category]);
  const changed=()=>window.dispatchEvent(new CustomEvent('sentryloot:consent',{detail:consent}));
  function banner(){
    if(document.getElementById('cookie-notice'))return;
    const node=document.createElement('section');node.id='cookie-notice';node.setAttribute('role','region');node.setAttribute('aria-labelledby','cookie-notice-title');
    node.innerHTML='<div class="cookie-notice-copy"><h2 id="cookie-notice-title">Cookies</h2><p>Essential cookies keep the site working. Choose whether to allow analytics and support chat. <a href="/privacy-policy">Privacy Policy</a></p><p class="cookie-save-error" role="status" hidden></p></div><div class="cookie-notice-actions"><button class="cookie-secondary" type="button" data-cookie-reject>Reject optional</button><button class="cookie-secondary" type="button" data-cookie-settings>Settings</button><button type="button" data-cookie-accept>Accept all</button></div>';
    document.body.append(node);
  }
  function dialog(){
    let node=document.getElementById('cookie-preferences');if(node)return node;
    node=document.createElement('dialog');node.id='cookie-preferences';node.setAttribute('aria-labelledby','cookie-preferences-title');
    node.innerHTML='<h2 id="cookie-preferences-title">Cookie settings</h2><p>Essential cookies are always enabled for sign-in, security and your cookie choices. Optional services stay off until you allow them.</p><label><input type="checkbox" name="analytics"><span><b>Analytics</b><small>Vercel visitor statistics and performance measurements.</small></span></label><label><input type="checkbox" name="support"><span><b>Support chat</b><small>Crisp chat and its browser storage. You can still use our email support without it.</small></span></label><p class="cookie-save-error" role="status" hidden></p><a href="/privacy-policy">Privacy Policy</a><div class="cookie-dialog-actions"><button type="button" data-cookie-close>Cancel</button><button type="button" data-cookie-save>Save preferences</button></div>';
    document.body.append(node);return node;
  }
  function open(){
    const node=dialog();node.querySelector('[name=analytics]').checked=allowed('analytics');node.querySelector('[name=support]').checked=allowed('support');
    node.querySelector('[role=status]').hidden=true;if(!node.open)node.showModal();
  }
  function eraseOptionalStorage(){
    // Only integration-owned first-party storage is cleared. Session/cart data stays intact.
    for(const name of ['localStorage','sessionStorage'])try{
      const storage=window[name];
      for(let i=storage.length-1;i>=0;i--){const k=storage.key(i);if(/^(crisp-client|_vercel|va-session)/i.test(k))storage.removeItem(k);}
    }catch(_){}
    for(const part of document.cookie.split(';')){
      const name=part.trim().split('=')[0];if(!/^(crisp-client|_vercel|va-session)/i.test(name))continue;
      const host=location.hostname.split('.');
      document.cookie=name+'=; Max-Age=0; Path=/';
      for(let i=0;i<host.length-1;i++)document.cookie=name+'=; Max-Age=0; Path=/; Domain=.'+host.slice(i).join('.');
    }
  }
  function apply(next){
    const revoke=(allowed('analytics')&&!next?.analytics)||(allowed('support')&&!next?.support);
    consent=next;
    try{if(next)localStorage.setItem(cacheKey,JSON.stringify(next));else localStorage.removeItem(cacheKey);}catch(_){}
    if(next)document.getElementById('cookie-notice')?.remove();else banner();
    if(revoke){eraseOptionalStorage();location.reload();return;}
    changed();
  }
  async function save(analytics,support){
    if(busy)return;busy=true;
    document.querySelectorAll('#cookie-notice button,#cookie-preferences button').forEach(b=>b.disabled=true);
    try{
      const session=await fetch('/api/me',{credentials:'same-origin',cache:'no-store'});if(!session.ok)throw Error('session');
      const me=await session.json();
      const response=await fetch('/api/cookie-consent',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-Consent-Request':'1',...(me.csrf?{'X-CSRF-Token':me.csrf}:{})},body:JSON.stringify({analytics,support})});
      if(!response.ok)throw Error('save');
      const data=await response.json();if(!data.consent)throw Error('receipt');
      document.getElementById('cookie-preferences')?.close();apply(data.consent);
    }catch(_){
      document.querySelectorAll('.cookie-save-error').forEach(e=>{e.textContent='Could not save your choice. Please try again.';e.hidden=false;});
    }finally{busy=false;document.querySelectorAll('#cookie-notice button,#cookie-preferences button').forEach(b=>b.disabled=false);}
  }
  async function refresh(){
    try{const r=await fetch('/api/cookie-consent',{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw Error('receipt');const data=await r.json();apply(data.consent);}
    catch(_){apply(null);}
    initialized=true;
  }
  window.CookieConsent={allows:allowed,open,get:()=>consent,ready:()=>initialized};
  const mobileSettings=document.createElement('button');mobileSettings.type='button';mobileSettings.className='cookie-mobile-settings';mobileSettings.setAttribute('data-cookie-settings','');mobileSettings.textContent='Cookie settings';document.body.append(mobileSettings);
  document.addEventListener('click',e=>{
    const b=e.target.closest('[data-cookie-settings],[data-cookie-accept],[data-cookie-reject],[data-cookie-save],[data-cookie-close]');if(!b)return;e.preventDefault();
    if(b.hasAttribute('data-cookie-settings'))open();
    else if(b.hasAttribute('data-cookie-accept'))save(true,true);
    else if(b.hasAttribute('data-cookie-reject'))save(false,false);
    else if(b.hasAttribute('data-cookie-save')){const d=dialog();save(d.querySelector('[name=analytics]').checked,d.querySelector('[name=support]').checked);}
    else dialog().close();
  });
  window.addEventListener('storage',e=>{if(e.key===cacheKey)refresh();});
  window.addEventListener('pageshow',e=>{if(e.persisted)location.reload();});
  refresh();
})();

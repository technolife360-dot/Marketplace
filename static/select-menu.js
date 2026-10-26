/* One compact, searchable dropdown for native selects. Native values remain the form source. */
window.SelectMenus=(()=>{
 const states=new WeakMap();let sequence=0,active=null,queued=false;
 const text=(uz,ru,en)=>document.documentElement.lang==='uz'?uz:document.documentElement.lang==='ru'?ru:en;
 const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function enhance(select){
  if(states.has(select)){states.get(select).sync();return}
  const id='site-select-'+(++sequence),picker=document.createElement('div');picker.className='site-select auth-country-picker';
  picker.innerHTML=`<button type="button" class="site-select-trigger auth-country-trigger" role="combobox" aria-haspopup="listbox" aria-expanded="false" aria-controls="${id}-list"><span class="site-select-value"></span><svg class="site-select-chevron" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></button><div class="site-select-popup auth-country-popup" popover="manual" hidden><input type="search" class="site-select-search auth-country-search" autocomplete="off"><div id="${id}-list" class="site-select-list" role="listbox"></div><p class="site-select-empty auth-country-empty" hidden></p></div>`;
  select.classList.add('site-select-native');select.tabIndex=-1;select.setAttribute('aria-hidden','true');select.after(picker);
  const trigger=picker.querySelector('button'),popup=picker.querySelector('.site-select-popup'),search=picker.querySelector('input'),list=picker.querySelector('[role=listbox]'),empty=picker.querySelector('.site-select-empty'),value=picker.querySelector('.site-select-value');
  let signature='',options=[];
  const state={picker,sync,close,position};states.set(select,state);
  function label(){const nativeLabel=select.labels?.[0];if(nativeLabel){if(!nativeLabel.id)nativeLabel.id=id+'-label';trigger.setAttribute('aria-labelledby',nativeLabel.id);return}trigger.setAttribute('aria-label',select.getAttribute('aria-label')||select.title||select.name||text('Tanlang','Выберите','Choose an option'))}
  function filter(){const query=search.value.trim().normalize('NFKD').toLocaleLowerCase();options.forEach(button=>{const hidden=select.options[Number(button.dataset.option)].hidden||!button.textContent.normalize('NFKD').toLocaleLowerCase().includes(query);if(button.hidden!==hidden)button.hidden=hidden;});const hideEmpty=options.some(button=>!button.hidden);if(empty.hidden!==hideEmpty)empty.hidden=hideEmpty}
  function sync(){
   if(!picker.isConnected)return;
   label();if(trigger.disabled!==select.disabled)trigger.disabled=select.disabled;trigger.setAttribute('aria-required',String(select.required));
   const caption=[...select.selectedOptions].map(option=>option.label).join(', ')||text('Tanlang','Выберите','Choose an option');if(value.textContent!==caption)value.textContent=caption;
   const snapshot=JSON.stringify([...select.options].map(o=>[o.label,o.value,o.disabled,o.parentElement.disabled||false,o.hidden,o.selected]));
   if(signature!==snapshot){signature=snapshot;list.innerHTML=[...select.options].map((o,index)=>`<button type="button" role="option" data-option="${index}" aria-selected="${o.selected}" ${o.disabled||o.parentElement.disabled?'disabled':''}><span>${escape(o.label)}</span><span class="site-select-check" aria-hidden="true">✓</span></button>`).join('');options=[...list.children];filter()}
   const hint=text('Qidirish…','Поиск…','Search options…');if(search.placeholder!==hint){search.placeholder=hint;search.setAttribute('aria-label',hint)}
   const hideSearch=select.options.length<=8;if(search.hidden!==hideSearch)search.hidden=hideSearch;const noResults=text('Natija topilmadi','Ничего не найдено','No options found');if(empty.textContent!==noResults)empty.textContent=noResults;
   if(select.multiple)list.setAttribute('aria-multiselectable','true');
   if(select.disabled&&active===state)close();
  }
  function close(focus=false){if(popup.matches(':popover-open'))popup.hidePopover();popup.hidden=true;trigger.setAttribute('aria-expanded','false');if(active===state)active=null;if(focus&&trigger.isConnected)trigger.focus({preventScroll:true})}
  function position(){const rect=trigger.getBoundingClientRect();popup.style.left=rect.left+'px';popup.style.top=(rect.bottom+6)+'px';popup.style.width=rect.width+'px';const available=Math.max(60,window.innerHeight-rect.bottom-24-(search.hidden?16:60));list.style.maxHeight=Math.min(180,available)+'px'}
  function open(){if(select.disabled)return;if(active&&active!==state)active.close();search.value='';sync();filter();popup.hidden=false;position();
   if(popup.showPopover)popup.showPopover();trigger.setAttribute('aria-expanded','true');active=state;
   const selected=options.find(o=>o.getAttribute('aria-selected')==='true'&&!o.disabled&&!o.hidden);if(!search.hidden)search.focus({preventScroll:true});else(selected||options.find(o=>!o.disabled&&!o.hidden))?.focus({preventScroll:true});if(selected)list.scrollTop=selected.offsetTop-list.offsetTop;
  }
  trigger.addEventListener('click',()=>popup.hidden?open():close());
  search.addEventListener('input',filter);
  list.addEventListener('click',event=>{const button=event.target.closest('[data-option]');if(!button||button.disabled)return;const option=select.options[Number(button.dataset.option)];if(!option)return;
   const changed=select.multiple||select.selectedIndex!==option.index;if(select.multiple)option.selected=!option.selected;else select.selectedIndex=option.index;
   trigger.removeAttribute('aria-invalid');sync();if(!select.multiple)close(true);if(changed){select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}))}
  });
  select.addEventListener('change',sync);
  select.addEventListener('invalid',event=>{event.preventDefault();trigger.setAttribute('aria-invalid','true');trigger.focus();open()});
  picker.addEventListener('keydown',event=>{
   if(event.key==='Escape'&&!popup.hidden){event.preventDefault();event.stopPropagation();close(true);return}
   if(event.key==='Tab'){close(true);return}
   if(popup.hidden&&['ArrowDown','ArrowUp'].includes(event.key)){event.preventDefault();open();return}
   if(popup.hidden)return;
   const visible=options.filter(o=>!o.hidden&&!o.disabled);
   if(event.target===search&&event.key==='Enter'){event.preventDefault();visible[0]?.click();return}
   if(!['ArrowDown','ArrowUp','Home','End'].includes(event.key)||event.target===search&&['Home','End'].includes(event.key))return;
   event.preventDefault();const current=visible.indexOf(document.activeElement),index=event.key==='Home'?0:event.key==='End'?visible.length-1:event.key==='ArrowDown'?Math.min(current+1,visible.length-1):Math.max(current-1,0);visible[index]?.focus();
  });
  select.form?.addEventListener('reset',()=>requestAnimationFrame(()=>{sync();close()}));
  sync();
 }
 function refresh(){queued=false;if(active&&!active.picker.isConnected)active.close();document.querySelectorAll('select').forEach(enhance)}
 function schedule(){if(!queued){queued=true;requestAnimationFrame(refresh)}}
 document.addEventListener('pointerdown',event=>{if(active&&!active.picker.contains(event.target))active.close()});
 document.addEventListener('click',event=>{const label=event.target.closest('label');if(label?.control?.tagName==='SELECT'&&!event.target.closest('.site-select')){const state=states.get(label.control);if(state){event.preventDefault();state.picker.querySelector('button').focus()}}});
 document.addEventListener('scroll',event=>{if(active&&!active.picker.contains(event.target))active.position()},true);
 window.addEventListener('resize',()=>active?.close());
 function relevantMutation(record){
  if(record.type==='attributes')return record.target===document.documentElement||record.target.matches('select,option,optgroup');
  if(record.target.closest?.('select,optgroup,option'))return true;
  return [...record.addedNodes,...record.removedNodes].some(node=>node.nodeType===1&&(node.matches('select')||node.querySelector('select')));
 }
 const observer=new MutationObserver(records=>{if(records.some(relevantMutation))schedule();});
 observer.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['disabled','label','selected','hidden']});
 observer.observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
 schedule();return {enhance,refresh};
})();

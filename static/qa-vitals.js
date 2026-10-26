/* Explicit opt-in diagnostics: no metrics are transmitted or enabled by default. */
(()=>{
 if(new URLSearchParams(location.search).get('qa_metrics')!=='1')return;
 const panel=document.createElement('aside');panel.id='qa-vitals';panel.setAttribute('aria-label','Browser performance measurements');panel.innerHTML='<b>Navigation Web Vitals · lab run</b><dl>'+['FCP','LCP','CLS','INP','TTFB'].map(k=>'<div><dt>'+k+'</dt><dd data-metric="'+k+'">waiting</dd></div>').join('')+'</dl><small>Current navigation. INP needs interaction. No data is sent.</small><button type="button" aria-label="Close diagnostics">×</button>';
 document.body.append(panel);panel.querySelector('button').onclick=()=>panel.remove();
 // Local snapshots help distinguish network delay from repeated DOM work.
 let mutations=0,longTasks=0,longTaskMs=0,layoutSources=[],lastMutations=0,lastSnapshot=performance.now();const started=lastSnapshot;
 const changes=new MutationObserver(records=>{for(const record of records){if(!panel.contains(record.target))mutations++;}});
 changes.observe(document.body,{subtree:true,childList:true,attributes:true});
 let taskObserver;
 if(window.PerformanceObserver&&PerformanceObserver.supportedEntryTypes?.includes('longtask')){
  taskObserver=new PerformanceObserver(list=>{for(const entry of list.getEntries()){longTasks++;longTaskMs+=entry.duration;}});taskObserver.observe({type:'longtask',buffered:true});
 }
 // Keep metric cells fixed in size so diagnostics do not create layout shifts.
 const style=document.createElement('style');style.textContent='#qa-vitals dl div{height:18px;min-height:18px;overflow:hidden;align-items:center}#qa-vitals dt{min-width:0;overflow:hidden;white-space:nowrap}#qa-vitals dd{flex:0 0 104px;width:104px;text-align:right;margin:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}';panel.append(style);
 const extra=document.createElement('dl');extra.dataset.qaRuntime='';panel.insertBefore(extra,panel.querySelector('small'));
 const refresh=document.createElement('button');refresh.type='button';refresh.textContent='Snapshot';refresh.className='qa-snapshot';refresh.style.cssText='position:static;display:block;margin-top:8px;font-size:11px';panel.append(refresh);
 function snapshot(){
  const resources=performance.getEntriesByType('resource'),apis=resources.filter(entry=>new URL(entry.name).origin===location.origin&&new URL(entry.name).pathname.startsWith('/api/'));
  const nav=performance.getEntriesByType('navigation')[0];
  const now=performance.now(),interval=(now-lastSnapshot)/1000,intervalChanges=mutations-lastMutations;
  const metrics=[['DOM changes',mutations],['Since snapshot',intervalChanges+' / '+interval.toFixed(1)+' s'],['DOM changes / sec',Math.round(mutations/Math.max(1,(performance.now()-started)/1000))],['Long tasks',longTasks],['Long task time',Math.round(longTaskMs)+' ms'],['API requests',apis.length],['Slowest API',Math.round(Math.max(0,...apis.map(entry=>entry.duration)))+' ms'],['Resources',resources.length],['DOMContentLoaded',nav?Math.round(nav.domContentLoadedEventEnd)+' ms':'—'],['Layout sources',layoutSources.join(', ')||'—'],['API types',[...new Set(apis.map(entry=>new URL(entry.name).pathname.split('/').slice(0,3).join('/')))].join(', ')]];
  lastMutations=mutations;lastSnapshot=now;
  extra.innerHTML=metrics.map(([key,value])=>'<div><dt>'+key+'</dt><dd>'+value+'</dd></div>').join('');
 }
 refresh.onclick=snapshot;const timer=setTimeout(snapshot,5000);
 panel.querySelector('button[aria-label="Close diagnostics"]').onclick=()=>{clearTimeout(timer);changes.disconnect();taskObserver?.disconnect();panel.remove();};
 const script=document.createElement('script');script.src='/static/vendor/web-vitals.iife.js';script.onload=()=>{const report=metric=>{if(metric.name==='CLS')layoutSources=metric.entries.flatMap(entry=>(entry.sources||[]).map(source=>source.node?.tagName?.toLowerCase()+'.'+String(source.node?.className||'').split(' ').slice(0,2).join('.'))).filter(Boolean).slice(0,8);const cell=panel.querySelector('[data-metric="'+metric.name+'"]');if(cell)cell.textContent=(metric.name==='CLS'?metric.value.toFixed(3):Math.round(metric.value)+' ms')+' · '+metric.rating};for(const name of ['onFCP','onLCP','onCLS','onINP','onTTFB'])window.webVitals[name](report,{reportAllChanges:true})};script.onerror=()=>{panel.querySelector('small').textContent='Metrics library could not load.'};document.head.append(script)
})();

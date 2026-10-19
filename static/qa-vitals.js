/* Explicit opt-in diagnostics: no metrics are transmitted or enabled by default. */
(()=>{
 if(new URLSearchParams(location.search).get('qa_metrics')!=='1')return;
 const panel=document.createElement('aside');panel.id='qa-vitals';panel.setAttribute('aria-label','Browser performance measurements');panel.innerHTML='<b>Navigation Web Vitals · lab run</b><dl>'+['FCP','LCP','CLS','INP','TTFB'].map(k=>'<div><dt>'+k+'</dt><dd data-metric="'+k+'">waiting</dd></div>').join('')+'</dl><small>Current navigation. INP needs interaction. No data is sent.</small><button type="button" aria-label="Close diagnostics">×</button>';
 document.body.append(panel);panel.querySelector('button').onclick=()=>panel.remove();
 const script=document.createElement('script');script.src='/static/vendor/web-vitals.iife.js';script.onload=()=>{const report=metric=>{const cell=panel.querySelector('[data-metric="'+metric.name+'"]');if(cell)cell.textContent=(metric.name==='CLS'?metric.value.toFixed(3):Math.round(metric.value)+' ms')+' · '+metric.rating};for(const name of ['onFCP','onLCP','onCLS','onINP','onTTFB'])window.webVitals[name](report,{reportAllChanges:true})};script.onerror=()=>{panel.querySelector('small').textContent='Metrics library could not load.'};document.head.append(script)
})();

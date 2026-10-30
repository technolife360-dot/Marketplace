/* Version country data explicitly: old Asia-only responses can remain in HTTP caches. */
async function loadRegionData(url){const response=await fetch(url,{credentials:'same-origin',signal:AbortSignal.timeout(6000)});if(!response.ok)throw Error('Regional data unavailable');return response.json()}
window.SENTRYLOOT_MARKETS_READY=Promise.allSettled([
 loadRegionData('/static/asia-markets.json?v=global-20261029-2'),
 loadRegionData('/static/regional-languages.json?v=6')
]).then(([countries,languages])=>{
 window.SENTRYLOOT_LANGUAGE_DATA=languages.status==='fulfilled'?languages.value:null;
 const fallback=[{country:'US',currency:'USD',language:'en'},{country:'GB',currency:'GBP',language:'en'},{country:'DE',currency:'EUR',language:'de'},{country:'FR',currency:'EUR',language:'fr'},{country:'IT',currency:'EUR',language:'it'},{country:'ES',currency:'EUR',language:'es'},{country:'NL',currency:'EUR',language:'nl'},{country:'PL',currency:'PLN',language:'pl'},{country:'PT',currency:'EUR',language:'pt'},{country:'CA',currency:'CAD',language:'en'},{country:'MY',currency:'MYR',language:'ms'},{country:'SG',currency:'SGD',language:'en'},{country:'SA',currency:'SAR',language:'ar'},{country:'UZ',currency:'UZS',language:'uz'},{country:'RU',currency:'RUB',language:'ru'}];
 window.SENTRYLOOT_ASIA_MARKETS=countries.status==='fulfilled'?countries.value:fallback;
 window.SENTRYLOOT_MARKETS_INCOMPLETE=countries.status!=='fulfilled';
 return window.SENTRYLOOT_ASIA_MARKETS;
});

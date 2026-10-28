window.SENTRYLOOT_MARKETS_READY = fetch('/static/asia-markets.json', { credentials: 'same-origin' })
  .then((response) => {
    if (!response.ok) throw new Error('Country and currency data unavailable');
    return response.json();
  })
  .then((markets) => {
    window.SENTRYLOOT_ASIA_MARKETS = markets;
    return markets;
  })
  .catch(() => {
    const fallback = [{country:'US',currency:'USD'},{country:'GB',currency:'GBP'},{country:'DE',currency:'EUR'},{country:'CA',currency:'CAD'},{country:'MY',currency:'MYR'},{country:'SG',currency:'SGD'},{country:'SA',currency:'SAR'},{country:'UZ',currency:'UZS'},{country:'RU',currency:'RUB'}];
    window.SENTRYLOOT_ASIA_MARKETS = fallback;
    return fallback;
  });

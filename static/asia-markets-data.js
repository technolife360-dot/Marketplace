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
    window.SENTRYLOOT_ASIA_MARKETS = [];
    return [];
  });

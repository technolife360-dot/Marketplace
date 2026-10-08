(function () {
  if (window.__sentryLootCrispLoaded) return;
  window.__sentryLootCrispLoaded = true;
  window.$crisp = window.$crisp || [];
  window.CRISP_WEBSITE_ID = '23d64f2d-3d3a-4e73-bca1-4e24795ba125';

  var script = document.createElement('script');
  script.src = 'https://client.crisp.chat/l.js';
  script.async = true;
  script.onerror = function () {
    window.__sentryLootCrispLoadFailed = true;
  };
  document.head.appendChild(script);
})();

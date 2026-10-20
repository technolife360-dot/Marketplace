(function () {
  if (window.__sentryLootCrispLoaded) return;
  window.__sentryLootCrispLoaded = true;
  window.$crisp = window.$crisp || [];
  // Official Web Chat SDK configuration; keep vendor controls readable.
  window.$crisp.push(["config", "color:theme", ["black"]]);
  window.$crisp.push(["config", "color:mode", ["dark"]]);
  window.CRISP_WEBSITE_ID = '23d64f2d-3d3a-4e73-bca1-4e24795ba125';
  var locale = 'en';
  try { locale = localStorage.getItem('bozor-language') || 'en'; } catch (_) {}
  if (!['en', 'uz', 'ru'].includes(locale)) locale = 'en';
  window.CRISP_RUNTIME_CONFIG = Object.assign({}, window.CRISP_RUNTIME_CONFIG, { locale: locale });

  var script = document.createElement('script');
  script.src = 'https://client.crisp.chat/l.js';
  script.async = true;
  script.onerror = function () {
    window.__sentryLootCrispLoadFailed = true;
  };
  document.head.appendChild(script);
})();

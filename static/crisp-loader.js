(function () {
  if (window.__sentryLootCrispLoaded) return;
  window.__sentryLootCrispLoaded = true;
  window.$crisp = window.$crisp || [];
  // Official Web Chat SDK configuration; keep vendor controls readable.
  window.$crisp.push(["config", "color:theme", ["black"]]);
  window.$crisp.push(["config", "color:mode", ["dark"]]);
  window.$crisp.push(["config", "availability:tooltip", [false]]);
  window.$crisp.push(["config", "show:operator:count", [false]]);
  window.$crisp.push(["do", "chat:close"]);
  window.$crisp.push(["do", "chat:hide"]);
  window.CRISP_WEBSITE_ID = '23d64f2d-3d3a-4e73-bca1-4e24795ba125';
  var locale = 'en';
  try { locale = localStorage.getItem('bozor-language') || 'en'; } catch (_) {}
  if (!['en', 'uz', 'ru'].includes(locale)) locale = 'en';
  window.CRISP_RUNTIME_CONFIG = Object.assign({}, window.CRISP_RUNTIME_CONFIG, { locale: locale });

  // Keep the entry point small and predictable; Crisp still handles the conversation.
  var dock = document.createElement('aside');
  dock.id = 'support-dock';
  dock.setAttribute('aria-label', 'Support');
  dock.innerHTML = '<div class="support-hint" hidden><button class="support-hint-dismiss" type="button" aria-label="Close">×</button><strong></strong><p></p><button class="support-hint-open" type="button"></button></div><button class="support-launcher" type="button" aria-label="Open support chat"><img class="support-launcher-logo" src="https://images.gamestorehub.com/site-assets/sentryloot-logo-crest.jpg?v=1" alt=""><svg class="support-launcher-close" viewBox="0 0 24 24" width="24" height="24" fill="none" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg><span class="support-unread" hidden></span></button>';
  document.body.appendChild(dock);
  var hint = dock.querySelector('.support-hint');
  var launcher = dock.querySelector('.support-launcher');
  var badge = dock.querySelector('.support-unread');
  var hintTimer, unread = 0;
  function words() {
    var lang = document.documentElement.lang || locale;
    return lang === 'uz' ? ['Yordam kerakmi?', 'Savolingizni bizga yozing.', 'Chatni ochish', 'Yordam chatini ochish', 'Yopish'] :
      lang === 'ru' ? ['Нужна помощь?', 'Напишите нам свой вопрос.', 'Открыть чат', 'Открыть чат поддержки', 'Закрыть'] :
      ['Need a hand?', 'Send us your question.', 'Open chat', 'Open support chat', 'Close'];
  }
  function syncLabels() {
    var copy = words();
    hint.querySelector('strong').textContent = copy[0];
    hint.querySelector('p').textContent = copy[1];
    hint.querySelector('.support-hint-open').textContent = copy[2];
    launcher.setAttribute('aria-label', document.documentElement.dataset.supportChatOpen ? copy[4] : copy[3]);
    hint.querySelector('.support-hint-dismiss').setAttribute('aria-label', copy[4]);
  }
  function dismissHint() { clearTimeout(hintTimer); hint.hidden = true; }
  function openChat() {
    dismissHint(); unread = 0; badge.hidden = true;
    if (window.__sentryLootCrispLoadFailed) {
      window.open('https://go.crisp.chat/chat/embed/?website_id=' + window.CRISP_WEBSITE_ID, '_blank', 'noopener,noreferrer');
      return;
    }
    document.documentElement.dataset.supportChatOpen = 'true';
    dock.hidden = false;
    launcher.setAttribute('aria-expanded', 'true'); syncLabels();
    window.$crisp.push(['do', 'chat:show']);
    window.$crisp.push(['do', 'chat:open']);
  }
  launcher.setAttribute('aria-expanded', 'false');
  launcher.addEventListener('click', function () {
    if (document.documentElement.dataset.supportChatOpen) window.$crisp.push(['do', 'chat:close']);
    else openChat();
  });
  hint.querySelector('.support-hint-open').addEventListener('click', openChat);
  hint.querySelector('.support-hint-dismiss').addEventListener('click', dismissHint);
  document.addEventListener('keydown', function (event) { if (event.key === 'Escape') dismissHint(); });
  window.$crisp.push(['on', 'chat:closed', function () {
    delete document.documentElement.dataset.supportChatOpen;
    window.$crisp.push(['do', 'chat:hide']); dock.hidden = false;
    launcher.setAttribute('aria-expanded', 'false'); syncLabels();
  }]);
  window.$crisp.push(['on', 'chat:opened', function () {
    dismissHint(); dock.hidden = false;
    document.documentElement.dataset.supportChatOpen = 'true';
    launcher.setAttribute('aria-expanded', 'true'); syncLabels();
  }]);
  window.$crisp.push(['on', 'message:received', function () {
    if (document.documentElement.dataset.supportChatOpen) return;
    unread++; badge.textContent = unread > 9 ? '9+' : String(unread); badge.hidden = false;
  }]);
  window.SentryLootSupport = { open: openChat };
  syncLabels();
  new MutationObserver(syncLabels).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
  var seen = false;
  try { seen = sessionStorage.getItem('sentryloot-support-hint') === '1'; sessionStorage.setItem('sentryloot-support-hint', '1'); } catch (_) {}
  if (!seen) { hint.hidden = false; hintTimer = setTimeout(dismissHint, 5000); }

  var script = document.createElement('script');
  script.src = 'https://client.crisp.chat/l.js';
  script.async = true;
  script.onerror = function () {
    window.__sentryLootCrispLoadFailed = true;
    delete document.documentElement.dataset.supportChatOpen;
    dock.hidden = false;
  };
  document.head.appendChild(script);
})();

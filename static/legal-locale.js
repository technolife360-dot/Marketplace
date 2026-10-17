(function () {
  let selected = 'en';
  try { selected = localStorage.getItem('bozor-language') || 'en'; } catch (_) {}
  if (!['en', 'uz', 'ru'].includes(selected)) selected = 'en';
  document.documentElement.lang = selected;
  const page = location.pathname === '/privacy-policy' ? 'privacy' : 'deletion';
  const copy = window.SENTRYLOOT_LEGAL_TRANSLATIONS?.[page]?.[selected];
  const article = document.querySelector('.legal-copy');
  if (!article) return;
  if (copy) {
    article.innerHTML = `<h1>${copy.title}</h1>${copy.body}`;
    document.title = `${copy.title} — SentryLoot`;
    const description = document.querySelector('meta[name="description"]');
    if (description) description.content = copy.lead;
  }
})();

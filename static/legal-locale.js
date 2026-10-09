(function () {
  var selected = 'en';
  try {
    selected = localStorage.getItem('bozor-language') || 'en';
  } catch (_) {}

  document.querySelectorAll('[data-language-only]').forEach(function (node) {
    node.hidden = node.dataset.languageOnly !== selected;
  });
})();

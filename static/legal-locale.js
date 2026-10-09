(function () {
  var selected = 'en';
  try {
    selected = localStorage.getItem('bozor-language') || 'en';
  } catch (_) {}

  document.querySelectorAll('[data-language-only]').forEach(function (node) {
    node.hidden = node.dataset.languageOnly !== selected;
  });

  document.querySelectorAll('[data-language-summary-container]').forEach(function (node) {
    node.hidden = selected !== 'uz' && selected !== 'ru';
  });

  var summaryHeading = document.querySelector('[data-language-summary-heading]');
  if (summaryHeading) {
    summaryHeading.hidden = selected !== 'uz' && selected !== 'ru';
    summaryHeading.textContent = selected === 'uz' ? 'Qisqacha mazmun' : 'Краткое содержание';
  }
})();

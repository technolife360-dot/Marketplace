const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const data = JSON.parse(fs.readFileSync(path.join(root, 'static/regional-languages.json'), 'utf8'));
const regionalLanguages = ['de', 'fr', 'es', 'it', 'pt', 'nl', 'pl', 'tr', 'ar', 'ms', 'zh'];

// These complete source modules are buyer-facing. Taking the actual third argument
// catches newly added labels and notices, rather than testing a dictionary count.
function englishCalls(file) {
  const source = fs.readFileSync(path.join(root, file), 'utf8');
  const literal = "'(?:\\\\.|[^'\\\\])*'";
  const expression = new RegExp(`\\b(?:t|adminText|tr)\\(\\s*${literal}\\s*,\\s*${literal}\\s*,\\s*(${literal})`, 'g');
  return [...new Set([...source.matchAll(expression)].map(match => vm.runInNewContext(match[1])))];
}

for (const file of ['static/mobile-site.js', 'static/listing-detail.js', 'static/topup-detail.js']) {
  test(`regional languages cover buyer UI calls in ${file}`, () => {
    const phrases = englishCalls(file);
    assert.ok(phrases.length >= 60, 'the source extractor must find the module copy');
    for (const language of regionalLanguages) {
      for (const phrase of phrases) {
        assert.equal(typeof data.messages[language][phrase], 'string', `${language}: ${phrase}`);
        assert.ok(data.messages[language][phrase].trim(), `${language}: ${phrase}`);
      }
    }
  });
}

test('all regional languages share the same non-empty phrase coverage', () => {
  const referenceKeys = Object.keys(data.messages.de).sort();
  assert.deepEqual(Object.keys(data.messages).sort(), [...regionalLanguages].sort());
  for (const language of regionalLanguages) {
    assert.deepEqual(Object.keys(data.messages[language]).sort(), referenceKeys, language);
    assert.equal(data.languages.find(row => row.code === language)?.direction, language === 'ar' ? 'rtl' : 'ltr');
    for (const [english, translated] of Object.entries(data.messages[language])) {
      assert.ok(translated.trim(), `${language}: ${english}`);
      assert.deepEqual(translated.match(/\{\w+\}/g) || [], english.match(/\{\w+\}/g) || [], `${language}: placeholders in ${english}`);
      assert.ok(!/<\/?[a-z][^>]*>/i.test(translated), `${language}: copy must not insert HTML`);
    }
  }
});

test('desktop checkout covers its English-first translation calls', () => {
  const source = fs.readFileSync(path.join(root, 'static/order-process.js'), 'utf8');
  const cart = source.slice(source.indexOf('async function cart('), source.indexOf('function reviewUpload('));
  const phrases = [...cart.matchAll(/\btr\(\s*('(?:\\.|[^'\\])*')/g)].map(match => vm.runInNewContext(match[1]));
  assert.ok(phrases.length >= 18, 'extract the checkout, coupon and disclosure copy');
  for (const language of regionalLanguages) {
    for (const phrase of phrases) assert.ok(data.messages[language][phrase]?.trim(), `${language}: ${phrase}`);
  }
});

test('English fallbacks are not registered as sentence translations', () => {
  // Genuine cognates and shared UI terms are valid translations. Longer identical
  // text would silently hide missing translations behind apparently full coverage.
  const sharedTerms = new Set(['Accounts', 'Notifications', 'Messages', 'Description', 'Subtotal', 'Password', 'Region', 'Server', 'Name', 'Details', 'Status', 'Services', 'Menu', 'Total', 'Message', 'No', 'Home', 'Account', 'Games', 'Game', 'Items', 'Filters', 'Platform', 'Contact', 'Item', 'Service', 'Conversation', 'PROFILE', 'PROFIL', 'CONTACT', 'Image', 'Image 1', 'Image 2', 'Image 3']);
  for (const language of regionalLanguages) {
    for (const [english, translated] of Object.entries(data.messages[language])) {
      if (translated === english) assert.ok(sharedTerms.has(english), `${language}: untranslated ${english}`);
    }
  }
});

test('footer and sign-in copy are covered and View all does not duplicate the UI arrow', () => {
  const phrases = [
    'Blog & guides', 'No reviews yet. Feedback from completed purchases will appear here.',
    'Find game items and services. Review the listing, seller, and game rules before buying.',
    'Live payments are not enabled yet.', 'Buy & Sell', 'Help', 'Start selling',
    'Top Up — coming soon', 'Orders and delivery', 'Payment support', 'Contact us',
    'Message support', 'Trust & policies', 'Seller Policy', 'Prohibited Items',
    'Refund & Dispute Policy', 'All rights reserved.', 'Data deletion',
    'Service status', 'Open support chat',
    'Sign in to your account', 'Sign in to continue.', 'New here?', 'Show password',
    'Hide password', 'SentryLoot account', 'Step into your gaming world',
    'with confidence.', 'Your account, listings, and messages together in one secure place.',
    'Secure sign-in',
  ];
  for (const language of regionalLanguages) {
    for (const phrase of phrases) {
      assert.ok(data.messages[language][phrase]?.trim(), `${language}: ${phrase}`);
      assert.notEqual(data.messages[language][phrase], phrase, `${language}: ${phrase}`);
    }
    assert.ok(!data.messages[language]['View all'].includes('→'), `${language}: the UI supplies the arrow`);
    for (const number of [1, 2, 3]) assert.ok(data.messages[language][`Image ${number}`]?.includes(String(number)));
  }
});

test('purchase validation retains the actual quantity and ID limits', () => {
  const validations = new Map([
    ['Enter a whole number from 1 to 99.', ['1', '99']],
    ['Use numbers only. Player ID: 3–40 digits; server: 1–10 digits.', ['3', '40', '1', '10']],
  ]);
  for (const language of regionalLanguages) {
    for (const [phrase, limits] of validations) {
      assert.deepEqual(data.messages[language][phrase].match(/\d+/g), limits, `${language}: ${phrase}`);
    }
  }
});

test('home, catalogue, cart, account, support and protection notices have real coverage', () => {
  const critical = [
    'Search results', 'All listings', 'Loading listings…', 'Could not load listings.',
    'Try again', 'New listings are on the way', 'Approved products will appear here.',
    'Recommended', 'Price: high to low', 'Fastest delivery', 'Apply filters',
    'Your cart', 'Review your item before continuing.', 'Remove item',
    'Payments are being set up. No money is charged right now.',
    'Profile and account settings.', 'Change password', 'Email verified',
    'Do not include passwords or recovery codes.', 'No support requests yet',
    'Track your request and every reply in one place.', 'Contact support',
    'Fees and payments', 'Order help', 'Refunds and disputes', 'Marketplace policies',
    'Track delivery through your order page. Get help if an issue occurs.',
    'Follow the steps on your order page. Change the login and recovery details after receiving access.',
    'Accounts also cover review of access lost due to the seller. Buyer-caused problems and unrelated publisher actions are excluded. This is a reporting process, with no automatic refund or financial guarantee.',
    'This page could not be loaded. Refresh and try again.',
  ];
  for (const language of regionalLanguages) {
    for (const phrase of critical) {
      assert.ok(data.messages[language][phrase]?.trim(), `${language}: ${phrase}`);
      assert.notEqual(data.messages[language][phrase], phrase, `${language}: English fallback for ${phrase}`);
    }
  }
});

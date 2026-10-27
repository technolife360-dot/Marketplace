const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function share(context = {}) {
  const ctx = {window: {}, URL, URLSearchParams, ...context};
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync('static/desktop-share.js', 'utf8'), ctx);
  return ctx.window.DesktopShare;
}

test('share destinations retain the complete product URL and title without breaking query parameters', () => {
  const url = 'https://gamestorehub.com/listing/offer?q=a%2Bb#photo-2';
  const title = 'PUBG + FC & "Rare" account';
  const links = share().links(url, title);
  const x = new URL(links.x), linkedin = new URL(links.linkedin), whatsapp = new URL(links.whatsapp), email = new URL(links.email);
  assert.equal(x.origin, 'https://twitter.com');
  assert.equal(x.searchParams.get('text'), title);
  assert.equal(x.searchParams.get('url'), url);
  assert.equal(linkedin.origin, 'https://www.linkedin.com');
  assert.equal(linkedin.searchParams.get('url'), url);
  assert.equal(whatsapp.origin, 'https://wa.me');
  assert.equal(whatsapp.searchParams.get('text'), `${title}\n${url}`);
  assert.equal(email.protocol, 'mailto:');
  assert.equal(email.searchParams.get('subject'), title);
  assert.equal(email.searchParams.get('body'), `${title}\n${url}`);
});

test('sharing rejects executable links and URLs containing credentials', () => {
  const menu = share();
  for (const url of ['javascript:alert(1)', 'data:text/html,hello', 'https://name:password@example.com/']) {
    assert.throws(() => menu.links(url, 'Product'));
  }
});

test('phone flow returns to the existing handler without creating a share dialog', () => {
  const menu = share({matchMedia: query => {assert.equal(query, '(min-width:841px)');return {matches: false};}});
  // No document or clipboard exists in this context: desktop UI must not run.
  assert.equal(menu.open({title: 'Offer', url: 'https://gamestorehub.com/listing/offer'}), false);
});

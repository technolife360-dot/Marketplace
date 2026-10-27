const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

// These tests catch hidden content, stale route animations and redundant downloads.
function setup(reduced = false) {
  const state = { scripts: [], animations: 0, cancelled: 0, observersStopped: 0 };
  const media = { matches: reduced, addEventListener(_type, callback) { state.preferenceChanged = callback; } };
  const element = { isConnected: true, style: {} };
  const elements = [element];
  const root = { isConnected: true, querySelector: () => element, querySelectorAll: () => elements };
  const runtime = {
    animate() { state.animations++; return { cancel() { state.cancelled++; } }; },
    inView(elements, callback) { elements.forEach(callback); return () => { state.observersStopped++; }; },
  };
  const window = { matchMedia: () => media };
  const context = { window, document: { documentElement: { dataset: {} }, createElement: () => ({}), head: { appendChild(script) { state.scripts.push(script); } } }, console };
  vm.createContext(context);
  const file = path.join(__dirname, '../static/premium-motion.js');
  vm.runInContext(fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '', context);
  assert.ok(window.PremiumMotion, 'Motion enhancement must register a lifecycle controller');
  return { state, media, element, elements, root, runtime, window, context };
}

test('reduced motion leaves content visible without downloading Motion', async () => {
  const x = setup(true);
  await x.window.PremiumMotion.mount(x.root);
  assert.equal(x.state.scripts.length, 0);
  assert.deepEqual(x.element.style, {});
});

test('a failed Motion download keeps the marketplace usable', async () => {
  const x = setup();
  const pending = x.window.PremiumMotion.mount(x.root);
  x.state.scripts[0].onerror();
  await pending;
  assert.equal(x.state.animations, 0);
  assert.deepEqual(x.element.style, {});
});

test('leaving a route during download cannot animate the abandoned route', async () => {
  const x = setup();
  const pending = x.window.PremiumMotion.mount(x.root);
  x.window.PremiumMotion.stop();
  x.window.Motion = x.runtime;
  x.state.scripts[0].onload();
  await pending;
  assert.equal(x.state.animations, 0);
});

test('enabling reduced motion cancels active animation and viewport listeners', async () => {
  const x = setup();
  x.window.Motion = x.runtime;
  await x.window.PremiumMotion.mount(x.root);
  assert.ok(x.state.animations > 0);
  x.media.matches = true;
  x.state.preferenceChanged();
  assert.ok(x.state.cancelled > 0);
  assert.ok(x.state.observersStopped > 0);
});

test('refreshing new listings does not replay existing elements or download twice', async () => {
  const x = setup();
  const pending = x.window.PremiumMotion.mount(x.root);
  x.window.Motion = x.runtime;
  x.state.scripts[0].onload();
  await pending;
  const animations = x.state.animations;
  await x.window.PremiumMotion.refresh(x.root);
  assert.equal(x.state.animations, animations);
  x.elements.push({ isConnected: true, style: {} });
  await x.window.PremiumMotion.refresh(x.root);
  assert.equal(x.state.animations, animations + 1);
  assert.equal(x.state.scripts.length, 1);
});

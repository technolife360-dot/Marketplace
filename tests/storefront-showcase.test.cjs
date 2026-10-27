const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class Element {
  constructor() {
    this.listeners = new Map(); this.dataset = {}; this.attributes = {}; this.isConnected = true; this.children = [];
    this.style = {setProperty: (name, value) => { this.style[name] = value; }};
    const classes = new Set();
    this.classList = {add:name=>classes.add(name),toggle: (name, on) => on ? classes.add(name) : classes.delete(name), contains: name => classes.has(name)};
  }
  addEventListener(name, callback) { if (!this.listeners.has(name)) this.listeners.set(name, new Set()); this.listeners.get(name).add(callback); }
  removeEventListener(name, callback) { this.listeners.get(name)?.delete(callback); }
  emit(name, event = {}) { [...(this.listeners.get(name) || [])].forEach(callback => callback(event)); }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this.attributes[name]; if(name==='data-game-card')delete this.dataset.gameCard; }
  contains(node) { return node === this || this.children.some(child=>child.contains(node)); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.append(node); }
  replaceChildren(...nodes) { this.children=[...nodes]; }
  matches() { return !!this.keyboardFocus; }
  scrollIntoView() { this.scrolled=true; }
  querySelectorAll(selector) { return this.children.flatMap(child=>[...(selector==='[data-game-card]'&&child.dataset.gameCard!==undefined?[child]:[]),...child.querySelectorAll(selector)]); }
  cloneNode(deep) { const clone=new Element(); clone.dataset={...this.dataset};clone.attributes={...this.attributes};if(deep)clone.children=this.children.map(child=>child.cloneNode(true));return clone; }
}
function setup({reduced = false, delayed = false, gallery = false} = {}) {
  const timers = new Map(), observers = []; let timerId = 0;
  const document = new Element(); document.documentElement = {lang:'en'}; document.hidden = false;
  document.createElement = () => new Element();
  const media = new Element(); media.matches = reduced;
  const toggle = new Element(), previous = new Element(), next = new Element();
  const root = new Element(), current = new Element(), counter = new Element(), stage = new Element();
  const images = [0,1,2].map((_, index) => {
    const image = new Element(); image.complete = index === 0 || !delayed; image.naturalWidth = 1400;
    image.classList.toggle('active', index === 0);
    return image;
  });
  const dots = images.map((_, index) => { const dot = new Element(); dot.dataset.marketSlide = String(index); return dot; });
  const cards = Array.from({length:15}, (_, index) => { const card = new Element(); card.dataset.gameName = 'Game ' + index; card.dataset.gameCard=''; return card; });
  stage.children=[...cards]; root.children=[stage];
  root.querySelector = selector => ({'.game-carousel-stage':stage,'[data-rotation-toggle]':toggle, '[data-game-previous]':previous, '[data-game-next]':next, '[data-game-current]':current, '[data-game-counter]':counter})[selector] || null;
  root.querySelectorAll = selector => selector === '[data-game-card]' ? cards : selector === '[data-market-slide]' ? dots : images;
  root.appendChild = node => { root.created = node; };
  const container = {
    querySelector: () => gallery ? null : root,
    querySelectorAll: () => gallery ? [root] : [],
  };
  const window = {
    matchMedia: () => media,
    setInterval: (callback, ms) => { const id = ++timerId; timers.set(id, {callback, ms}); return id; },
    clearInterval: id => timers.delete(id),
  };
  const context = {window, document, IntersectionObserver:class {
    constructor(callback) {this.callback=callback; observers.push(this);}
    observe() {} disconnect() {this.disconnected=true;}
  }};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('static/storefront-showcase.js','utf8'), context);
  window.StorefrontShowcase.mount(container);
  const flush = async () => {for (let i=0;i<8;i++) await Promise.resolve();};
  return {window, document, media, root, stage, images, dots, cards, toggle, previous, next, current, counter, container, timers, observers, flush,
    tick:async () => { [...timers.values()].forEach(t => t.callback()); await flush(); }};
}

test('hero autoplay advances after eight seconds and updates its actual image and dot', async () => {
  const x = setup();
  assert.equal([...x.timers.values()][0].ms,8000);
  await x.tick();
  assert.equal(x.images[1].classList.contains('active'),true);
  assert.equal(x.images[0].classList.contains('active'),false);
  assert.equal(x.dots[1].attributes['aria-current'],'true');
  assert.equal(x.root.dataset.showcaseIndex,'1');
});
test('hover, focus, background tabs and offscreen content pause autoplay', async () => {
  const x = setup();
  for (const [pause,resume] of [
    [()=>x.root.emit('pointerenter'),()=>x.root.emit('pointerleave')],
    [()=>x.root.emit('focusin'),()=>x.root.emit('focusout',{relatedTarget:null})],
    [()=>{x.document.hidden=true;x.document.emit('visibilitychange');},()=>{x.document.hidden=false;x.document.emit('visibilitychange');}],
    [()=>x.observers[0].callback([{isIntersecting:false}]),()=>x.observers[0].callback([{isIntersecting:true}])],
  ]) {pause(); assert.equal(x.timers.size,0); resume(); assert.equal(x.timers.size,1);}
});
test('explicit pause survives hover and visibility changes until the user resumes', () => {
  const x = setup();
  x.root.emit('keydown',{target:x.root,key:' ',preventDefault(){}}); x.root.emit('pointerenter'); x.root.emit('pointerleave'); x.document.emit('visibilitychange');
  assert.equal(x.timers.size,0);
  x.root.emit('keydown',{target:x.root,key:' ',preventDefault(){}}); assert.equal(x.timers.size,1);
});
test('reduced motion stops autoplay but preserves manual slide navigation', async () => {
  const x = setup({reduced:true});
  assert.equal(x.timers.size,0);
  x.dots[2].emit('click'); await x.flush();
  assert.equal(x.images[2].classList.contains('active'),true);
  x.media.matches=false; x.media.emit('change'); assert.equal(x.timers.size,1);
  x.media.matches=true; x.media.emit('change'); assert.equal(x.timers.size,0);
});
test('route cleanup cancels timers/listeners and stale image loads cannot change the old slide', async () => {
  const x = setup({delayed:true});
  await x.flush(); x.tick();
  x.window.StorefrontShowcase.stop();
  x.images[1].emit('load'); await x.flush();
  assert.equal(x.images[0].classList.contains('active'),true);
  assert.equal(x.images[1].classList.contains('active'),false);
  assert.equal(x.timers.size,0); assert.equal(x.observers[0].disconnected,true);
  assert.equal(x.document.listeners.get('visibilitychange').size,0);
  x.media.emit('change'); assert.equal(x.timers.size,0);
});
test('continuous rail has 15 original games and one identical inaccessible loop copy', () => {
  const x = setup({gallery:true});
  assert.equal(x.timers.size,0,'one CSS track owns motion; no per-card interval');
  const track=x.stage.children[0],original=track.children[0],duplicate=track.children[1];
  assert.equal(original.children.length,15); assert.equal(duplicate.children.length,15);
  assert.equal(duplicate.attributes['aria-hidden'],'true');
  assert.deepEqual(duplicate.children.map(c=>c.dataset.gameName),original.children.map(c=>c.dataset.gameName));
  assert.ok(duplicate.children.every(c=>c.tabIndex===-1&&c.dataset.gameCard===undefined));
  x.root.emit('pointerenter'); x.root.emit('pointerleave');
  assert.equal(x.root.dataset.playing,'true','hover does not stop the continuous rail');
  x.window.StorefrontShowcase.mount(x.container); assert.equal(x.stage.children.length,1);
  x.window.StorefrontShowcase.stop(); assert.equal(x.stage.children.length,15);
});
test('rail pauses only for explicit pause, keyboard reading, hidden tabs or reduced motion', () => {
  const x=setup({gallery:true});
  x.root.emit('keydown',{target:x.root,key:' ',preventDefault(){}});
  x.root.emit('pointerleave'); assert.equal(x.root.dataset.playing,'false');
  x.root.emit('keydown',{target:x.root,key:' ',preventDefault(){}});
  assert.equal(x.root.dataset.playing,'true');
  x.cards[0].keyboardFocus=true;x.root.emit('focusin',{target:x.cards[0]});
  assert.equal(x.root.dataset.keyboard,'true');assert.equal(x.root.dataset.playing,'false');
  assert.equal(x.cards[0].scrolled,true,'focused games must be brought into the static keyboard viewport');
  x.stage.scrollLeft=1800;
  x.root.emit('focusout',{relatedTarget:null});assert.equal(x.root.dataset.playing,'true');
  assert.equal(x.stage.scrollLeft,0,'manual keyboard scrolling must not offset the automatic track');
  x.document.hidden=true;x.document.emit('visibilitychange');assert.equal(x.root.dataset.playing,'false');
  x.document.hidden=false;x.document.emit('visibilitychange');assert.equal(x.root.dataset.playing,'true');
  x.window.StorefrontShowcase.stop();assert.equal(x.root.dataset.playing,'false');
});
test('reduced-motion rail keeps all 15 originals accessible without autoplay', () => {
  const x=setup({gallery:true,reduced:true});
  assert.equal(x.timers.size,0);
  assert.equal(x.root.dataset.playing,'false');
  assert.equal(x.cards.filter(c=>c.tabIndex===0).length,15);
  assert.ok(x.cards.every(c=>c.attributes['aria-hidden']!=='true'));
});

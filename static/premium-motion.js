/* Progressive enhancement: content stays visible when Motion is unavailable. */
window.PremiumMotion = (() => {
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  let download, currentRoot = null, epoch = 0;
  const seen = new WeakSet(), observers = [], animations = [];
  const status = value => { document.documentElement.dataset.motionStatus = value; };

  function runtime() {
    if (window.Motion) return Promise.resolve(window.Motion);
    if (!download) download = new Promise(resolve => {
      const script = document.createElement('script');
      script.src = '/static/vendor/motion-14.7.1.min.js';
      script.async = true;
      script.onload = () => resolve(window.Motion || null);
      script.onerror = () => { status('unavailable'); resolve(null); };
      document.head.appendChild(script);
    });
    return download;
  }

  function stop() {
    epoch++;
    currentRoot = null;
    observers.splice(0).forEach(cleanup => cleanup());
    animations.splice(0).forEach(animation => animation.cancel());
  }

  async function refresh(root = currentRoot) {
    if (!root || !root.isConnected || preference.matches) return;
    const request = epoch;
    const motion = await runtime();
    if (!motion || request !== epoch || !root.isConnected || preference.matches) return;
    status('ready');
    const elements = [...root.querySelectorAll('.home-intro-copy, .home-mobile-games nav > a, .market-product-card .market-card-cover, .home-guide > ol > li')].filter(element => !seen.has(element));
    elements.forEach(element => seen.add(element));
    if (!elements.length) return;
    observers.push(motion.inView(elements, element => {
      if (request !== epoch || preference.matches || !element.isConnected) return;
      animations.push(motion.animate(element, {
        opacity: [0.45, 1], transform: ['translateY(12px)', 'translateY(0px)'],
      }, { duration: 0.46, ease: [0.22, 1, 0.36, 1] }));
    }, { amount: 0.12 }));
  }

  function mount(root) {
    stop();
    if (!root || !root.querySelector('.home-intro, .market-browse-page')) return Promise.resolve();
    currentRoot = root;
    if (preference.matches) { status('reduced'); return Promise.resolve(); }
    return refresh(root);
  }

  preference.addEventListener('change', () => {
    const root = currentRoot;
    stop();
    if (preference.matches) { currentRoot = root; status('reduced'); }
    else if (root?.isConnected) mount(root);
  });
  return { mount, refresh, stop };
})();

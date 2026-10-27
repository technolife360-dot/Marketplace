# Compact Premium Marketplace Implementation Plan

**Goal:** Implement the approved competitive audit with a smaller four-column desktop catalogue, earlier prices, coherent cinematic styling and responsive navigation.

**Architecture:** Keep Python, vanilla JS, existing card data and route/event handlers. Refine the existing premium CSS layer and semantic card markup. Reuse existing artwork and Motion enhancement; no package or infrastructure changes.

**Spec:** User approved all recommendations in `competitive-review/TAQQOSLASH.md` and explicitly requested smaller cards, four in a desktop row. Existing cinematic premium direction remains binding.

## Constraints and review focus

- Preserve compact search/select geometry, native values, sidebar row sizes and drag behavior.
- Four fixed desktop columns, three at smaller desktop/tablet widths, two on phones, one on very narrow screens. Sparse inventory must not stretch to fill the row.
- Keep title, one price, actual delivery, seller, review and favorite data; escape all user content. No invented trust metrics or stock.
- Long Uzbek/Russian titles and large UZS prices must wrap or truncate deliberately, without hiding controls or causing overflow.
- Empty/error review and catalogue states remain truthful and useful. No empty focusable carousel.
- No production data, real financial actions, deployment or new dependencies.

## Tasks

- [ ] Refine `static/app.js` card anatomy: image + favorite, category/title, price/action, facts/delivery, seller. Add image dimensions and preserve escaping, seller links, favorite state and sold-out filtering. Run relevant existing frontend tests.
- [ ] Refine `static/premium-storefront.css`: compact hero, eight fully visible desktop game tiles, four columns at >=1100 px, responsive fallbacks, compact cards with price near title and clear 44 px actions. Compact guide and empty reviews. Update asset cache versions in `static/index.html`.
- [ ] Improve the empty review state in `static/purchase-reviews.js`; verify it does not create a focusable empty rail or rating claims, and populated reviews still escape content and label test feedback.
- [ ] Run full existing build/tests with isolated environment and local database. Inspect rendered desktop, tablet and mobile; test search/category, game filters, favorites, listing details and safe cart navigation. Fix regressions, capture evidence, compare with audit/reference, perform fresh code review.

## Execution decisions

- Continue in the existing dirty workspace to preserve earlier requested implementation and user changes; no reset, automatic commit, merge or deployment.
- No repeated style-selection or approval round: user has selected cinematic premium and now explicitly approved implementing the audit.
- Visual density changes are verified in the browser; no tests that merely mirror CSS constants. A focused empty-review behavior test covers the changed interaction boundary.

# Premium Storefront Implementation Plan

**Goal:** Give SentryLoot a cinematic, premium first impression while preserving existing marketplace flows.

**Architecture:** Keep Python and vanilla JavaScript. Add one deliberately ordered theme layer and a progressively enhanced, locally served Motion controller. Reuse the existing artwork, self-hosted font, route handlers and card data. MagicPath is a separate design exploration, not a React migration.

**Tech Stack:** Python, HTML/CSS, vanilla JS, installed Motion 14.7.1.

## Design

Use charcoal surfaces, warm orange actions, large balanced headings, a cinematic hero, clear listing cards and accessible game shortcuts. Preserve compact search/select geometry, sidebar row sizes/drag handle, account navigation, translations and truthful seller/review states. Do not invent inventory, trust metrics or payment availability. On mobile use a horizontal game rail, readable hero and two-column cards where appropriate.

## Global Constraints

- No production deployment, settings, real payments or production database changes.
- All new UI copy must support English, Uzbek and Russian.
- Respect reduced motion, keyboard navigation, native selects and 44px controls.
- Content must remain visible if Motion fails or is unavailable.

## Review Focus

- Search category popup stays anchored below its field.
- Long listing/seller strings and empty/error states remain readable.
- Route changes cancel stale animations/listeners; no animation hides actionable content.
- Reduced-motion preference changes take effect immediately.
- Existing sidebar, favorite, detail, cart and authentication routes remain usable.

## Tasks

- [x] Inspect baseline desktop/mobile, run existing tests, build a MagicPath concept.
- [x] Add a focused premium CSS layer; refine hero, game navigation, cards and shared surfaces.
- [x] Add a locally served lazy Motion controller with route cleanup and reduced-motion behavior; test those meaningful lifecycle boundaries.
- [x] Run build/full tests and browser QA at desktop, tablet and mobile widths; exercise search, menus, card/detail/cart and auth entry points.
- [x] Review changes against Web Interface Guidelines, inspect screenshots and report verified limits.

## Execution notes

MagicPath project 465849455086829568, component 465849727326515200 built and visually inspected. User chose cinematic premium. Image concept generated and inspected; existing production artwork retained, sample claims in the reference were not copied. New CSS/Motion assets require three explicit WSGI static allowlist entries; new endpoint tests cover MIME types and traversal denial. Initial baseline tests found four missing existing requirements; these were installed only under /tmp/sentryloot-qa-deps. Fresh review found a mobile two-line title height mismatch; fixed with a 2.9em height matching 13px/1.45 typography.

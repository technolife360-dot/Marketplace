# Seller offer creation

`/#seller` opens the five-stage offer form for email-verified, independently approved sellers. `/#seller/dashboard` keeps listings, bulk tools, availability and account operations separate from creation.

1. Choose an active category and a matching game/platform from the versioned seller catalogue. Another game/platform can be entered for private moderation.
2. Enter public details. Attribute fields depend on product type and game. Credentials never belong in the public description.
3. Select up to eight images, remove/reorder them, and choose the cover by placing it first. JPEG/PNG/WebP originals are limited to 15 MB, resized locally and revalidated/re-encoded by the existing authenticated server upload endpoint before R2 storage.
4. Enter MYR prices in ringgit (two decimals), stock and manual delivery time. The payload stores integer sen, not a conversion or relabelling of old UZS prices. Existing listings/orders keep their original currency.
5. Review, edit individual sections, confirm ownership/accuracy and submit for moderation. The seller cannot publish directly.

Draft text and current step are saved in localStorage under the authenticated user ID. Photos are kept in IndexedDB in the same browser. Drafts are not account-synced. Consent checkboxes are deliberately not restored. Storage failures remain visible; files are not silently claimed as saved. Successful submission removes the draft.

No supplier top-up API, live payment configuration or production secrets are changed by this UI. The `top-ups` listing category uses the existing manual currency-delivery flow, separate from the supplier-managed top-up catalogue.

## Seller catalogue snapshot (2026-10-24)

`data/seller-catalog.json` contains 700 distinct catalogue identities: games, platforms and voucher brands. Category counts overlap: accounts 344, items 281, currency 104, gift cards 80, top-ups 187, services 172, digital products 68. These are taxonomy choices, not live inventory or publisher authorization. Existing production game/account approval gates remain in force.

Each category relation retains its provider URL and evidence basis. Eldorado relations came from its public navigation. UniPin titles came from its separate Flash Top-Up and Voucher Purchase product cards. G2G account names were read from public category metadata and included only when that category reported offers; exact sister-category URLs and game activation products came from its official services sitemap. Sitemap evidence does not establish current stock. Failed/blocked G2G category requests were not treated as verified account pages. Region-only aliases, known abbreviated titles and renamed platforms were consolidated. Non-gaming media-account relations and an ambiguous abbreviated identity were excluded; DLC, editions and bundles were excluded from the additional game activation entries.

The snapshot is checked in and loaded once per process by `seller_catalog.py`. Requests never crawl competitors or bulk-seed hundreds of database rows. `/api/seller/catalog` returns lightweight identities and allowed category slugs; only the game used in a listing is persisted on demand. `/api/games` retains its existing database-based behaviour for other screens. New snapshots must preserve existing canonical IDs and aliases and include evidence for every new category relation.

The picker initially renders 48 matches, with Show more and alias-aware search over the full catalogue. Switching category clears an incompatible selection; restored drafts are checked again. Creation, game edits, re-submission/reopening and bulk import use the same server-side compatibility validation. Unknown custom games keep the existing inactive moderation path; they do not automatically enter the public catalogue.

## Catalogue artwork

`data/seller-catalog-images.json` maps each identity to a reviewed image source, content digest and small R2 URL. Raster artwork is re-encoded without metadata into a 96×96 WebP frame, preserving the complete logo/cover and transparency. The maintenance publisher rejects thumbnails over 24 KiB; actual files are substantially smaller. Sources include catalogue icons, official app/game artwork and archived covers. A mod may use explicitly identified parent-game artwork when its own artwork is unavailable; it must never silently borrow an unrelated game's icon. Store search matches require visual/title/publisher review, particularly where several games share similar names.

Run `scripts/publish_catalogue_images.py --source-dir /path/to/reviewed-thumbnails` for validation, then add `--env-file /path/to/ignored-r2-env --apply` to publish. The prepared directory must contain a matching `sources.json` and one 96×96 WebP per catalogue identity. The publisher creates content-addressed keys under `admin-images/catalogue-icons/v1/`, separate from visitor uploads. It writes the complete manifest atomically after all uploads succeed, with resumable checkpoints in the preparation directory. Existing originals are not deleted or overwritten. Images have a one-year immutable cache header and are served directly from the existing R2 custom domain; no image proxy or third-party API runs on storefront requests. Source metadata is retained for maintenance; the public endpoint includes only the small R2 image URL.

Tiles keep a fixed 48px frame (36px on small screens) and a text fallback. Images have no `src` until an IntersectionObserver rooted in the scrolling game grid sees them within 72px of its viewport. Native lazy loading and asynchronous decoding also remain enabled. Selected-product summaries load only their single thumbnail. Errors restore the label fallback without another request or layout shift; the observer disconnects when leaving the form.

Checks: `npm run build`, `node --test tests/frontend.test.cjs tests/offer-wizard.test.cjs`, and Python unittest discovery. Browser QA covers category validation, conditional account fields, shared dropdown selection, image upload/reorder, draft reload and final MYR preview. Production R2/network delivery is separate from isolated local UI/HTTP tests.

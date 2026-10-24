# Seller offer creation

`/#seller` opens the five-stage offer form for email-verified, independently approved sellers. `/#seller/dashboard` keeps listings, bulk tools, availability and account operations separate from creation.

1. Choose an active category and game; another game/platform can be entered for moderation.
2. Enter public details. Attribute fields depend on product type and game. Credentials never belong in the public description.
3. Select up to eight images, remove/reorder them, and choose the cover by placing it first. JPEG/PNG/WebP originals are limited to 15 MB, resized locally and revalidated/re-encoded by the existing authenticated server upload endpoint before R2 storage.
4. Enter MYR prices in ringgit (two decimals), stock and manual delivery time. The payload stores integer sen, not a conversion or relabelling of old UZS prices. Existing listings/orders keep their original currency.
5. Review, edit individual sections, confirm ownership/accuracy and submit for moderation. The seller cannot publish directly.

Draft text and current step are saved in localStorage under the authenticated user ID. Photos are kept in IndexedDB in the same browser. Drafts are not account-synced. Consent checkboxes are deliberately not restored. Storage failures remain visible; files are not silently claimed as saved. Successful submission removes the draft.

No supplier top-up API, live payment configuration or production secrets are changed by this UI. The `top-ups` listing category uses the existing manual currency-delivery flow, separate from the supplier-managed top-up catalogue.

Checks: `npm run build`, `node --test tests/frontend.test.cjs tests/offer-wizard.test.cjs`, and Python unittest discovery. Browser QA covers category validation, conditional account fields, shared dropdown selection, image upload/reorder, draft reload and final MYR preview. Production R2/network delivery is separate from isolated local UI/HTTP tests.

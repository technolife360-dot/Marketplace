# UI conventions requested by the owner

- All select dropdowns must use `select-menu.js` and the `.auth-country-trigger` style: open below the field, match its width, limit list height to 180px, scroll long lists, and search lists over eight options.
- Preserve native select values, FormData, required validation, disabled states and change handlers. Verify keyboard and pointer selection in Chrome.
- Never add duplicate field icons, select arrows or borders.
- Keep form controls 44px high, with 8px between a label and its control and at least 16px between neighbouring fields. Use 18px vertical spacing for stacked fields; preserve compact home/header search geometry and quantity controls.
- Single-line field icons must be absolutely positioned inside their own `.field-control`, vertically centered, with 24px SVGs and 18px artwork. Reserve 46px leading padding so text cannot overlap the icon. Textarea icons align with the first text line.
- Header `.top-actions` SVGs stay 24×24, with actual rendered `use` artwork 18×18.
- Further detail: `../.cursor/rules/compact-select-menus.mdc`.


- Home search must preserve the current production/Vercel appearance. Its category menu must always open directly BELOW `#home-category`, anchored to that field, never above it or elsewhere. Keep a compact scrollable list. If a native menu cannot guarantee this position, use an anchored popup while preserving the exact field appearance and layout. Do not redesign the search when adjusting its icon.

- The sidebar's game tiles were intentionally replaced by account navigation below the divider. Messages, purchases, saved listings, reviews and requests belong there; seller wallet/payout links are role-specific. Keep profile dropdown focused on account status/settings, support and sign-out.
- Personal sidebar links must reuse `.market-sidebar-main` geometry: 40px rows, 14px/500 text, 10px gap, 32×32 icon frames and 24×24 SVGs. Do not introduce separate competing size rules for the two groups.

- The entire desktop `.market-sidebar` must scroll as one region. Keep its row heights fixed; do not create a nested scroll area for `.market-sidebar-account`.

- Close the sidebar by dragging its vertical right divider (`#market-sidebar-handle`) left. The supplied Geist sidebar icon (`#market-sidebar-toggle`) appears in the header only while collapsed and only opens it. Preserve the original brand position; align the icon with the sidebar icon frames. Keep persisted state, keyboard access and unchanged row sizes.

- Do not show Start selling, Seller dashboard or Admin panel in `.market-sidebar`, including for existing sellers and admins. Keep the header Sell Item button as the selling entry point; admin access is separate from public sidebar navigation.

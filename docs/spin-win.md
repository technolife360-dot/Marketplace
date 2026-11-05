# Spin & Win

Customer page: `/#spin-win`. Owner page: `/#admin-spin-win`, linked from the admin console. An authenticated, verified account gets one free result per Asia/Kuala_Lumpur calendar day. Concurrent and retried requests reuse the saved result. A no-prize result also consumes the daily spin.

Large wins appear in the private owner queue with account ID, verified email, award reference, time, test/real mode and fulfilment history. Every active full administrator receives an in-site bell notification; the winner receives a notification too. No external email/SMS is sent automatically. Status progresses from new to contacted, shipped, delivered; it cannot move backwards. Records remain visible after fulfilment.

Vouchers are top-up-only non-withdrawable promotional credit in the existing rewards ledger. Current rewards settings govern expiry (default 180 days) and the checkout redemption cap (default 20%). Supplier USD test checkout now accepts a server-bound rewards quote; legacy Top Up and account checkout behavior is preserved. Existing supplier integration remains test-only; this feature does not activate live payments or delivery.

Physical odds while in stock: iPhone 18 Pro 0.001%, PS5 0.002%, Smart TV 0.002%. Voucher odds: RM0.10 6%, RM0.20 2%, RM0.50 1%, RM1 0.7%, RM2 0.25%, RM5 0.05%. Remaining probability: no prize. Empty stock or insufficient remaining voucher budget removes that outcome and assigns its probability to no prize. Animation has equal segments and does not choose results. The customer probabilities/explanation panels were removed at the owner's request; probabilities remain in the API and admin panel.

Campaigns default to disabled, zero physical stock and zero voucher budget. The owner must verify prize availability and set real inventory/budget before enabling. Limits are lifetime totals for each payment mode, not daily/monthly allowances. Issued awards cannot be undone by lowering limits. Increasing a total replenishes the remaining allocation. Settings updates have version numbers and audit records. Stock, daily results, bonus credit, award records and notifications commit atomically under the existing shared rewards lock. Test/real campaigns and credits are isolated.

Data uses the existing private/RLS-protected platform_config table under spinwin: keys; there is no public winner feed or public email/address exposure. No new schema migration is required. API routes inherit the existing authentication, suspension, email verification, admin MFA and CSRF guards.

Validation: tests/test_spin_win.py and tests/spin-win.test.cjs; existing rewards engine/risk/checkout tests and frontend tests. Preview screenshots in output/spin-win are from an isolated local TEST campaign. DEMO winner is generated fixture data, not an actual customer win. No production campaign has been enabled or deployed.

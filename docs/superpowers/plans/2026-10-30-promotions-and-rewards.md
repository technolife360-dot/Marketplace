# Platform promotions and rewards

Owner approved delivery-confirmed awards, platform-funded benefits, accumulating credits redeemable for accounts or Top Up; then explicitly opted out of further questions and requested implementation.

Implementation choices: 1% account / 0.5% Top Up earn; 20% maximum credit redemption (admin configurable); no coupon+credit stacking by default; 180-day credit validity. Non-withdrawable promotional credit, not seller earnings. Keep real/test balances and campaigns isolated. No automatic conversion of legacy points into purchasing power. Existing live payment and supplier gates remain intact.

Architecture: new `rewards_engine.py` stores private transactional records in existing RLS-protected platform_config; no production schema migration. USD micro-units (1 USD = 1000000) give a common ledger for UZS/MYR purchases. Use only validated cached server FX, snapshot it into 5-minute quotes, and fail closed for benefits when no valid FX exists. Existing gross order items/seller entitlements remain intact; only customer payment total is reduced. Provider settlement must fund any platform subsidy rather than reduce seller earnings. State changes, balances, reservations, campaign usage and reversals must be transactional/idempotent.

## Shared API contract

- `GET /api/rewards`: `{mode,test_only,settings,balance_micro,available_micro,pending_micro,debt_micro,history,display_currency,rates}`; `rates` are units per USD. UI uses Intl to display micro/1000000*rate. History entries have type, amount_micro, created_at, reference/status. User scope only.
- `POST /api/rewards/vouchers/claim` `{code}` → wallet. Voucher is a single-use personal gift/compensation credit, optionally recipient-bound; expired/disabled/wrong-owner rejected.
- `POST /api/rewards/quote` `{kind:'account'|'topup',package_id?,quantity?,coupon_code:'',use_bonus:false}` → `{id,expires_at,mode,test_only,currency,subtotal_minor,fee_minor,gross_total_minor,discount_minor,bonus_minor,total_minor,earn_micro}`. Server reads actual cart or package; browser never provides monetary truth. Promo coupon code separate from old seller-funded coupon.
- `GET /api/admin/rewards`: `{settings,campaigns,summary,mode,test_only}`; summary has issued_micro,spent_micro,pending_micro,liability_micro. Campaigns combine coupons/vouchers.
- `POST /api/admin/rewards/settings`: enabled,account_bps,topup_bps,redemption_bps,stacking,credit_expiry_days. Decimal-free bps.
- `POST /api/admin/rewards/campaigns`: `{code?,kind:'coupon'|'voucher',scope:'account'|'topup'|'both',discount_type:'percent'|'fixed',value,currency:'USD'|'UZS'|'MYR',minimum_minor:0,maximum_discount_minor:0,max_uses:1,per_user_limit:1,expires_at,enabled,recipient_id?:''}`. Percent value is bps; fixed value uses USD/MYR cents or whole UZS. Blank voucher code securely generated. Test/real mode from server provider, never client.
- New checkout optional `rewards_quote_id` is carried through request fingerprint and validation. No quote preserves legacy checkout behavior. User totals sent to checkout must reflect final quoted net total.

## Shared engine integration contract

- `reserve(db,uid,quote_id,kind,source_id,lines,currency,subtotal,fee,core)` called INSIDE existing transaction, before order insert. `lines` is the actual cart dictionary list, or `[{package_id,quantity,price_minor}]` for Top Up; engine validates quote against server context, single consumption, mode, limits/balance, returns full quote with total_minor (gross less platform discount/credit). No network calls inside.
- `sync_order(db,oid,core)` reads source/payment state and confirms/releases/reverses credits inside existing transaction. `sync_topup(db,oid,core)` equivalent. Calling repeatedly is safe. No state writes/commits outside caller transaction.
- `purchase(db,kind,source_id)` returns stored promotion record or None; metadata reports gross/net/benefits for order views/refund amounts. Legacy order rows without metadata keep old behavior.
- Quotes capture expected earnings; available only after completed + verified successful payment. Cancel/expiry restores reserved credit; confirmed refund restores used credit and reverses earnings, retaining any resulting debt. Disputes freeze the earned credit; resolution can restore it.

## Work

- [x] Engine, authorization, ledger, quotes, claims/campaigns, settings and regression tests.
- [x] Marketplace and Top Up checkout/payment/refund/settlement hooks and focused tests.
- [x] Customer/admin UI, bonus checkout controls, exact quote binding and responsive styling.
- [ ] Isolated full tests/build, Chrome synthetic flows, review, authorized push and deployment checks.

Verification: Python full suite ran 366 tests (3 skipped); final focused backend suite passed 28 tests. Final browser/translation/frontend suite passed 142 tests and build completed. Chrome verified actual local API campaign creation/toggling, voucher claim, wallet, account credit/coupon quotes and Top Up credit quotes. Mobile viewport 390×844 had no horizontal overflow; no browser console errors. Final review found no remaining P1/P2 issues. Synthetic QA uses a disposable SQLite database, not production records. Stripe SDK calls are mocked in integration tests with signed webhook fixtures; no live payment or supplier delivery has been exercised.

Do not invent offers/sales, modify real payment records, create live Stripe payments, enable live checkout or supplier delivery. Admin campaign/config changes in browser QA use isolated local DB only.

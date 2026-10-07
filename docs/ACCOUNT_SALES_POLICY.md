# Game account sales policy and launch gate (draft)

This is an operational draft, not legal advice or a promise that account transfers are lawful. A buyer or seller checkbox does not override a publisher's terms, payment-provider rules, or local law.

## Allow-list before any account listing

An account category may be enabled only for a specific game after the operator records:

1. The publisher's current account-transfer rule and a dated review of the official source.
2. Written publisher authorization where the rules are unclear or prohibit transfers.
3. A legal review for every country enabled for buyers, sellers, payment, and payout.
4. A payment-provider approval for the marketplace model, including delayed settlement, refunds, chargebacks, and payouts.
5. A documented moderation and proof-of-ownership process that does not collect publisher, email, social-login, or 2FA passwords.

The production environment must list a game in both `MARKETPLACE_APPROVED_GAME_SLUGS` and `MARKETPLACE_APPROVED_ACCOUNT_GAME_SLUGS`. The account allow-list is separate by design. Do not add games based on competitor listings or seller assurances alone.

## Seller rules

- The seller must pass verified email, identity verification, and administrator seller approval.
- The seller must own the account or have documented authority to transfer it, and must confirm that the publisher permits the transfer.
- Stolen, hacked, compromised, rented, shared, recovery-accessible-by-a-third-party, misrepresented, or unverified-ownership accounts are prohibited.
- The listing must accurately state game, platform, region, account contents, transfer limits, linked-login types, and known recovery or ban risks. Do not publish account identifiers or personal information.
- Keep negotiation and delivery in the marketplace. No off-platform payment, contact diversion, fake reviews, duplicate listings, or false delivery confirmation.
- Never submit a password, OTP, recovery code, or another person's private information as ownership evidence. Until a secure private evidence channel and reviewer process exist, account ownership is only seller-attested and is not independently verified.

## Buyer rules and account handover

- Before checkout, show that the publisher may prohibit the transfer, ban the account, or restore it to a prior owner. The buyer must explicitly acknowledge this risk.
- The listing and its approval are not an endorsement by the publisher and do not guarantee account permanence, continued access, rank, items, or value.
- Delivery secrets must only be shared through the encrypted order-delivery flow; never through public listing text, images, email, or third-party chat.
- Publish a dispute deadline and refund rules only after legal and payment-provider review. Evidence must be kept in-platform; never request passwords, OTPs, or identity documents in dispute messages.

## Moderator checklist

- Verify that the game and account type are currently on the reviewed allow-list.
- Confirm seller identity and seller standing; review the listing for misleading, stolen, hacked, rented, or recovery-risk indicators.
- Check the seller attestation and ensure the description does not expose logins, linked-account details, or personal data.
- Reject or pause if publisher policy is unclear, the listing implies a prohibited transaction, evidence appears fabricated, or ownership cannot be established under the approved process.
- Record the decision and reason in the moderation audit trail. Re-review a game when the publisher changes its terms or when a credible abuse report arrives.

## Launch blockers

- The operator/legal entity and supported countries are not yet finalized.
- No production payment, refund, dispute-settlement, or payout provider is configured.
- A private, access-controlled, retention-limited ownership-evidence workflow has not been implemented. Public product-image uploads are not evidence storage.
- No lawyer-approved account-sale terms, after-sale recovery remedy, dispute window, or refund schedule is published.

Until these items are resolved, live account sales must stay disabled. This policy reduces fraud risk but cannot guarantee that a seller will not deceive a buyer or that a publisher will not enforce its rules.

## Official reference examples

- [EA User Agreement](https://www.ea.com/legal/user-agreement?isLocalized=true)
- [EA SPORTS FC Mobile rules](https://help.ea.com/en/articles/ea-sports-fc/fc-mobile/rules-fc-mobile/)
- [PUBG Mobile account safety notice](https://www.pubgmobile.com/webplat/info/news_version3/35372/57705/57706/57821/57822/57823/m22591/202207/918840.shtml)
- [Uzbekistan Law on Electronic Commerce](https://www.lex.uz/uz/acts/-6213382?ONDATE=25.07.2026)

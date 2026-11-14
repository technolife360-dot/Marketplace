# Gamer showcases

The community lives at `/community`. Marketplace and Top Up keep their existing routes, authentication and payment flows. The marketplace sidebar links to Community.

## Implemented flows

- Discover and Following: real approved posts, game-name pills on Discover, type tabs, pagination and player discovery. All post grids reuse the compact 373.33 × 287.99 px card and shrink on narrow screens.
- Public/owner showcase: cover, shared account avatar/name, handle, bio, follower counts, pinned posts and visitor view.
- Collection: favourites shelf, selectable items and story inspector. Collections are player submissions, not verified game inventories or sale listings.
- Moments and detail: native/Stream video playback, image posts, linked collection items, reactions, private saved folders, sharing and comments. The 900 × 546 px desktop media area has a related-media list alongside it, stacking below on small screens. The bounded related-post API excludes the current author and viewer, prioritizes the same game, and reuses the shared audience/block/suspension checks. The detail back link is removed.
- Creation: moments, collection items and achievements; owned uploads, optional thumbnail, live preview, audience, comments, pins, permission confirmation, draft/publish and editing.
- Profile/settings: profile editing, games, audience, comment permissions, notification preferences and block list.
- Circle: followers, following and a private squad list.
- Notifications: real follow/reaction/comment events, idempotent delivery and mark-as-read.
- Showcase layout: up to twelve posts, drag/drop and keyboard-accessible move buttons.
- Discover publishes new public moments immediately. Verified accounts and the normal permission, upload and rate validation are required. Users can report published posts for staff review.
- The full post editor and profile cover uploads use server-side safety checks with OpenAI GPT-4.1 mini. Captions, media and optional thumbnails are analysed for real violence or graphic injury, nudity or sexual content, dangerous real-world acts and recreational drug content. Flagged posts stay hidden, and uncertain or queued submissions stay private. Staff report, rights and appeal controls are available for support cases.
- Copyright/privacy: rights holders can submit private cases without signing up. Authors can appeal a removal; successful appeals return the post to review. Comments can be reported and removed. Case contacts are restricted to authorized staff.
- Marketplace: verified sellers can attach an owned, active listing from the same game to a moment. The post reads current price, stock and listing availability from the marketplace.
- Shared account menu: home and community use `account-menu.js`/`.css`, the same avatar/name and canonical account routes. Visibility changes refresh account identity after edits in another tab.

There is no second language picker. The community reads the home page's regional preference and account language. New community copy has English, Uzbek and Russian translations; other existing regional translations are used where available, with English fallback. User content is never translated.

## Persistence and security

`community.py`, `community_safety.py` and `community_video.py` own the private community tables and media lifecycle. PostgreSQL RLS is enabled and grants to PUBLIC, anon and authenticated are revoked. Browser clients use the existing application session and CSRF token, never database credentials. Account writes require a verified, non-suspended account and are rate limited. Copyright/privacy requests also accept guests, with same-origin JSON submission checks and an hourly limit.

One central visibility predicate applies to feed/search/saved/detail/media. Drafts, private audiences, follower audiences and reciprocal blocks are enforced on the server. Public JSON excludes account email and private profile preferences. Media must belong to the posting account. Images are decoded/re-encoded before storage; originals and executable formats are not served. MP4s are decoded and normalized with bounded resources.

Media uses the existing private R2 evidence bucket. Access is checked before generating a short-lived signed URL. Local filesystem fallback exists only in development. Production fails closed if R2 is unavailable. Signed media leases last at most five minutes, so a previously issued lease can survive a later privacy change until it expires.

Account deletion removes showcase data and objects. The existing authenticated retention cron also removes unreferenced uploads older than seven days, twenty per run. Referenced drafts, post media and covers remain intact.

## Upload handling

- New composer images use private staged uploads and normalize to WebP.
- New MP4 uploads preserve duration and audio, with stripped metadata and incremental safety checks.
- The former 4 MB / 30-second composer cutoff and 512 MB account ceiling are removed. The legacy small-body endpoint remains for profile images/old clients.
- 20 upload reservations per account/hour prevent automated abuse. Provider and server processing capacity still apply; see the R2 direct upload section below.

Optional Cloudflare Stream supports MP4 uploads up to 200 MB / 180 seconds. Configure `CF_STREAM_ACCOUNT_ID`, `CF_STREAM_API_TOKEN`, `CF_STREAM_SIGNING_KEY_ID` and `CF_STREAM_SIGNING_KEY_PEM` on the server. The signing PEM can be base64 encoded. Reservation requests enforce signed playback, one-hour upload expiry and maximum duration. The current composer reserves `/api/community/uploads` and sends new images and MP4 clips directly to private R2 storage; it does not choose Stream based on account settings. The legacy Stream API and signed playback remain for existing media and integrations. Processing must finish before a post can be submitted. Playback uses locally signed RSA tokens lasting five minutes. Each account may retain at most fifty Stream uploads, in addition to existing short-clip/image quotas. Unreferenced Stream videos are included in retention and erasure.

Automatic safety is implemented in `community_moderation.py`; it is a probabilistic classifier, not a guarantee or copyright matcher. Videos are decoded in bounded windows and sampled at roughly one frame per second, including later windows; audio is not analysed. Brief violations between samples can be missed. Stream videos cannot auto-publish in this initial version: their full media needs an asynchronous scanner, and a poster/caption is never accepted as proof that a video is safe. Do not enable large-video uploads publicly until that scanner exists. No account bans or payment decisions are automated. Staff still handle private reports, rights cases and appeals. Account export includes the user's own community records through the existing reauthenticated export endpoint.

## Deployment order

1. Apply both `supabase/migrations/20261107000000_community.sql` and `supabase/migrations/20261108000000_community_safety.sql` through the normal database migration process.
2. Verify existing R2 private bucket credentials and image/video processing dependencies. Enable Stream only after configuring its account and signing key and completing a real upload/playback check.
3. Run the build, workflow tests and enabled PostgreSQL checks.
4. Deploy the application and assets together. Production startup expects the new private tables to exist.

Do not seed the local design-review accounts into production. The development preview at port 8022 uses a separate database under `/tmp`; its initial images and accounts are review fixtures. Production starts with real empty states until users publish.

## Validation

Earlier full-suite checkpoint: 176 JavaScript tests passed; Python ran 437 tests, with the five opt-in PostgreSQL tests skipped in that SQLite run. Those tests were separately run on disposable PostgreSQL 17. Additional community, media, startup and evidence regressions were run after subsequent edits. The final PostgreSQL run contains six passing tests, including the private-table RLS/grants check.

Browser checks covered desktop 1586×992, mobile 390×844 and 320px width, page navigation, real image upload, draft persistence after reload, publication validation, Follow/Following, game filters, shared select menus, no duplicate language picker, overflow, media loading and browser errors. The last focused community/startup run passed 21 tests. Local R2 configuration was absent; private R2 access/signing was tested with bounded mocks and the real image/video pipeline was exercised locally. The private bucket was not modified. See `design-qa.md` for the visual review.

## Changed files

- `community.py`, `app.py`: feature API, migration wiring, authenticated binary media responses and retention/account-erasure integration.
- `video_evidence.py`: explicit optional gameplay audio preservation; evidence defaults unchanged.
- `static/community.html`, `static/community.js`, `static/community.css`, `static/community-locales.js`: standalone responsive interface and localized copy.
- `static/app.js`, `static/index.html`: Community navigation link and cache version.
- `supabase/migrations/20261107000000_community.sql`: private schema, constraints, indexes and RLS/grants.
- `tests/test_community.py`, `tests/test_community_postgres.py`: HTTP ownership/privacy/media/folder/moderation and PostgreSQL regressions.
- `.github/workflows/ci.yml`, `package.json`: compatibility tests and build checks.
- `.gitignore`: development-only uploads.
- `design-qa.md`, `docs/community.md`: visual review and operational notes.

## Latest scope

Shared identity, moderation, rights cases, country opt-in, Stream processing/signing and stale-review protection have WSGI/unit regressions. Cloudflare Stream credentials were absent in the local preview, so provider calls are mocked in tests; real-account upload and playback remain a deployment check. Local fixtures are never production content.

## Automatic safety operations

Store `OPENAI_API_KEY` only in `~/Desktop/SentryLoot-Secrets/.env` locally and the hosting provider's server-side secret store in production. Never put real keys into the marketplace workspace or Git. Requests use a fixed OpenAI endpoint, structured boolean outputs, a 16-second timeout, bounded private media reads, and `store: false`. Credentials, raw provider errors and user media are never included in audit logs. The audit stores policy version, decision and category codes. The existing publish rate limit bounds external calls; each edit is rechecked, and the browser cannot supply an approval. No additional database migration is required.

Configure the server key and verify billing/rate limits before deployment. The synthetic live API probes returned HTTP 429 with `billing_not_active`; real classification is blocked until the connected OpenAI project activates API billing. Mocked service-contract and real decoding/workflow tests do not establish real-world classifier accuracy. New provider data flow and sampling limits are disclosed in the composer, Safety & rights and English/Uzbek/Russian privacy notices.


### Community albums and R2 direct uploads (2026-11-08)

The composer now has one icon-only, keyboard-accessible media picker. It accepts
several images or one MP4, with per-image removal and an ordered album viewer.
`media_ids` is the authoritative attachment list; `media_id` remains the cover
for existing clients. Every attachment has the post's visibility, ownership and
block checks. Every image is scanned; album edits invalidate staff review tokens.

New composer uploads use `POST /api/community/uploads` (size and type only),
a signed PUT straight to private R2, then `POST /uploads/{id}/complete`.
Production file bytes bypass Vercel's 4.5 MB request boundary. Development alone
uses authenticated 3 MB chunks at `/uploads/{id}/chunk?offset=…` so the same
large-file workflow is testable without cloud credentials. There is no former
4 MB / 30-second composer cutoff. R2's single-PUT service boundary is 5 GiB;
server disk/CPU availability, supported formats, image decoding budgets and
upload-rate protections still apply. Larger objects require multipart ingestion.
Do not describe storage or processing as physically unlimited.

Unpublished originals are staged privately and never served by the media API.
The server validates the declared size, decodes/re-encodes images, or remuxes MP4
streams with faststart and stripped metadata, without truncating duration. It
stores a separate final object, commits metadata, then deletes the staging
object. Thus a replay of a staging PUT cannot change an approved post. Finalize
is idempotent; concurrent processing uses a lease. Expired abandoned staging
objects are cleaned by existing retention and account-erasure workflows.

MP4 safety checks progress in chronological 16-second windows through owner-only
`POST /api/community/media/{id}/check`. The Publish action continues checking
until complete. Each window is sampled at about one frame/second, including
later windows; audio is not analyzed. Cache decisions bind the caption and
policy version to immutable server-owned media. Incomplete checks or provider
failures cannot publish. There is no 30-second analysis truncation for new
uploads. Legacy bounded clips and Stream playback remain readable.

Apply `supabase/migrations/20261108010000_community_albums_uploads.sql` before
deploying this code. The new tables are server-only with RLS and revoked browser
role grants. Existing R2 credentials must have object read/write access to the
private bucket. Bucket CORS permits **PUT only** from `https://gamestorehub.com`
and `https://www.gamestorehub.com`; it grants no public read access. The community
page's CSP permits connect requests only to its configured R2 account endpoint.
All authentication/CSRF checks remain on reservation, completion, local chunks
and safety-check API calls. Provider keys remain outside the repository.

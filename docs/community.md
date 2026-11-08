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
- Moderation: every new post and edit enters a human review queue before publication, including images and clips. Admins can inspect private submission media with explicit review access. Approval includes a content revision token; edits invalidate an open review. Production admin MFA requirements apply.
- Copyright/privacy: rights holders can submit private cases without signing up. Authors can appeal a removal; successful appeals return the post to review. Comments can be reported and removed. Case contacts are restricted to authorized staff.
- Marketplace: verified sellers can attach an owned, active listing from the same game to a moment. The post reads current price, stock and listing availability from the marketplace.
- Shared account menu: home and community use `account-menu.js`/`.css`, the same avatar/name and canonical account routes. Visibility changes refresh account identity after edits in another tab.

There is no second language picker. The community reads the home page's regional preference and account language. New community copy has English, Uzbek and Russian translations; other existing regional translations are used where available, with English fallback. User content is never translated.

## Persistence and security

`community.py`, `community_safety.py` and `community_video.py` own the private community tables and media lifecycle. PostgreSQL RLS is enabled and grants to PUBLIC, anon and authenticated are revoked. Browser clients use the existing application session and CSRF token, never database credentials. Account writes require a verified, non-suspended account and are rate limited. Copyright/privacy requests also accept guests, with same-origin JSON submission checks and an hourly limit.

One central visibility predicate applies to feed/search/saved/detail/media. Drafts, private audiences, follower audiences and reciprocal blocks are enforced on the server. Public JSON excludes account email and private profile preferences. Media must belong to the posting account. Images are decoded/re-encoded before storage; originals and executable formats are not served. MP4s are decoded and normalized with bounded resources.

Media uses the existing private R2 evidence bucket. Access is checked before generating a short-lived signed URL. Local filesystem fallback exists only in development. Production fails closed if R2 is unavailable. Signed media leases last at most five minutes, so a previously issued lease can survive a later privacy change until it expires.

Account deletion removes showcase data and objects. The existing authenticated retention cron also removes unreferenced uploads older than seven days, twenty per run. Referenced drafts, post media and covers remain intact.

## Current upload limits

- Images: JPG, PNG or WebP, 4 MB per upload; normalized to WebP.
- Gameplay clips: MP4, 4 MB and 30 seconds, normalized to H.264/AAC. Audio is preserved for community clips. Existing dispute/evidence videos still strip audio.
- 20 uploads per account/hour; 512 MB per-account stored-media ceiling.

Optional Cloudflare Stream supports MP4 uploads up to 200 MB / 180 seconds. Configure `CF_STREAM_ACCOUNT_ID`, `CF_STREAM_API_TOKEN`, `CF_STREAM_SIGNING_KEY_ID` and `CF_STREAM_SIGNING_KEY_PEM` on the server. The signing PEM can be base64 encoded. Reservation requests enforce signed playback, one-hour upload expiry and maximum duration. Browser uploads use resumable TUS chunks; only a scoped upload URL reaches the browser. Processing must finish before a post can be submitted. Playback uses locally signed RSA tokens lasting five minutes. Each account may retain at most fifty Stream uploads, in addition to existing short-clip/image quotas. Unreferenced Stream videos are included in retention and erasure.

No automatic Content ID matching, content classifier or legal adjudication is claimed. Moderation is a human operation. Staff must review the queue and handle private rights cases. Account export includes the user's own community records through the existing reauthenticated export endpoint.

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

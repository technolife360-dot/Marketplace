# Advisory AI listing review

SentryLoot can use Gemini's hosted API to review a new listing when it enters the moderator queue. The request runs in the server environment, so it continues to work while the developer's Mac is turned off.

## What it checks

The model can flag possible credential or OTP requests, off-platform trading, questionable ownership claims, apparent publisher-rule concerns, and inconsistencies. Its result is a private moderator note. The model cannot approve or reject an ad, ban a seller, decide a dispute, or move money. Existing deterministic checks and human moderation remain active when Gemini is not configured, over quota, or unavailable.

## Data sent

The server sends only the listing's public game/category, title, description, platform, region, and a short allowlist of public game attributes. It excludes seller identity, images, delivery instructions, private evidence, and account/session records. Before sending, the server removes URLs, email addresses, phone-like numbers, and text following password/code labels. Do not put confidential material in public listing fields. Gemini's free tier may use prompts and responses to improve Google's products; use the paid tier and review its current terms before sending any data that needs stronger contractual handling.

## Enable the free-tier integration

1. Create a Gemini API key in Google AI Studio.
2. Add `GEMINI_API_KEY` to the Vercel project's **server-side** Environment Variables for the intended deployment environments. Do not put the key in `static/`, a `VITE_`/`NEXT_PUBLIC_` variable, Git, or a browser request.
3. Optionally set `GEMINI_MODEL`; the default is `gemini-flash-latest`.
4. Redeploy. A listing submitted for moderation triggers one bounded API request. The result appears in the private admin listing queue.

The integration uses the Gemini REST API directly and adds no client SDK dependency. Free quota is controlled by Google's current model/project rate limits and can pause at any time. A missing key or quota/provider failure is recorded as a private unavailable status and does not block a listing from reaching human review. Switching to paid usage later requires changing the Google project/billing or provider key, not rewriting the moderation flow.

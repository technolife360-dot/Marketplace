-- Allow the Facebook provider already implemented by the server-side OAuth flow.
ALTER TABLE public.oauth_identities
  DROP CONSTRAINT IF EXISTS oauth_identities_provider_check;

ALTER TABLE public.oauth_identities
  ADD CONSTRAINT oauth_identities_provider_check
  CHECK (provider IN ('google', 'facebook', 'apple'));

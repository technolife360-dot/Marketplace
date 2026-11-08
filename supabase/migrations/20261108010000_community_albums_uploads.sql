-- Ordered Community albums and private staged R2 uploads.
BEGIN;
ALTER TABLE public.community_media ALTER COLUMN byte_size TYPE BIGINT;
CREATE TABLE IF NOT EXISTS community_post_media (
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
        media_id TEXT NOT NULL REFERENCES community_media(id), position INTEGER NOT NULL CHECK(position>=0),
        PRIMARY KEY(post_id,media_id), UNIQUE(post_id,position));
CREATE INDEX IF NOT EXISTS community_post_media_object ON community_post_media(media_id);
CREATE TABLE IF NOT EXISTS community_uploads (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        object_key TEXT NOT NULL UNIQUE, content_type TEXT NOT NULL, byte_size BIGINT NOT NULL,
        received BIGINT NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'uploading',
        media_id TEXT REFERENCES community_media(id) ON DELETE SET NULL,
        expires_at BIGINT NOT NULL, claim TEXT NOT NULL DEFAULT '', claim_until BIGINT NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS community_media_checks (
        media_id TEXT PRIMARY KEY REFERENCES community_media(id) ON DELETE CASCADE,
        duration REAL NOT NULL, cursor_seconds REAL NOT NULL DEFAULT 0,
        caption_hash TEXT NOT NULL DEFAULT '', policy TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT 'unchecked', categories TEXT NOT NULL DEFAULT '[]', uncertain INTEGER NOT NULL DEFAULT 0,
        claim TEXT NOT NULL DEFAULT '', claim_until BIGINT NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS community_upload_expiry ON community_uploads(expires_at);
ALTER TABLE public.community_post_media ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_post_media FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_uploads ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_uploads FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_media_checks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_media_checks FROM PUBLIC, anon, authenticated;
COMMIT;

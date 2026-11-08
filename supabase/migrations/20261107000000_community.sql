-- Private gamer showcase tables; accessed only through the application server.
BEGIN;
CREATE TABLE IF NOT EXISTS community_profiles (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        handle TEXT NOT NULL UNIQUE, bio TEXT NOT NULL DEFAULT '', cover_id TEXT,
        visibility TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','followers','private')),
        preferences TEXT NOT NULL DEFAULT '{}', layout TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS community_media (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        object_key TEXT NOT NULL UNIQUE, content_type TEXT NOT NULL, byte_size INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS community_posts (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('moment','item','achievement')), title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '', game_slug TEXT NOT NULL REFERENCES games(slug), media_id TEXT REFERENCES community_media(id),
        thumbnail_id TEXT REFERENCES community_media(id), linked_items TEXT NOT NULL DEFAULT '[]',
        audience TEXT NOT NULL DEFAULT 'public' CHECK(audience IN ('public','followers','private')),
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','hidden','deleted')),
        comments_enabled INTEGER NOT NULL DEFAULT 1, pinned INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS community_follows (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,target_id), CHECK(user_id<>target_id));
CREATE TABLE IF NOT EXISTS community_saves (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
        folder TEXT NOT NULL DEFAULT 'Favorites', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,post_id));
CREATE TABLE IF NOT EXISTS community_reactions (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE, PRIMARY KEY(user_id,post_id));
CREATE TABLE IF NOT EXISTS community_comments (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
        body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS community_blocks (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(user_id,target_id), CHECK(user_id<>target_id));
CREATE TABLE IF NOT EXISTS community_events (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        actor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, post_id TEXT REFERENCES community_posts(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS community_reports (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE, reason TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,post_id));
CREATE TABLE IF NOT EXISTS community_squad (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(user_id,target_id), CHECK(user_id<>target_id));
CREATE TABLE IF NOT EXISTS community_folders (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,name));
CREATE INDEX IF NOT EXISTS community_posts_feed ON community_posts(status,created_at DESC,id DESC);
CREATE INDEX IF NOT EXISTS community_posts_owner ON community_posts(user_id,status,created_at DESC);
CREATE INDEX IF NOT EXISTS community_follow_target ON community_follows(target_id,user_id);
CREATE INDEX IF NOT EXISTS community_comments_post ON community_comments(post_id,created_at,id);
CREATE INDEX IF NOT EXISTS community_events_user ON community_events(user_id,created_at DESC);
CREATE INDEX IF NOT EXISTS community_media_owner ON community_media(user_id,created_at);
ALTER TABLE public.community_profiles ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_profiles FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_media ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_media FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_posts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_posts FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_follows ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_follows FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_saves ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_saves FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_reactions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_reactions FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_comments ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_comments FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_blocks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_blocks FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_events FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_reports ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_reports FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_squad ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_squad FROM PUBLIC, anon, authenticated;
ALTER TABLE public.community_folders ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_folders FROM PUBLIC, anon, authenticated;
COMMIT;

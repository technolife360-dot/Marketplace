BEGIN;

CREATE TABLE IF NOT EXISTS community_servers (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

CREATE TABLE IF NOT EXISTS community_channels (
        id TEXT PRIMARY KEY, server_id TEXT NOT NULL REFERENCES community_servers(id) ON DELETE CASCADE,
        name TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0, UNIQUE(server_id, name)
    );

CREATE TABLE IF NOT EXISTS community_server_members (
        server_id TEXT NOT NULL REFERENCES community_servers(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        muted_until TEXT, joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(server_id, user_id)
    );

CREATE TABLE IF NOT EXISTS community_channel_messages (
        id TEXT PRIMARY KEY, channel_id TEXT NOT NULL REFERENCES community_channels(id) ON DELETE CASCADE,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        body TEXT NOT NULL DEFAULT '', reply_id TEXT REFERENCES community_channel_messages(id) ON DELETE SET NULL,
        post_id TEXT REFERENCES community_posts(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0 CHECK(removed IN (0, 1))
    );

CREATE INDEX IF NOT EXISTS community_channels_messages_page ON community_channel_messages(channel_id,created_at DESC,id DESC);

CREATE INDEX IF NOT EXISTS community_channels_messages_author ON community_channel_messages(user_id);

CREATE INDEX IF NOT EXISTS community_servers_members_user ON community_server_members(user_id);

ALTER TABLE public.community_servers ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_servers FROM PUBLIC, anon, authenticated;

ALTER TABLE public.community_channels ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_channels FROM PUBLIC, anon, authenticated;

ALTER TABLE public.community_server_members ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_server_members FROM PUBLIC, anon, authenticated;

ALTER TABLE public.community_channel_messages ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.community_channel_messages FROM PUBLIC, anon, authenticated;

COMMIT;

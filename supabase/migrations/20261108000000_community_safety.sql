-- Discover publication review, private rights cases and Stream uploads.
BEGIN;

CREATE TABLE
        IF NOT EXISTS community_post_state (
                post_id TEXT PRIMARY KEY REFERENCES community_posts (id) ON DELETE CASCADE,
                listing_id TEXT REFERENCES listings (id) ON DELETE SET NULL,
                review_status TEXT NOT NULL DEFAULT 'approved' CHECK (
                        review_status IN ('pending', 'approved', 'rejected', 'draft')
                ),
                review_note TEXT NOT NULL DEFAULT '',
                rights_at TEXT,
                reviewer_id TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE
        IF NOT EXISTS community_cases (
                id TEXT PRIMARY KEY,
                user_id TEXT REFERENCES users (id) ON DELETE SET NULL,
                kind TEXT NOT NULL CHECK (
                        kind IN ('copyright', 'privacy', 'appeal', 'comment')
                ),
                post_id TEXT NOT NULL DEFAULT '',
                comment_id TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                reference TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
                decision TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

CREATE TABLE
        IF NOT EXISTS community_streams (
                media_id TEXT PRIMARY KEY REFERENCES community_media (id) ON DELETE CASCADE,
                remote_id TEXT NOT NULL UNIQUE,
                state TEXT NOT NULL DEFAULT 'uploading',
                duration REAL NOT NULL DEFAULT 0,
                checked_at TEXT
        );

CREATE INDEX IF NOT EXISTS community_review_queue ON community_post_state (review_status, updated_at);

CREATE INDEX IF NOT EXISTS community_case_queue ON community_cases (status, created_at);

ALTER TABLE public.community_post_state ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.community_post_state
FROM
        PUBLIC,
        anon,
        authenticated;

ALTER TABLE public.community_cases ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.community_cases
FROM
        PUBLIC,
        anon,
        authenticated;

ALTER TABLE public.community_streams ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.community_streams
FROM
        PUBLIC,
        anon,
        authenticated;

COMMIT;
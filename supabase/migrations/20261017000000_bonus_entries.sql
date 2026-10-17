BEGIN;

CREATE TABLE IF NOT EXISTS public.bonus_entries (
 id TEXT PRIMARY KEY,
 user_id TEXT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
 source_type TEXT NOT NULL,
 source_id TEXT NOT NULL,
 entry_type TEXT NOT NULL,
 points INTEGER NOT NULL CHECK (points <> 0),
 mode TEXT NOT NULL CHECK (mode IN ('preview', 'real')),
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE (user_id, source_type, source_id, entry_type)
);

CREATE INDEX IF NOT EXISTS idx_bonus_entries_user ON public.bonus_entries(user_id, created_at DESC);
ALTER TABLE public.bonus_entries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.bonus_entries FROM PUBLIC, anon, authenticated;

COMMIT;

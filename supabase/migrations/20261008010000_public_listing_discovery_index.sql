-- Public browse results are limited to live listings with unreserved stock.
-- The matching composite index keeps game-filtered newest-first discovery efficient.
BEGIN;

CREATE INDEX IF NOT EXISTS idx_listings_live_game_newest
  ON public.listings (game_id, created_at DESC)
  WHERE status = 'published' AND stock > reserved;

COMMIT;

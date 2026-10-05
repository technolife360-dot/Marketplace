PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
 display_name TEXT NOT NULL, country TEXT NOT NULL DEFAULT 'UZ', language TEXT NOT NULL DEFAULT 'uz', currency TEXT NOT NULL DEFAULT 'UZS',
 email_verified INTEGER NOT NULL DEFAULT 0, suspended INTEGER NOT NULL DEFAULT 0, accepted_terms_version TEXT NOT NULL DEFAULT '', accepted_terms_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS admin_accounts (user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 csrf TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS oauth_identities (
 provider TEXT NOT NULL CHECK(provider IN ('google','apple')), subject TEXT NOT NULL,
 user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 PRIMARY KEY(provider,subject), UNIQUE(provider,user_id)
);
CREATE TABLE IF NOT EXISTS email_tokens (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 purpose TEXT NOT NULL, expires_at TEXT NOT NULL, consumed_at TEXT
);
CREATE TABLE IF NOT EXISTS seller_profiles (
 user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, shop_name TEXT NOT NULL,
 bio TEXT NOT NULL DEFAULT '', verification_status TEXT NOT NULL DEFAULT 'unverified', selling_enabled INTEGER NOT NULL DEFAULT 1,
 identity_status TEXT NOT NULL DEFAULT 'not_started', identity_provider TEXT NOT NULL DEFAULT '', identity_reference TEXT NOT NULL DEFAULT '',
 identity_verified_at TEXT, identity_consent_at TEXT, identity_consent_version TEXT NOT NULL DEFAULT '', identity_last_event_at TEXT,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS games (id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS categories (id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, product_type TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS listings (
 id TEXT PRIMARY KEY, seller_id TEXT NOT NULL REFERENCES users(id), game_id TEXT NOT NULL REFERENCES games(id), category_id TEXT NOT NULL REFERENCES categories(id),
 title TEXT NOT NULL, description TEXT NOT NULL, product_type TEXT NOT NULL, price_minor INTEGER NOT NULL CHECK(price_minor > 0), currency TEXT NOT NULL DEFAULT 'UZS',
 platform TEXT NOT NULL DEFAULT '', region TEXT NOT NULL DEFAULT '', attributes_json TEXT NOT NULL DEFAULT '{}', delivery_method TEXT NOT NULL DEFAULT 'manual',
 delivery_eta TEXT NOT NULL DEFAULT '24 hours', requirements TEXT NOT NULL DEFAULT '', stock INTEGER NOT NULL DEFAULT 1 CHECK(stock >= 0), reserved INTEGER NOT NULL DEFAULT 0 CHECK(reserved >= 0),
 status TEXT NOT NULL DEFAULT 'draft', moderation_note TEXT NOT NULL DEFAULT '', image_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE VIRTUAL TABLE IF NOT EXISTS listing_search USING fts5(title,description,content='listings',content_rowid='rowid',tokenize='unicode61 remove_diacritics 2');
CREATE TRIGGER IF NOT EXISTS listing_search_ai AFTER INSERT ON listings BEGIN INSERT INTO listing_search(rowid,title,description) VALUES(new.rowid,new.title,new.description); END;
CREATE TRIGGER IF NOT EXISTS listing_search_ad AFTER DELETE ON listings BEGIN INSERT INTO listing_search(listing_search,rowid,title,description) VALUES('delete',old.rowid,old.title,old.description); END;
CREATE TRIGGER IF NOT EXISTS listing_search_au AFTER UPDATE OF title,description ON listings BEGIN INSERT INTO listing_search(listing_search,rowid,title,description) VALUES('delete',old.rowid,old.title,old.description); INSERT INTO listing_search(rowid,title,description) VALUES(new.rowid,new.title,new.description); END;
CREATE TABLE IF NOT EXISTS favorites (user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, listing_id));
CREATE TABLE IF NOT EXISTS carts (user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE, quantity INTEGER NOT NULL CHECK(quantity > 0), updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id, listing_id));
CREATE TABLE IF NOT EXISTS orders (
 id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE, buyer_id TEXT NOT NULL REFERENCES users(id), currency TEXT NOT NULL, subtotal_minor INTEGER NOT NULL,
 commission_minor INTEGER NOT NULL, commission_bps INTEGER NOT NULL DEFAULT 0, total_minor INTEGER NOT NULL, status TEXT NOT NULL, payment_mode TEXT NOT NULL,
 accepted_checkout_terms_version TEXT NOT NULL DEFAULT '', accepted_checkout_terms_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS order_items (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), listing_id TEXT NOT NULL REFERENCES listings(id), seller_id TEXT NOT NULL REFERENCES users(id),
 title TEXT NOT NULL, quantity INTEGER NOT NULL, unit_price_minor INTEGER NOT NULL, commission_minor INTEGER NOT NULL, delivery_method TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_events (id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(id), actor_id TEXT REFERENCES users(id), from_status TEXT, to_status TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS payments (
 id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES orders(id), provider TEXT NOT NULL, provider_reference TEXT UNIQUE,
 amount_minor INTEGER NOT NULL, currency TEXT NOT NULL, status TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ledger_entries (
 id TEXT PRIMARY KEY, order_id TEXT REFERENCES orders(id), user_id TEXT REFERENCES users(id), entry_type TEXT NOT NULL,
 amount_minor INTEGER NOT NULL, currency TEXT NOT NULL, description TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS deliveries (
 id TEXT PRIMARY KEY, order_item_id TEXT NOT NULL UNIQUE REFERENCES order_items(id), seller_id TEXT NOT NULL REFERENCES users(id),
 protected_payload TEXT NOT NULL, submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, buyer_accessed_at TEXT
);
CREATE TABLE IF NOT EXISTS product_requests (
 id TEXT PRIMARY KEY, requester_id TEXT NOT NULL REFERENCES users(id), game_id TEXT NOT NULL REFERENCES games(id), category_id TEXT REFERENCES categories(id),
 title TEXT NOT NULL, description TEXT NOT NULL, budget_minor INTEGER, currency TEXT NOT NULL DEFAULT 'UZS', expires_at TEXT,
 status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS request_responses (
 id TEXT PRIMARY KEY, request_id TEXT NOT NULL REFERENCES product_requests(id), seller_id TEXT NOT NULL REFERENCES users(id), message TEXT NOT NULL,
 listing_id TEXT REFERENCES listings(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS conversations (
 id TEXT PRIMARY KEY, buyer_id TEXT NOT NULL REFERENCES users(id), seller_id TEXT NOT NULL REFERENCES users(id), listing_id TEXT REFERENCES listings(id),
 order_id TEXT REFERENCES orders(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(buyer_id,seller_id,listing_id)
);
CREATE TABLE IF NOT EXISTS messages (
 id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE, sender_id TEXT NOT NULL REFERENCES users(id),
 body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, read_at TEXT
);
CREATE TABLE IF NOT EXISTS notifications (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, kind TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
 href TEXT NOT NULL DEFAULT '/', read_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reviews (
 id TEXT PRIMARY KEY, order_item_id TEXT NOT NULL UNIQUE REFERENCES order_items(id), reviewer_id TEXT NOT NULL REFERENCES users(id), seller_id TEXT NOT NULL REFERENCES users(id),
 rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS reports (
 id TEXT PRIMARY KEY, reporter_id TEXT NOT NULL REFERENCES users(id), listing_id TEXT REFERENCES listings(id), order_id TEXT REFERENCES orders(id),
 reason TEXT NOT NULL, details TEXT NOT NULL, evidence_url TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'open', resolution TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS account_deletion_requests (id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), status TEXT NOT NULL DEFAULT 'pending', reason TEXT NOT NULL DEFAULT '', reviewed_by TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, reviewed_at TEXT);
CREATE TABLE IF NOT EXISTS payout_requests (
 id TEXT PRIMARY KEY, seller_id TEXT NOT NULL REFERENCES users(id), amount_minor INTEGER NOT NULL CHECK(amount_minor > 0), currency TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', admin_id TEXT REFERENCES users(id), note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS platform_config (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS audit_logs (
 id TEXT PRIMARY KEY, actor_id TEXT REFERENCES users(id), action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
 details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS rate_limits (bucket TEXT NOT NULL, subject TEXT NOT NULL, window_start INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(bucket,subject,window_start));
CREATE INDEX IF NOT EXISTS idx_listings_public ON listings(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_listings_game_category ON listings(game_id, category_id, status);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price_minor, status);
CREATE INDEX IF NOT EXISTS idx_listings_seller ON listings(seller_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_buyer ON orders(buyer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_items_seller ON order_items(seller_id, order_id);
CREATE INDEX IF NOT EXISTS idx_events_order ON order_events(order_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS idx_requests_open ON product_requests(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ledger_user ON ledger_entries(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status, created_at DESC);

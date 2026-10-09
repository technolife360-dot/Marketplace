#!/usr/bin/env python3
"""SentryLoot marketplace server with SQLite and Supabase PostgreSQL backends."""
from __future__ import annotations
import hashlib, hmac, html, ipaddress, json, os, re, secrets, sqlite3, time, unicodedata
import io
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http import HTTPStatus
from email.message import Message
from pathlib import Path
from queue import Empty, LifoQueue
from threading import Lock
from urllib.parse import parse_qs, urlparse
from urllib.parse import quote as urlquote
from urllib.request import Request as UrlRequest, urlopen as urlopen_request
from urllib.error import HTTPError as UrlHTTPError, URLError as UrlURLError
from payment_providers import get_provider
import email_service
import identity_service
import oauth_service
from asia_markets import ASIA_COUNTRIES, ASIA_COUNTRY_CURRENCIES, ASIA_CURRENCIES

SUPPORTED_LANGUAGES = frozenset({'en', 'uz', 'ru', 'zh', 'ja', 'ko', 'id', 'ms', 'th', 'vi', 'hi', 'ar', 'tr', 'kk', 'bn'})

ROOT = Path(__file__).resolve().parent
# Small dotenv reader keeps the project dependency-free; real process variables take precedence.
_configured_env_path=os.environ.get('SENTRYLOOT_ENV_FILE','').strip()
_env_candidates=[Path(_configured_env_path).expanduser()] if _configured_env_path else [Path.home()/'Desktop'/'SentryLoot-Secrets'/'.env',ROOT/'.env']
_env_path=next((candidate for candidate in _env_candidates if candidate.is_file()),_env_candidates[0])
for _line in _env_path.read_text().splitlines() if _env_path.is_file() else []:
    _line=_line.strip()
    if _line and not _line.startswith('#') and '=' in _line:
        _key,_value=_line.split('=',1); os.environ.setdefault(_key.strip(),_value.strip().strip('\"').strip("'"))
import delivery_crypto
MODE = os.environ.get('MARKETPLACE_MODE', 'development').lower()
DB_PATH = os.environ.get('DATABASE_PATH', str(ROOT / 'marketplace.sqlite3'))
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
SUPABASE_URL = os.environ.get('SUPABASE_URL', '').strip().rstrip('/')
SUPABASE_SERVICE_ROLE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '').strip()
SUPABASE_LISTING_IMAGES_BUCKET = os.environ.get('SUPABASE_LISTING_IMAGES_BUCKET', 'listing-images').strip()
SUPABASE_ACCOUNT_EVIDENCE_BUCKET = os.environ.get('SUPABASE_ACCOUNT_EVIDENCE_BUCKET', 'account-evidence').strip()
try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

DB_INTEGRITY_ERRORS = (sqlite3.IntegrityError,) + ((psycopg.IntegrityError,) if psycopg else ())
_postgres_pool = None
_postgres_pool_lock = Lock()
SESSION_SECRET = os.environ.get('SESSION_SECRET', '')
if MODE == 'production' and (len(SESSION_SECRET) < 32 or SESSION_SECRET.startswith('replace-with')):
    raise RuntimeError('Set SESSION_SECRET to a unique random value of at least 32 characters in production')
if not SESSION_SECRET:
    SESSION_SECRET = secrets.token_urlsafe(48)
COOKIE_NAME = 'bozorgg_session'
SESSION_DAYS = 7
MAX_BODY = 64 * 1024
MAX_IMAGE_BODY = 5 * 1024 * 1024
ACCOUNT_SELLER_TERMS_VERSION = 'account-seller-v1-2026-10'
ACCOUNT_BUYER_TERMS_VERSION = 'account-buyer-v1-2026-10'

class HttpError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message

def now_iso(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def ident(): return secrets.token_urlsafe(12)

def postgres_placeholders(sql):
    """Convert SQLite qmark placeholders while leaving quoted question marks alone."""
    out=[]; quote=None; i=0
    while i < len(sql):
        ch=sql[i]
        if quote:
            out.append(ch)
            if ch == quote:
                if i + 1 < len(sql) and sql[i + 1] == quote:
                    out.append(sql[i + 1]); i += 1
                else: quote=None
        elif ch in ("'", '"'):
            quote=ch; out.append(ch)
        elif ch == '?': out.append('%s')
        else: out.append(ch)
        i += 1
    return ''.join(out)

class PostgresConnectionPool:
    """Small thread-safe pool to avoid a new Supabase connection per HTTP request."""
    def __init__(self, max_size=1):
        self.max_size=max_size
        self.idle=LifoQueue(maxsize=max_size)
        self.lock=Lock()
        self.total=0

    def _new_connection(self):
        return psycopg.connect(DATABASE_URL, connect_timeout=15, autocommit=True, row_factory=dict_row, prepare_threshold=None)

    def getconn(self):
        while True:
            try:
                conn=self.idle.get_nowait()
            except Empty:
                with self.lock:
                    create=self.total < self.max_size
                    if create: self.total+=1
                if create:
                    try: return self._new_connection()
                    except Exception:
                        with self.lock: self.total-=1
                        raise
                try: conn=self.idle.get(timeout=15)
                except Empty: raise TimeoutError('Database connection pool is busy.')
            if conn.closed:
                self._discard(conn)
                continue
            return conn

    def _discard(self, conn):
        try: conn.close()
        finally:
            with self.lock: self.total=max(0,self.total-1)

    def putconn(self, conn):
        if conn.closed:
            self._discard(conn)
            return
        try:
            if conn.info.transaction_status != psycopg.pq.TransactionStatus.IDLE:
                conn.rollback()
            self.idle.put_nowait(conn)
        except Exception:
            self._discard(conn)

    def close(self):
        while True:
            try: conn=self.idle.get_nowait()
            except Empty: return
            self._discard(conn)


class PostgresConnection:
    """Small DB-API compatibility wrapper for the app's SQLite-style execute calls."""
    def __init__(self, connection, pool=None): self.connection=connection; self.pool=pool
    def execute(self, sql, params=()):
        sql=sql.strip()
        if sql.upper() == 'BEGIN IMMEDIATE': sql='BEGIN'
        ignore=bool(re.match(r'^INSERT\s+OR\s+IGNORE\s+INTO\s+',sql,re.I))
        if ignore: sql=re.sub(r'^INSERT\s+OR\s+IGNORE\s+INTO\s+', 'INSERT INTO ', sql, count=1, flags=re.I)
        sql=postgres_placeholders(sql)
        if ignore: sql += ' ON CONFLICT DO NOTHING'
        return self.connection.execute(sql, params or ())
    def close(self):
        if self.connection is None: return
        conn,self.connection=self.connection,None
        if self.pool: self.pool.putconn(conn)
        else: conn.close()

def connect():
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError('DATABASE_URL is set, but psycopg is missing. Install requirements.txt first.')
        global _postgres_pool
        if _postgres_pool is None:
            with _postgres_pool_lock:
                if _postgres_pool is None: _postgres_pool=PostgresConnectionPool(max_size=1)
        return PostgresConnection(_postgres_pool.getconn(),_postgres_pool)
    db = sqlite3.connect(DB_PATH, timeout=15, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db

def production_marketplace_sales_enabled():
    """Fail closed until business, provider, and publisher-rule gates are satisfied."""
    if MODE != 'production': return True
    if os.environ.get('MARKETPLACE_SALES_ENABLED','').strip().lower() != 'true': return False
    try:
        provider=get_provider(MODE,os.environ.get('PAYMENT_PROVIDER','disabled').strip().lower())
    except Exception:
        return False
    return provider.name not in ('disabled','sandbox')

def approved_game_slugs(variable):
    return {slug.strip().lower() for slug in os.environ.get(variable,'').split(',')
            if re.fullmatch(r'[a-z0-9-]{1,100}',slug.strip().lower())}

def listing_allowed_for_production(db, game_id, product_type):
    if MODE != 'production': return True
    if not production_marketplace_sales_enabled(): return False
    game=db.execute('SELECT slug FROM games WHERE id=?',(game_id,)).fetchone()
    if not game or game['slug'].lower() not in approved_game_slugs('MARKETPLACE_APPROVED_GAME_SLUGS'): return False
    if product_type=='account' and game['slug'].lower() not in approved_game_slugs('MARKETPLACE_APPROVED_ACCOUNT_GAME_SLUGS'):
        return False
    return True

def require_listing_allowed(db, game_id, product_type):
    if not listing_allowed_for_production(db,game_id,product_type):
        raise HttpError(503,'Ishlab chiqarishda savdo hozircha yopiq: operator, to‘lov provayderi va shu o‘yin/tovar turi bo‘yicha yozma ruxsat hamda qoidalar tekshiruvi talab qilinadi.')

def enforce_production_marketplace_gate(db):
    if MODE != 'production': return
    for listing in db.execute("SELECT id,game_id,product_type,seller_account_terms_version FROM listings WHERE status='published'").fetchall():
        if (not listing_allowed_for_production(db,listing['game_id'],listing['product_type'])
                or (listing['product_type']=='account' and listing['seller_account_terms_version']!=ACCOUNT_SELLER_TERMS_VERSION)):
            db.execute("UPDATE listings SET status='paused',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='published'",(listing['id'],))

def public_site_base():
    value=os.environ.get('PUBLIC_BASE_URL','').strip().rstrip('/')
    parsed=urlparse(value)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password:
        value='https://gamestorehub.com' if MODE=='production' else 'http://127.0.0.1:8000'
    return value

def public_sitemap_xml():
    base=public_site_base()
    urls=[base+'/',base+'/top-up',base+'/browse',base+'/blog',base+'/guide',base+'/fees',base+'/policies',base+'/support',base+'/help',base+'/terms',base+'/refunds',base+'/seller-policy',base+'/prohibited-items',base+'/contact',base+'/privacy-policy',base+'/data-deletion']
    db=connect()
    try:
        for listing in db.execute("SELECT id,game_id,product_type FROM listings WHERE status='published' AND stock>reserved ORDER BY updated_at DESC").fetchall():
            if listing_allowed_for_production(db,listing['game_id'],listing['product_type']):
                urls.append(base+'/listing/'+urlquote(str(listing['id']),safe=''))
        for post in db.execute("SELECT slug FROM blog_posts WHERE status='published' ORDER BY published_at DESC").fetchall():
            if re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',str(post['slug'])):
                urls.append(base+'/blog/'+urlquote(str(post['slug']),safe=''))
        for product in db.execute('SELECT game_slug,url_slug FROM topup_packages WHERE enabled=1 ORDER BY game_slug,amount').fetchall():
            if re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',str(product['game_slug'])) and re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',str(product['url_slug'])):
                urls.append(base+'/top-up/'+urlquote(str(product['game_slug']),safe='')+'/'+urlquote(str(product['url_slug']),safe=''))
    finally:
        db.close()
    entries=''.join(f'<url><loc>{html.escape(url)}</loc></url>' for url in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+entries+'</urlset>').encode('utf-8')

def remove_stored_ai_reviews(db):
    rows=db.execute("SELECT id,attributes_json FROM listings WHERE attributes_json LIKE '%_ai_review%'").fetchall()
    for row in rows:
        try: attributes=json.loads(row['attributes_json'] or '{}')
        except (TypeError,ValueError): continue
        if isinstance(attributes,dict) and attributes.pop('_ai_review',None) is not None:
            db.execute('UPDATE listings SET attributes_json=? WHERE id=?',(json.dumps(attributes,ensure_ascii=False),row['id']))

TOPUP_CATALOG = (
    ('pubg-mobile','PUBG Mobile','UC',(60,325,660,1800,3850,8100)),
    ('mobile-legends','Mobile Legends: Bang Bang','Diamonds',(14,42,70,140,284,716,1446)),
    ('free-fire','Free Fire','Diamonds',(100,200,300,310,520,830,1060)),
    ('honor-of-kings','Honor of Kings','Tokens',(16,80,240,400,560,830,1245)),
)

def seed_topup_catalog(db):
    """Seed stable package identities; prices and stock intentionally need admin setup."""
    for game_slug,game_name,currency,amounts in TOPUP_CATALOG:
        for amount in amounts:
            suffix=f'{amount}-{currency.lower()}'
            package_id=f'{game_slug}-{suffix}'
            db.execute('''INSERT INTO topup_packages(id,game_slug,game_name,url_slug,currency,amount)
                VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING''',
                (package_id,game_slug,game_name,suffix,currency,amount))

def topup_public_package(row):
    available=int(row['stock_on_hand'])-int(row['stock_reserved'])>0
    return {'id':row['id'],'game_slug':row['game_slug'],'game_name':row['game_name'],'url_slug':row['url_slug'],
            'currency':row['currency'],'amount':row['amount'],'price_minor':row['price_minor'],
            'coming_soon':bool(row['coming_soon']),'available':available,
            'priced':int(row['price_minor'])>0,'purchasable':False,'payment_ready':False}

def migrate():
    db=connect()
    try:
        if DATABASE_URL:
            required=('account_deletion_requests','account_review_evidence','account_reviews','admin_accounts','audit_logs','blog_posts','carts','categories','conversations','deliveries','email_tokens','favorites','games','ledger_entries','listings','messages','notifications','oauth_identities','order_events','order_items','orders','payments','payout_requests','platform_config','product_requests','rate_limits','reports','request_responses','reviews','seller_profiles','sessions','users')
            missing=[table for table in required if not db.execute('SELECT to_regclass(?) AS name',(f'public.{table}',)).fetchone()['name']]
            if missing:
                raise RuntimeError('Supabase sxemasi topilmadi. Avval supabase/migrations/20261005000000_marketplace_schema.sql migratsiyasini qo‘llang. Yetishmayotgan jadvallar: '+', '.join(missing))
            required_sql=','.join('?' for _ in required)
            security_rows=db.execute(f"SELECT c.relname,c.relrowsecurity,has_table_privilege('anon',c.oid,'select') anon_select,has_table_privilege('authenticated',c.oid,'select') authenticated_select FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ({required_sql})",tuple(required)).fetchall()
            security_issues=[row['relname'] for row in security_rows if not row['relrowsecurity'] or row['anon_select'] or row['authenticated_select']]
            if security_issues:
                raise RuntimeError('Supabase RLS yoki browser-role ruxsatlari xavfsiz emas. Tekshiring: '+', '.join(security_issues))
            db.execute("""CREATE TABLE IF NOT EXISTS topup_packages (
                id TEXT PRIMARY KEY, game_slug TEXT NOT NULL, game_name TEXT NOT NULL,
                url_slug TEXT NOT NULL, currency TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
                price_minor INTEGER NOT NULL DEFAULT 0 CHECK(price_minor>=0), stock_on_hand INTEGER NOT NULL DEFAULT 0 CHECK(stock_on_hand>=0),
                stock_reserved INTEGER NOT NULL DEFAULT 0 CHECK(stock_reserved>=0), enabled INTEGER NOT NULL DEFAULT 1, coming_soon INTEGER NOT NULL DEFAULT 1,
                manual_enabled INTEGER NOT NULL DEFAULT 1, supplier_enabled INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(game_slug,url_slug), CHECK(stock_reserved<=stock_on_hand)
            )""")
            db.execute('ALTER TABLE public.topup_packages ADD COLUMN IF NOT EXISTS coming_soon INTEGER NOT NULL DEFAULT 1')
            db.execute("""CREATE TABLE IF NOT EXISTS topup_orders (
                id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE, buyer_id TEXT NOT NULL REFERENCES users(id),
                package_id TEXT NOT NULL REFERENCES topup_packages(id), player_id TEXT NOT NULL, server_id TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity>0), unit_price_minor INTEGER NOT NULL CHECK(unit_price_minor>0),
                currency TEXT NOT NULL DEFAULT 'UZS', status TEXT NOT NULL DEFAULT 'awaiting_payment',
                payment_reference TEXT NOT NULL DEFAULT '', inventory_quantity INTEGER NOT NULL DEFAULT 0,
                supplier_quantity INTEGER NOT NULL DEFAULT 0, supplier_reference TEXT NOT NULL DEFAULT '',
                fulfillment_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT,
                CHECK(inventory_quantity+supplier_quantity<=quantity)
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS topup_inventory_events (
                id TEXT PRIMARY KEY, package_id TEXT NOT NULL REFERENCES topup_packages(id), actor_id TEXT REFERENCES users(id),
                delta INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            for table in ('topup_packages','topup_orders','topup_inventory_events'):
                db.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
                db.execute(f'REVOKE ALL ON public.{table} FROM anon, authenticated')
            required=required+('topup_packages','topup_orders','topup_inventory_events')
            remove_stored_ai_reviews(db)
            db.execute("ALTER TABLE public.listings ADD COLUMN IF NOT EXISTS seller_account_terms_version TEXT NOT NULL DEFAULT ''")
            db.execute('ALTER TABLE public.listings ADD COLUMN IF NOT EXISTS seller_account_terms_at TEXT')
            db.execute("ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS accepted_account_sale_terms_version TEXT NOT NULL DEFAULT ''")
            db.execute('ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS accepted_account_sale_terms_at TEXT')
            seed_blog_posts(db)
            db.execute("UPDATE seller_profiles SET selling_enabled=0 WHERE verification_status!='verified' OR identity_status!='verified' OR identity_provider!='didit'")
            db.execute("UPDATE listings SET status='paused',updated_at=CURRENT_TIMESTAMP WHERE status='published' AND seller_id NOT IN (SELECT user_id FROM seller_profiles WHERE verification_status='verified' AND selling_enabled=1 AND identity_status='verified' AND identity_provider='didit')")
            db.execute("INSERT INTO platform_config(key,value) VALUES('commission_bps','0'),('completion_window_hours','72'),('terms_version','draft-2026-10') ON CONFLICT(key) DO NOTHING")
            games=[('valorant','Valorant'),('pubg-mobile','PUBG Mobile'),('dota-2','Dota 2'),('counter-strike-2','Counter-Strike 2'),('mobile-legends','Mobile Legends')]
            categories=[('accounts','Gaming accounts','account'),('items','Items & skins','item'),('currency','In-game currency','currency'),('services','Coaching & services','service'),('codes','Gift cards & digital codes','code')]
            for slug,name in games: db.execute('INSERT INTO games(id,slug,name) VALUES(?,?,?) ON CONFLICT(id) DO NOTHING',(slug,slug,name))
            for slug,name,typ in categories: db.execute('INSERT INTO categories(id,slug,name,product_type) VALUES(?,?,?,?) ON CONFLICT(id) DO NOTHING',(slug,slug,name,typ))
            seed_topup_catalog(db)
            enforce_production_marketplace_gate(db)
            return
        db.executescript((ROOT / 'migrations/001_initial.sql').read_text())
        remove_stored_ai_reviews(db)
        db.execute("""CREATE TABLE IF NOT EXISTS account_reviews (
            order_id TEXT PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
            buyer_id TEXT NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'collecting' CHECK(status IN ('collecting','pending','needs_info','approved','refunded')),
            buyer_attested_at TEXT,
            review_note TEXT NOT NULL DEFAULT '',
            reviewed_by TEXT REFERENCES users(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            submitted_at TEXT,
            reviewed_at TEXT
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS account_review_evidence (
            order_id TEXT NOT NULL REFERENCES account_reviews(order_id) ON DELETE CASCADE,
            slot INTEGER NOT NULL CHECK(slot IN (1,2)),
            object_path TEXT NOT NULL UNIQUE,
            uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(order_id,slot)
        )""")
        listing_columns={r['name'] for r in db.execute('PRAGMA table_info(listings)')}
        if 'seller_account_terms_version' not in listing_columns: db.execute("ALTER TABLE listings ADD COLUMN seller_account_terms_version TEXT NOT NULL DEFAULT ''")
        if 'seller_account_terms_at' not in listing_columns: db.execute('ALTER TABLE listings ADD COLUMN seller_account_terms_at TEXT')
        order_columns={r['name'] for r in db.execute('PRAGMA table_info(orders)')}
        if 'accepted_account_sale_terms_version' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN accepted_account_sale_terms_version TEXT NOT NULL DEFAULT ''")
        if 'accepted_account_sale_terms_at' not in order_columns: db.execute('ALTER TABLE orders ADD COLUMN accepted_account_sale_terms_at TEXT')
        oauth_table=db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='oauth_identities'").fetchone()
        if oauth_table and 'facebook' not in oauth_table['sql'].lower():
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('BEGIN')
            try:
                db.execute("CREATE TABLE oauth_identities_new (provider TEXT NOT NULL CHECK(provider IN ('google','facebook','apple')), subject TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(provider,subject), UNIQUE(provider,user_id))")
                db.execute('INSERT INTO oauth_identities_new(provider,subject,user_id,created_at) SELECT provider,subject,user_id,created_at FROM oauth_identities')
                db.execute('DROP TABLE oauth_identities')
                db.execute('ALTER TABLE oauth_identities_new RENAME TO oauth_identities')
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                db.execute('PRAGMA foreign_keys=ON')
                raise
            db.execute('PRAGMA foreign_keys=ON')
        db.execute("""CREATE TABLE IF NOT EXISTS blog_posts (
            id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, category_json TEXT NOT NULL,
            title_json TEXT NOT NULL, summary_json TEXT NOT NULL, body_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
            author_id TEXT REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, published_at TEXT
        )""")
        seed_blog_posts(db)
        seller_columns={r['name'] for r in db.execute('PRAGMA table_info(seller_profiles)')}
        if 'identity_status' not in seller_columns: db.execute("ALTER TABLE seller_profiles ADD COLUMN identity_status TEXT NOT NULL DEFAULT 'not_started'")
        if 'identity_provider' not in seller_columns: db.execute("ALTER TABLE seller_profiles ADD COLUMN identity_provider TEXT NOT NULL DEFAULT ''")
        if 'identity_reference' not in seller_columns: db.execute("ALTER TABLE seller_profiles ADD COLUMN identity_reference TEXT NOT NULL DEFAULT ''")
        if 'identity_verified_at' not in seller_columns: db.execute('ALTER TABLE seller_profiles ADD COLUMN identity_verified_at TEXT')
        if 'identity_consent_at' not in seller_columns: db.execute('ALTER TABLE seller_profiles ADD COLUMN identity_consent_at TEXT')
        if 'identity_consent_version' not in seller_columns: db.execute("ALTER TABLE seller_profiles ADD COLUMN identity_consent_version TEXT NOT NULL DEFAULT ''")
        if 'identity_last_event_at' not in seller_columns: db.execute('ALTER TABLE seller_profiles ADD COLUMN identity_last_event_at TEXT')
        report_columns={r['name'] for r in db.execute('PRAGMA table_info(reports)')}
        if 'evidence_url' not in report_columns: db.execute("ALTER TABLE reports ADD COLUMN evidence_url TEXT NOT NULL DEFAULT ''")
        # Sellers from older local builds did not pass an approval workflow. Keep them
        # closed until an administrator has reviewed and explicitly enabled the profile.
        db.execute("UPDATE seller_profiles SET selling_enabled=0 WHERE verification_status!='verified' OR identity_status!='verified' OR identity_provider!='didit'")
        db.execute("UPDATE listings SET status='paused',updated_at=CURRENT_TIMESTAMP WHERE status='published' AND seller_id NOT IN (SELECT user_id FROM seller_profiles WHERE verification_status='verified' AND selling_enabled=1 AND identity_status='verified' AND identity_provider='didit')")
        db.execute("INSERT INTO listing_search(listing_search) VALUES('rebuild')")
        db.execute("INSERT OR IGNORE INTO platform_config(key,value) VALUES('commission_bps','0')")
        db.execute("INSERT OR IGNORE INTO platform_config(key,value) VALUES('completion_window_hours','72')")
        db.execute("INSERT OR IGNORE INTO platform_config(key,value) VALUES('terms_version','draft-2026-10')")
        games = [('valorant','Valorant'),('pubg-mobile','PUBG Mobile'),('dota-2','Dota 2'),('counter-strike-2','Counter-Strike 2'),('mobile-legends','Mobile Legends')]
        categories = [('accounts','Gaming accounts','account'),('items','Items & skins','item'),('currency','In-game currency','currency'),('services','Coaching & services','service'),('codes','Gift cards & digital codes','code')]
        for slug, name in games: db.execute('INSERT OR IGNORE INTO games(id,slug,name) VALUES(?,?,?)',(slug,slug,name))
        for slug, name, typ in categories: db.execute('INSERT OR IGNORE INTO categories(id,slug,name,product_type) VALUES(?,?,?,?)',(slug,slug,name,typ))
        db.execute("""CREATE TABLE IF NOT EXISTS topup_packages (
            id TEXT PRIMARY KEY, game_slug TEXT NOT NULL, game_name TEXT NOT NULL,
            url_slug TEXT NOT NULL, currency TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
            price_minor INTEGER NOT NULL DEFAULT 0 CHECK(price_minor>=0), stock_on_hand INTEGER NOT NULL DEFAULT 0 CHECK(stock_on_hand>=0),
            stock_reserved INTEGER NOT NULL DEFAULT 0 CHECK(stock_reserved>=0), enabled INTEGER NOT NULL DEFAULT 1, coming_soon INTEGER NOT NULL DEFAULT 1,
            manual_enabled INTEGER NOT NULL DEFAULT 1, supplier_enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(game_slug,url_slug), CHECK(stock_reserved<=stock_on_hand)
        )""")
        topup_columns={r['name'] for r in db.execute('PRAGMA table_info(topup_packages)')}
        if 'coming_soon' not in topup_columns:
            db.execute('ALTER TABLE topup_packages ADD COLUMN coming_soon INTEGER NOT NULL DEFAULT 1')
        db.execute("""CREATE TABLE IF NOT EXISTS topup_orders (
            id TEXT PRIMARY KEY, reference TEXT NOT NULL UNIQUE, buyer_id TEXT NOT NULL REFERENCES users(id),
            package_id TEXT NOT NULL REFERENCES topup_packages(id), player_id TEXT NOT NULL, server_id TEXT NOT NULL DEFAULT '',
            quantity INTEGER NOT NULL DEFAULT 1 CHECK(quantity>0), unit_price_minor INTEGER NOT NULL CHECK(unit_price_minor>0),
            currency TEXT NOT NULL DEFAULT 'UZS', status TEXT NOT NULL DEFAULT 'awaiting_payment',
            payment_reference TEXT NOT NULL DEFAULT '', inventory_quantity INTEGER NOT NULL DEFAULT 0,
            supplier_quantity INTEGER NOT NULL DEFAULT 0, supplier_reference TEXT NOT NULL DEFAULT '',
            fulfillment_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT,
            CHECK(inventory_quantity+supplier_quantity<=quantity)
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS topup_inventory_events (
            id TEXT PRIMARY KEY, package_id TEXT NOT NULL REFERENCES topup_packages(id), actor_id TEXT REFERENCES users(id),
            delta INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )""")
        seed_topup_catalog(db)
        enforce_production_marketplace_gate(db)
    finally:
        db.close()

def validate_blog_post(data):
    result={}
    for field,minimum,maximum in (('category',2,60),('title',5,140),('summary',10,500)):
        values=data.get(field)
        if not isinstance(values,list) or len(values)!=3: raise HttpError(400,f'{field} maydonida o‘zbek, rus va ingliz tilidagi 3 qiymat bo‘lishi kerak.')
        result[field]=[clean_text(v,field,minimum,maximum) for v in values]
    bodies=data.get('body')
    if not isinstance(bodies,list) or len(bodies)!=3: raise HttpError(400,'Maqola matnida 3 til uchun paragraflar bo‘lishi kerak.')
    result['body']=[]
    for language in bodies:
        if not isinstance(language,list) or not 1<=len(language)<=30: raise HttpError(400,'Har bir tilda 1–30 ta paragraf kiriting.')
        result['body'].append([clean_text(p,'Paragraf',10,3000) for p in language])
    return result

def seed_blog_posts(db):
    if db.execute('SELECT 1 FROM blog_posts LIMIT 1').fetchone():
        # Replace only the original built-in article; preserve any administrator-edited copy.
        seeded=db.execute("SELECT id FROM blog_posts WHERE slug='xavfsiz-xarid' AND title_json LIKE ?",('%before buying a game account%',)).fetchone()
        if seeded:
            safe_title=['O‘yin akkauntini sotishdan oldin rasmiy qoidalarni tekshiring','Перед продажей игрового аккаунта проверьте правила издателя','Check publisher rules before transferring a game account']
            safe_summary=['Ayrim noshirlar akkauntni sotish yoki boshqa odamga berishni taqiqlaydi. Avval o‘yin noshirining amaldagi qoidalarini tekshiring.','Некоторые издатели запрещают продажу и передачу игровых аккаунтов. Сначала проверьте действующие правила издателя.','Some publishers prohibit selling or transferring game accounts. Check the publisher’s current rules first.']
            safe_body=[
              ['Akkaunt sizniki bo‘lsa ham, o‘yin qoidalari uni boshqa odamga sotish yoki berishga ruxsat bermasligi mumkin.','EA qoidalari EA hisobini sotish, ulashish yoki boshqa odamga o‘tkazishni taqiqlaydi; FC Mobile qoidalari ham hisob xavfsizligi va uchinchi tomon akkauntlari bo‘yicha cheklov qo‘yadi.','PUBG Mobile rasmiy ogohlantirishi akkaunt savdosini ruxsatsiz deb ataydi va kirish ma’lumotlarini berish xavfini tushuntiradi.','Qoidaga zid akkauntlarni bu marketplace’da e’lon qilmang. Qoidalar va hududiy qonunlar farq qilishi mumkin; tushunarsiz bo‘lsa, noshirga va mahalliy yuristga murojaat qiling.'],
              ['Даже если аккаунт ваш, правила игры могут запрещать его продажу или передачу.','Правила EA запрещают продавать, передавать или совместно использовать аккаунт EA; правила FC Mobile также ограничивают сторонние аккаунты и требуют беречь данные входа.','Официальное предупреждение PUBG Mobile называет торговлю аккаунтами неразрешённой и объясняет риск передачи данных для входа.','Не размещайте на этой площадке аккаунты, передача которых нарушает правила издателя. Требования зависят от игры и страны; при сомнениях обратитесь к издателю и местному юристу.'],
              ['Even if an account is yours, the game’s rules may prohibit selling or transferring it.','EA rules prohibit selling, sharing, or transferring an EA Account; FC Mobile rules also restrict third-party accounts and warn players to protect login details.','PUBG Mobile’s official warning describes account trading as unauthorized and explains the risks of sharing login information.','Do not list accounts when a transfer would violate the publisher’s rules. Rules and local laws vary; ask the publisher and a local lawyer if unsure.']]
            db.execute('UPDATE blog_posts SET category_json=?,title_json=?,summary_json=?,body_json=? WHERE id=?',tuple(json.dumps(x,ensure_ascii=False) for x in (['QOIDALAR','ПРАВИЛА','RULES'],safe_title,safe_summary,safe_body))+(seeded['id'],))
        return
    posts=[
      ('xavfsiz-xarid',
       ['XAVFSIZ XARID','БЕЗОПАСНАЯ ПОКУПКА','SAFE BUYING'],
       ['O‘yin akkauntini sotishdan oldin rasmiy qoidalarni tekshiring','Перед продажей игрового аккаунта проверьте правила издателя','Check publisher rules before transferring a game account'],
       ['Ayrim noshirlar akkauntni sotish yoki boshqa odamga berishni taqiqlaydi. Avval o‘yin noshirining amaldagi qoidalarini tekshiring.','Некоторые издатели запрещают продажу и передачу игровых аккаунтов. Сначала проверьте действующие правила издателя.','Some publishers prohibit selling or transferring game accounts. Check the publisher’s current rules first.'],
       [['Akkaunt sizniki bo‘lsa ham, o‘yin qoidalari uni boshqa odamga sotish yoki berishga ruxsat bermasligi mumkin.','EA qoidalari EA hisobini sotish, ulashish yoki boshqa odamga o‘tkazishni taqiqlaydi; FC Mobile qoidalari ham hisob xavfsizligi va uchinchi tomon akkauntlari bo‘yicha cheklov qo‘yadi.','PUBG Mobile rasmiy ogohlantirishi akkaunt savdosini ruxsatsiz deb ataydi va kirish ma’lumotlarini berish xavfini tushuntiradi.','Qoidaga zid akkauntlarni bu marketplace’da e’lon qilmang. Qoidalar va hududiy qonunlar farq qilishi mumkin; tushunarsiz bo‘lsa, noshirga va mahalliy yuristga murojaat qiling.'],['Даже если аккаунт ваш, правила игры могут запрещать его продажу или передачу.','Правила EA запрещают продавать, передавать или совместно использовать аккаунт EA; правила FC Mobile также ограничивают сторонние аккаунты и требуют беречь данные входа.','Официальное предупреждение PUBG Mobile называет торговлю аккаунтами неразрешённой и объясняет риск передачи данных для входа.','Не размещайте на этой площадке аккаунты, передача которых нарушает правила издателя. Требования зависят от игры и страны; при сомнениях обратитесь к издателю и местному юристу.'],['Even if an account is yours, the game’s rules may prohibit selling or transferring it.','EA rules prohibit selling, sharing, or transferring an EA Account; FC Mobile rules also restrict third-party accounts and warn players to protect login details.','PUBG Mobile’s official warning describes account trading as unauthorized and explains the risks of sharing login information.','Do not list accounts when a transfer would violate the publisher’s rules. Rules and local laws vary; ask the publisher and a local lawyer if unsure.']]),
      ('sotuvchi-qollanma',
       ['SOTUVCHI QO‘LLANMASI','РУКОВОДСТВО ПРОДАВЦА','SELLER GUIDE'],
       ['Aniq va ishonchli e’lon yozish','Как создать понятное объявление','Writing a clear, trustworthy listing'],
       ['Yaxshi sarlavha, to‘liq tavsif va yetkazish shartlari xaridorga to‘g‘ri qaror qilishga yordam beradi.','Хороший заголовок, полное описание и условия доставки помогают покупателю принять решение.','A clear title, complete description, and delivery terms help buyers make an informed decision.'],
       [['Sarlavhada o‘yin, platforma va asosiy xususiyatni yozing.','Narxga nimalar kirishini va hudud cheklovlarini ko‘rsating.','Yetkazish muddatini real belgilang.','Boshqalarning shaxsiy ma’lumotlari yoki ruxsatsiz tasvirlarini joylamang.','Sotishdan oldin email, Didit va moderator tekshiruvi yakunlanishi kerak.'],['Укажите игру, платформу и особенности в заголовке.','Объясните, что входит в цену, и укажите ограничения региона.','Установите реальный срок доставки.','Не размещайте чужие персональные данные без разрешения.','Перед продажей нужны подтверждение почты, Didit и проверка модератора.'],['Put the game, platform, and key features in the title.','Explain what the price includes and list region restrictions.','Set a realistic delivery timeframe.','Do not post someone else’s personal data without permission.','Email, Didit, and moderator checks must finish before selling.']]),
      ('aldovlardan-himoya',
       ['HISOB XAVFSIZLIGI','ЗАЩИТА ОТ МОШЕННИЧЕСТВА','ACCOUNT SAFETY'],
       ['Fishing va soxta yordam xabarlarini tanish','Как распознать фишинг и поддельную поддержку','Spotting phishing and fake support messages'],
       ['Parol, OTP va tiklash havolalarini sotuvchiga yoki begona “yordamchi”ga bermang.','Не передавайте пароль, OTP и ссылки восстановления продавцу или неизвестной «поддержке».','Never give passwords, OTP codes, or reset links to a seller or an unsolicited support agent.'],
       [['Parol va tiklash kodini hech kim bilan bo‘lishmang.','Shubhali havolaga kirmasdan domen nomini tekshiring.','To‘lovni platformadan tashqarida yuborish taklifiga rozi bo‘lmang.','Hisobni faqat rasmiy tiklash oqimi orqali qaytaring.'],['Не сообщайте пароль и коды восстановления.','Проверяйте домен до перехода по подозрительной ссылке.','Не соглашайтесь переводить деньги вне платформы.','Восстанавливайте доступ только официальным способом.'],['Do not share passwords or recovery codes.','Check the domain before opening a suspicious link.','Do not pay outside the marketplace when asked.','Use the official recovery flow to regain access.']])]
    for slug,category,title,summary,body in posts:
        db.execute("INSERT INTO blog_posts(id,slug,category_json,title_json,summary_json,body_json,status,published_at) VALUES(?,?,?,?,?,?,'published',CURRENT_TIMESTAMP)",(ident(),slug,*[json.dumps(x,ensure_ascii=False) for x in (category,title,summary,body)]))

def rowdict(r): return dict(r) if r else None
def create_token(): return secrets.token_urlsafe(32)
def hash_token(raw): return hashlib.sha256(raw.encode()).hexdigest()
def encode_session(raw):
    signature=hmac.new(SESSION_SECRET.encode(),raw.encode(),hashlib.sha256).hexdigest()
    return raw+'.'+signature
def decode_session(value):
    raw,sep,signature=value.rpartition('.')
    if not sep or not raw: return None
    expected=hmac.new(SESSION_SECRET.encode(),raw.encode(),hashlib.sha256).hexdigest()
    return raw if hmac.compare_digest(signature,expected) else None
def password_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310_000)
    return salt.hex() + '$' + digest.hex()
def password_ok(password, stored):
    try:
        salt_hex, _ = stored.split('$',1)
        return hmac.compare_digest(password_hash(password, bytes.fromhex(salt_hex)), stored)
    except Exception: return False

def session_create(db, uid):
    token, csrf = create_token(), create_token()
    db.execute('INSERT INTO sessions(token_hash,user_id,csrf,expires_at) VALUES(?,?,?,?)',(hash_token(token),uid,(csrf), (datetime.now(timezone.utc)+timedelta(days=SESSION_DAYS)).isoformat()))
    return encode_session(token), csrf

def audit(db, actor, action, kind, entity, data=None):
    db.execute('INSERT INTO audit_logs(id,actor_id,action,entity_type,entity_id,details_json) VALUES(?,?,?,?,?,?)',
               (ident(),actor,action,kind,str(entity),json.dumps(data or {},ensure_ascii=False)))

def erase_account_personal_data(db, uid):
    """Remove account credentials and profile data while preserving order records.

    Order and ledger rows remain attached to an anonymized user row so financial
    history and foreign-key integrity are retained. User-authored marketplace
    content and identity verification data are erased; active listings are hidden.
    """
    evidence_paths=[row['object_path'] for row in db.execute('SELECT e.object_path FROM account_review_evidence e JOIN account_reviews ar ON ar.order_id=e.order_id WHERE ar.buyer_id=?',(uid,)).fetchall()]
    if any(not delete_account_evidence_object(object_path) for object_path in evidence_paths):
        raise HttpError(503,'Hisob dalillarini maxfiy Storage’dan o‘chirib bo‘lmadi; o‘chirish qayta uriniladi.')
    db.execute('DELETE FROM account_review_evidence WHERE order_id IN (SELECT order_id FROM account_reviews WHERE buyer_id=?)',(uid,))
    db.execute("UPDATE account_reviews SET review_note='',buyer_attested_at=NULL WHERE buyer_id=?",(uid,))
    db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
    db.execute('DELETE FROM email_tokens WHERE user_id=?',(uid,))
    db.execute('DELETE FROM oauth_identities WHERE user_id=?',(uid,))
    db.execute('DELETE FROM admin_accounts WHERE user_id=?',(uid,))
    db.execute('DELETE FROM favorites WHERE user_id=?',(uid,))
    db.execute('DELETE FROM carts WHERE user_id=?',(uid,))
    db.execute('DELETE FROM notifications WHERE user_id=?',(uid,))
    db.execute('DELETE FROM messages WHERE sender_id=?',(uid,))
    db.execute('DELETE FROM conversations WHERE buyer_id=? OR seller_id=?',(uid,uid))
    db.execute('DELETE FROM request_responses WHERE seller_id=? OR request_id IN (SELECT id FROM product_requests WHERE requester_id=?)',(uid,uid))
    db.execute('DELETE FROM product_requests WHERE requester_id=?',(uid,))
    db.execute('DELETE FROM reviews WHERE reviewer_id=?',(uid,))
    db.execute('DELETE FROM reports WHERE reporter_id=?',(uid,))
    db.execute("UPDATE listings SET status='archived',title='Removed listing',description='',requirements='',moderation_note='',image_url='',attributes_json='{}',stock=0,reserved=0,updated_at=CURRENT_TIMESTAMP WHERE seller_id=?",(uid,))
    db.execute('DELETE FROM seller_profiles WHERE user_id=?',(uid,))
    db.execute('UPDATE ledger_entries SET user_id=NULL WHERE user_id=?',(uid,))
    db.execute("UPDATE order_events SET actor_id=NULL,note='' WHERE actor_id=?",(uid,))
    db.execute("UPDATE audit_logs SET actor_id=NULL,details_json='{}' WHERE actor_id=?",(uid,))
    db.execute("UPDATE account_deletion_requests SET reason='' WHERE user_id=?",(uid,))
    db.execute("UPDATE users SET email=?,password_hash=?,display_name='Deleted user',country='UZ',language='en',currency='UZS',email_verified=0,suspended=1,accepted_terms_version='',accepted_terms_at=NULL WHERE id=?",
               ('deleted-'+uid+'@deleted.invalid',password_hash(secrets.token_urlsafe(48)),uid))

def notify(db, uid, kind, title, body, href='/'):
    if uid: db.execute('INSERT INTO notifications(id,user_id,kind,title,body,href) VALUES(?,?,?,?,?,?)',(ident(),uid,kind,title,body,href))
def email_order_update(db, uid, reference, status, description):
    if not uid or not email_service.is_configured(): return
    user=db.execute('SELECT email,display_name,email_verified,suspended FROM users WHERE id=?',(uid,)).fetchone()
    if not user or not user['email_verified'] or user['suspended']: return
    try: email_service.send_order_update(user['email'],user['display_name'],reference,status,description)
    except Exception as exc: print('transactional email delivery failed:',type(exc).__name__)
def blog_post_view(row):
    post=dict(row)
    for key in ('category_json','title_json','summary_json','body_json'):
        post[key[:-5]]=json.loads(post.pop(key))
    return post
def event(db, oid, actor, old, new, note=''):
    db.execute('INSERT INTO order_events(id,order_id,actor_id,from_status,to_status,note) VALUES(?,?,?,?,?,?)',(ident(),oid,actor,old,new,note))
def user_view(db, uid):
    u = db.execute('SELECT id,email,display_name,country,language,currency,email_verified,suspended,created_at FROM users WHERE id=?',(uid,)).fetchone()
    if not u: return None
    out = dict(u)
    # Admin status is an immutable role marker created by the local bootstrap command.
    out['is_admin'] = db.execute('SELECT 1 FROM admin_accounts WHERE user_id=?',(uid,)).fetchone() is not None
    out['seller'] = rowdict(db.execute("SELECT shop_name,bio,verification_status,selling_enabled,CASE WHEN identity_provider='didit' THEN identity_status ELSE 'not_started' END AS identity_status,identity_provider FROM seller_profiles WHERE user_id=?",(uid,)).fetchone())
    return out

def check_rate(db, bucket, subject, limit=10, period=300):
    now = int(time.time()); start = now - now % period
    # One conditional upsert makes the limit atomic under concurrent requests.
    # SQLite and PostgreSQL both support RETURNING for this statement.
    r = db.execute('''INSERT INTO rate_limits(bucket,subject,window_start,attempts)
        VALUES(?,?,?,1)
        ON CONFLICT(bucket,subject,window_start) DO UPDATE
        SET attempts=rate_limits.attempts+1
        WHERE rate_limits.attempts < ?
        RETURNING attempts''',(bucket,subject,start,limit)).fetchone()
    if not r: raise HttpError(429,'Urinishlar limiti tugadi. Birozdan keyin qayta urinib ko‘ring.')

def is_admin(db, uid): return bool(db.execute('SELECT 1 FROM admin_accounts WHERE user_id=?',(uid,)).fetchone())
def require_user(ctx):
    if not ctx['uid']: raise HttpError(401,'Davom etish uchun tizimga kiring.')
    if ctx['user'] and ctx['user']['suspended']: raise HttpError(403,'Hisobingiz vaqtincha cheklangan.')
    return ctx['uid']
def require_verified(ctx):
    uid=require_user(ctx)
    if not ctx['user']['email_verified']: raise HttpError(403,'Avval elektron pochtangizni tasdiqlang.')
    return uid
def require_admin(ctx):
    uid=require_user(ctx)
    if not is_admin(ctx['db'],uid): raise HttpError(403,'Administrator ruxsati kerak.')
    return uid
def seller_ok(db,uid):
    p=db.execute('SELECT * FROM seller_profiles WHERE user_id=?',(uid,)).fetchone()
    if not p: raise HttpError(403,'Avval sotuvchi profilini yarating.')
    if p['identity_status']!='verified' or p['identity_provider']!='didit':
        raise HttpError(403,'Sotishdan oldin tashqi KYC provayderida pasport va yuz tekshiruvi yakunlanishi kerak. Hujjatlarni bu saytga yuklamang.')
    if p['verification_status']!='verified' or not p['selling_enabled']:
        raise HttpError(403,'Sotuv boshlashdan oldin administrator sotuvchi profilingizni tekshirishi kerak.')
    return p

def settle_seller_escrow(db,oid):
    """Move sandbox-held amounts into withdrawable seller balances after resolution."""
    order=db.execute('SELECT currency FROM orders WHERE id=?',(oid,)).fetchone()
    if not order: raise HttpError(404,'Buyurtma topilmadi.')
    for item in db.execute('SELECT * FROM order_items WHERE order_id=?',(oid,)).fetchall():
        net=item['unit_price_minor']*item['quantity']-item['commission_minor']
        db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,item['seller_id'],'escrow_release',-net,order['currency'],'Buyurtma nizosi/yetkazishi hal qilindi'))
        if net:
            db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,item['seller_id'],'seller_earning',net,order['currency'],'Yetkazilgan buyurtma bo‘yicha sotuvchi daromadi'))
        if item['commission_minor']:
            db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,None,'escrow_fee_release',-item['commission_minor'],order['currency'],'Platforma komissiyasi escrow’dan chiqarildi'))
            db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,None,'platform_commission',item['commission_minor'],order['currency'],'Platforma komissiyasi'))

def refund_sandbox_escrow(db,oid,buyer_id):
    """Record a simulated sandbox refund; it never represents a live cash transfer."""
    order=db.execute('SELECT currency,total_minor FROM orders WHERE id=?',(oid,)).fetchone()
    if not order: raise HttpError(404,'Buyurtma topilmadi.')
    for item in db.execute('SELECT * FROM order_items WHERE order_id=?',(oid,)).fetchall():
        net=item['unit_price_minor']*item['quantity']-item['commission_minor']
        db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,item['seller_id'],'escrow_release',-net,order['currency'],'Sandbox nizosi: sotuvchi escrow’i bekor qilindi'))
        if item['commission_minor']:
            db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,None,'escrow_fee_release',-item['commission_minor'],order['currency'],'Sandbox nizosi: komissiya escrow’i bekor qilindi'))
    db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,buyer_id,'buyer_refund',order['total_minor'],order['currency'],'Sandbox refund simulyatsiyasi; real pul o‘tkazilmagan'))
def clean_text(value, field, min_len=1, max_len=5000):
    if not isinstance(value,str): raise HttpError(400,f'{field}: matn talab qilinadi.')
    value=unicodedata.normalize('NFC', value).strip()
    if len(value)<min_len or len(value)>max_len: raise HttpError(400,f'{field}: uzunligi {min_len}–{max_len} belgi bo‘lishi kerak.')
    return value
def evidence_link(value):
    value=clean_text(value or '','Dalil havolasi',0,1000)
    if not value: return ''
    parsed=urlparse(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        raise HttpError(400,'Dalil havolasi HTTPS bo‘lishi va login/parol saqlamasligi kerak.')
    return value

def evidence_bucket_path(object_path):
    if not SUPABASE_URL.startswith('https://') or not SUPABASE_SERVICE_ROLE_KEY or not re.fullmatch(r'[a-z0-9_-]{1,100}',SUPABASE_ACCOUNT_EVIDENCE_BUCKET):
        raise HttpError(503,'Maxfiy dalil saqlash hali sozlanmagan. Supabase private Storage bucket va server kalitlari kerak.')
    return f"{SUPABASE_URL}/storage/v1/object/{urlquote(SUPABASE_ACCOUNT_EVIDENCE_BUCKET,safe='')}/{urlquote(object_path,safe='/')}"

def require_private_evidence_bucket():
    url=f"{SUPABASE_URL}/storage/v1/bucket/{urlquote(SUPABASE_ACCOUNT_EVIDENCE_BUCKET,safe='')}"
    request=UrlRequest(url,headers={'Authorization':f'Bearer {SUPABASE_SERVICE_ROLE_KEY}','apikey':SUPABASE_SERVICE_ROLE_KEY},method='GET')
    try:
        with urlopen_request(request,timeout=10) as response: info=json.loads(response.read())
    except Exception as exc:
        raise HttpError(503,'Supabase dalil bucketini tekshirib bo‘lmadi; u mavjud, maxfiy va server kaliti to‘g‘ri ekanini tekshiring.') from exc
    if not isinstance(info,dict) or info.get('public') is not False:
        raise HttpError(503,'Akkaunt dalillari uchun bucket public emasligini Supabase’da sozlang.')

def normalize_account_evidence(raw_body,content_type):
    if not raw_body or len(raw_body)>MAX_IMAGE_BODY: raise HttpError(413,'Har bir skrinshot 5 MB dan kichik bo‘lishi kerak.')
    content_type=content_type.split(';',1)[0].strip().lower()
    expected={'image/jpeg':'JPEG','image/png':'PNG','image/webp':'WEBP'}
    if content_type not in expected: raise HttpError(415,'Faqat JPG, PNG yoki WebP skrinshot qabul qilinadi.')
    try:
        import warnings
        from PIL import Image, ImageOps
        Image.MAX_IMAGE_PIXELS=20_000_000
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            image=Image.open(io.BytesIO(raw_body))
            if image.format!=expected[content_type] or getattr(image,'is_animated',False): raise HttpError(415,'Fayl haqiqiy statik rasm bo‘lishi kerak.')
            if image.width*image.height>20_000_000: raise HttpError(413,'Skrinshot o‘lchami juda katta.')
            image.load()
            image=ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
            optimized=io.BytesIO(); image.save(optimized,format='WEBP',quality=82,method=5)
            return optimized.getvalue()
    except HttpError: raise
    except ImportError as exc: raise HttpError(503,'Serverda rasmni xavfsiz qayta ishlash kutubxonasi yo‘q.') from exc
    except Exception as exc: raise HttpError(400,'Skrinshot fayli yaroqsiz yoki buzilgan.') from exc

def upload_account_evidence(uid,oid,slot,raw_body,content_type):
    require_private_evidence_bucket()
    image_bytes=normalize_account_evidence(raw_body,content_type)
    user_key=hashlib.sha256(str(uid).encode()).hexdigest()[:24]
    object_path=f"{user_key}/{secrets.token_hex(24)}.webp"
    request=UrlRequest(evidence_bucket_path(object_path),data=image_bytes,method='POST',headers={'Authorization':f'Bearer {SUPABASE_SERVICE_ROLE_KEY}','apikey':SUPABASE_SERVICE_ROLE_KEY,'Content-Type':'image/webp','Cache-Control':'private, no-store','x-upsert':'false'})
    try:
        with urlopen_request(request,timeout=20) as response:
            if response.status not in (200,201): raise HttpError(502,'Skrinshot maxfiy saqlash joyiga yuklanmadi.')
    except (UrlHTTPError,UrlURLError,TimeoutError) as exc:
        raise HttpError(502,'Skrinshot maxfiy saqlash joyiga yuklanmadi.') from exc
    return object_path

def signed_account_evidence_url(object_path):
    bucket_path=evidence_bucket_path(object_path)
    endpoint=bucket_path.replace('/storage/v1/object/','/storage/v1/object/sign/',1)
    request=UrlRequest(endpoint,data=json.dumps({'expiresIn':300}).encode(),method='POST',headers={'Authorization':f'Bearer {SUPABASE_SERVICE_ROLE_KEY}','apikey':SUPABASE_SERVICE_ROLE_KEY,'Content-Type':'application/json'})
    try:
        with urlopen_request(request,timeout=10) as response: result=json.loads(response.read())
    except Exception as exc:
        raise HttpError(503,'Moderator uchun vaqtinchalik dalil havolasini yaratib bo‘lmadi.') from exc
    signed=result.get('signedURL') if isinstance(result,dict) else None
    if not isinstance(signed,str) or not signed: raise HttpError(503,'Storage vaqtinchalik havolani qaytarmadi.')
    if signed.startswith('/'): return SUPABASE_URL+'/storage/v1'+signed
    if signed.startswith('https://') and signed.startswith(SUPABASE_URL+'/'): return signed
    raise HttpError(503,'Storage xavfsiz dalil havolasini qaytarmadi.')

def delete_account_evidence_object(object_path):
    request=UrlRequest(evidence_bucket_path(object_path),method='DELETE',headers={'Authorization':f'Bearer {SUPABASE_SERVICE_ROLE_KEY}','apikey':SUPABASE_SERVICE_ROLE_KEY})
    try:
        with urlopen_request(request,timeout=10) as response: return response.status in (200,204)
    except UrlHTTPError as exc:
        if exc.code==404: return True
        return False
    except Exception:
        return False
def money(value):
    if isinstance(value,bool) or not isinstance(value,int) or value<=0 or value>1_000_000_000_000: raise HttpError(400,'Narx musbat va ruxsat etilgan chegaradagi butun son bo‘lishi kerak (UZS).')
    return value
LINKED_ACCOUNT_PROVIDERS={'google','facebook','apple','steam','playstation','xbox','other'}
def resolve_game_id(db, value):
    name=clean_text(value,'O‘yin nomi',2,80)
    existing=db.execute('SELECT id FROM games WHERE lower(name)=lower(?) OR lower(id)=lower(?) ORDER BY active DESC,id LIMIT 1',(name,name)).fetchone()
    if existing: return existing['id']
    slug='custom-'+hashlib.sha256(name.casefold().encode('utf-8')).hexdigest()[:24]
    db.execute('INSERT OR IGNORE INTO games(id,slug,name,active) VALUES(?,?,?,0)',(slug,slug,name))
    row=db.execute('SELECT id FROM games WHERE slug=?',(slug,)).fetchone()
    if not row: raise HttpError(409,'Bu o‘yin nomini saqlab bo‘lmadi. Boshqa nom kiriting.')
    return row['id']
def listing_image_urls(value):
    if value is None: return []
    if not isinstance(value,list) or len(value)>6: raise HttpError(400,'Ko‘pi bilan 6 ta rasm qo‘shish mumkin.')
    urls=[]
    for item in value:
        url=clean_text(item,'Rasm manzili',1,500)
        try:
            parsed=urlparse(url)
            host=(parsed.hostname or '').rstrip('.').lower()
            parsed.port
        except ValueError:
            raise HttpError(400,'Rasm manzili to‘g‘ri URL bo‘lishi kerak.')
        if parsed.scheme!='https' or '.' not in host or re.fullmatch(r'[0-9.]+',host) or parsed.username or parsed.password or host in ('localhost','localhost.localdomain') or host.endswith(('.local','.internal','.test')):
            raise HttpError(400,'Rasm manzili xavfsiz HTTPS havola bo‘lishi kerak.')
        try:
            if ipaddress.ip_address(host).is_global is False: raise HttpError(400,'Mahalliy yoki xususiy tarmoqdagi rasm manzili mumkin emas.')
        except ValueError: pass
        if url not in urls: urls.append(url)
    return urls
def linked_account_providers(value):
    if value is None: return []
    if not isinstance(value,list) or len(value)>len(LINKED_ACCOUNT_PROVIDERS) or any(not isinstance(x,str) or x not in LINKED_ACCOUNT_PROVIDERS for x in value):
        raise HttpError(400,'Bog‘langan hisob turi noto‘g‘ri.')
    return sorted(set(value))
def parse_json(body):
    try: return json.loads(body or b'{}')
    except Exception: raise HttpError(400,'JSON so‘rovi noto‘g‘ri.')

def listing_detail(db, lid, viewer=None):
    r=db.execute("""SELECT l.id,l.seller_id,l.game_id,l.category_id,l.title,l.description,l.product_type,l.price_minor,l.currency,l.platform,l.region,l.attributes_json,l.delivery_method,l.delivery_eta,l.requirements,l.stock,l.reserved,l.status,l.moderation_note,l.image_url,l.created_at,l.updated_at,g.name game_name,g.slug game_slug,c.name category_name,s.shop_name seller_name,s.verification_status,CASE WHEN s.identity_provider='didit' AND s.identity_status='verified' THEN 1 ELSE 0 END AS identity_verified,
      (SELECT COUNT(*) FROM reviews rv WHERE rv.seller_id=l.seller_id) review_count,(SELECT AVG(rating) FROM reviews rv WHERE rv.seller_id=l.seller_id) seller_rating
      FROM listings l JOIN games g ON g.id=l.game_id JOIN categories c ON c.id=l.category_id LEFT JOIN seller_profiles s ON s.user_id=l.seller_id WHERE l.id=?""",(lid,)).fetchone()
    if not r: return None
    out=dict(r); out['available']=max(0,out['stock']-out['reserved']); out['attributes']=json.loads(out.pop('attributes_json') or '{}')
    if viewer and (out['seller_id']==viewer or is_admin(db,viewer)):
        out['marketplace_visible']=bool(out['status']=='published' and out['available']>0
                                        and listing_allowed_for_production(db,out['game_id'],out['product_type']))
    # Risk signals are moderation metadata, never part of the public listing payload.
    risk_flags=out['attributes'].pop('_risk_flags',[])
    out['attributes'].pop('_ai_review',None)
    if viewer and is_admin(db,viewer):
        out['risk_flags']=risk_flags
    out['is_favorite']=bool(viewer and db.execute('SELECT 1 FROM favorites WHERE user_id=? AND listing_id=?',(viewer,lid)).fetchone())
    return out

def listing_risk_flags(db, seller_id, game_id, product_type, title, description):
    """Deterministic review signals. These flag listings for a human; they do not accuse or auto-ban."""
    flags=[]
    text=f'{title}\n{description}'
    if re.search(r'(?i)(?:https?://|www\.|t\.me/|telegram|whatsapp|discord\.gg|instagram\.com|pay\s+me\s+direct|outside\s+(?:the\s+)?platform)',text):
        flags.append('off_platform_contact_or_payment')
    if re.search(r'(?i)\b(?:password|passcode|otp|2fa|backup\s+code|recovery\s+code)\s*[:=]',text):
        flags.append('possible_credential_or_code')
    normalize_title=lambda value: re.sub(r'[^a-z0-9]+',' ',unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().lower()).strip()
    normalized=normalize_title(title)
    if normalized:
        prior_titles=db.execute("SELECT title FROM listings WHERE seller_id=? AND game_id=? AND status IN ('draft','pending_review','published','paused') ORDER BY created_at DESC LIMIT 50",(seller_id,game_id)).fetchall()
        if any(normalize_title(row['title'])==normalized for row in prior_titles): flags.append('possible_duplicate_listing')
    if product_type=='account':
        account_count=db.execute("SELECT COUNT(*) n FROM listings WHERE seller_id=? AND product_type='account'",(seller_id,)).fetchone()['n']
        if account_count>=10: flags.append('high_account_listing_volume')
    return sorted(set(flags))

def seo_listing_html(listing_id):
    db=connect()
    try:
        item=listing_detail(db,listing_id)
        if (not item or item['status']!='published'
                or not listing_allowed_for_production(db,item['game_id'],item['product_type'])):
            return None
    finally:
        db.close()
    template=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
    base=public_site_base()
    canonical=base+'/listing/'+urlquote(str(item['id']),safe='')
    title=f"{item['title']} | {item['game_name']} | SentryLoot"
    description=re.sub(r'\s+',' ',str(item['description'] or '')).strip()[:260]
    image=str(item['image_url'] or '')
    replacements={
        'SentryLoot — Game Marketplace':html.escape(title,quote=True),
        'A marketplace for permitted game items and digital services. Marketplace sales are currently restricted to approved games and products.':html.escape(description,quote=True),
        'https://gamestorehub.com/':html.escape(canonical,quote=True),
        'https://gamestorehub.com/static/assets/sentryloot-logo-full.jpg':html.escape(image or base+'/static/assets/sentryloot-logo-full.jpg',quote=True),
        'SentryLoot GameStore logo':html.escape(f"{item['game_name']} listing image" if image else 'SentryLoot GameStore logo',quote=True),
    }
    for old,new in replacements.items(): template=template.replace(old,new)
    return template.encode('utf-8')

def seo_page_html(path, slug=None):
    """Return crawlable metadata/content for public SPA routes."""
    base=public_site_base(); template=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
    title_map={
        '/top-up':('Game currency top ups','Browse PUBG Mobile, Mobile Legends, Free Fire, and Honor of Kings top-up packages on SentryLoot.'),
        '/help':('SentryLoot Help Center','Find answers to payment, order, refund, and dispute questions.'),
        '/browse':('Game marketplace listings','Browse approved game items and services on SentryLoot.'),
        '/guide':('Buying and safety guide','Learn how to use SentryLoot safely and review marketplace rules.'),
        '/fees':('Marketplace fees and payments','Current payment and fee information for SentryLoot.'),
        '/policies':('SentryLoot marketplace policies','Marketplace, publisher, and account-transfer policies.'),
        '/support':('Crisp Support and FAQ','Help with payments, orders, refunds, and disputes.'),
        '/terms':('Terms of Service — SentryLoot','Terms for using the SentryLoot marketplace.'),
        '/refunds':('Refund and Dispute Policy — SentryLoot','How to request help with an order or report a dispute.'),
        '/seller-policy':('Seller Policy — SentryLoot','Rules and responsibilities for SentryLoot sellers.'),
        '/prohibited-items':('Prohibited Items — SentryLoot','Products and conduct prohibited on SentryLoot.'),
        '/contact':('Contact SentryLoot','Contact SentryLoot support and compliance.'),
        '/blog':('SentryLoot Blog','Guides to safer buying, selling, and gaming marketplaces.')}
    canonical=base+path
    body=''
    if path=='/top-up' and slug:
        parts=slug.split('/')
        db=connect()
        try:
            if len(parts)==1:
                game=db.execute('SELECT game_name FROM topup_packages WHERE game_slug=? AND enabled=1 LIMIT 1',(parts[0],)).fetchone()
                if not game: return None
                title=str(game['game_name'])+' Top Up | SentryLoot'; description='Browse '+str(game['game_name'])+' game currency packages.'; canonical=base+'/top-up/'+urlquote(parts[0],safe='')
            elif len(parts)==2:
                package=db.execute('SELECT game_name,amount,currency FROM topup_packages WHERE game_slug=? AND url_slug=? AND enabled=1',(parts[0],parts[1])).fetchone()
                if not package: return None
                title=f"{package['amount']} {package['currency']} {package['game_name']} Top Up | SentryLoot"; description=f"Top up {package['amount']} {package['currency']} for {package['game_name']} on SentryLoot."; canonical=base+'/top-up/'+urlquote(parts[0],safe='')+'/'+urlquote(parts[1],safe='')
            else: return None
        finally: db.close()
        body='<section class="page"><h1>'+html.escape(title)+'</h1><p>'+html.escape(description)+'</p></section>'
    elif path=='/blog' and slug:
        db=connect()
        try: row=db.execute("SELECT * FROM blog_posts WHERE slug=? AND status='published'",(slug,)).fetchone()
        finally: db.close()
        if not row: return None
        post=blog_post_view(row); title=str(post['title'][2])+' | SentryLoot'; description=str(post['summary'][2])[:260]; canonical=base+'/blog/'+urlquote(slug,safe='')
        body='<article class="page blog-article"><h1>'+html.escape(str(post['title'][2]))+'</h1><p>'+html.escape(str(post['summary'][2]))+'</p>'+''.join('<p>'+html.escape(str(paragraph))+'</p>' for paragraph in post['body'][2])+'</article>'
    else:
        title,description=title_map.get(path,('SentryLoot','Game marketplace for approved digital products and services.'))
        body='<section class="page"><h1>'+html.escape(title)+'</h1><p>'+html.escape(description)+'</p></section>'
    template=re.sub(r'<html lang="[^"]*">', '<html lang="en">', template, count=1)
    template=re.sub(r'<title>.*?</title>', '<title>'+html.escape(title)+'</title>', template, count=1, flags=re.S)
    template=re.sub(r'<meta name="description" content="[^"]*">','<meta name="description" content="'+html.escape(description,quote=True)+'">',template,count=1)
    template=re.sub(r'<link rel="canonical" href="[^"]*">','<link rel="canonical" href="'+html.escape(canonical,quote=True)+'">',template,count=1)
    template=re.sub(r'<meta property="og:title" content="[^"]*">','<meta property="og:title" content="'+html.escape(title,quote=True)+'">',template,count=1)
    template=re.sub(r'<meta property="og:description" content="[^"]*">','<meta property="og:description" content="'+html.escape(description,quote=True)+'">',template,count=1)
    template=re.sub(r'<meta property="og:url" content="[^"]*">','<meta property="og:url" content="'+html.escape(canonical,quote=True)+'">',template,count=1)
    template=re.sub(r'<meta property="og:image" content="[^"]*">','<meta property="og:image" content="'+html.escape(base+'/static/assets/sentryloot-logo-full.jpg',quote=True)+'">',template,count=1)
    template=template.replace('<main id="app" tabindex="-1"><div class="loading"><span class="spinner"></span> Yuklanmoqda…</div></main>','<main id="app" tabindex="-1">'+body+'</main>')
    return template.encode('utf-8')

def order_view(db, oid, uid, admin=False):
    q=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if not q: return None
    order=dict(q)
    items=db.execute('SELECT oi.*,l.game_id,l.category_id,l.product_type FROM order_items oi LEFT JOIN listings l ON l.id=oi.listing_id WHERE oi.order_id=?',(oid,)).fetchall()
    is_buyer=order['buyer_id']==uid
    if not admin and not is_buyer and not any(i['seller_id']==uid for i in items): raise HttpError(403,'Bu buyurtmaga ruxsatingiz yo‘q.')
    if not admin and not is_buyer:
        items=[i for i in items if i['seller_id']==uid]
        order['buyer_id']=None
        order['subtotal_minor']=sum(i['unit_price_minor']*i['quantity'] for i in items)
        order['commission_minor']=sum(i['commission_minor'] for i in items)
        order['total_minor']=order['subtotal_minor']
    order['items']=[]
    for item in items:
        it=dict(item)
        delivery=db.execute('SELECT id,submitted_at,buyer_accessed_at,protected_payload FROM deliveries WHERE order_item_id=?',(it['id'],)).fetchone()
        if delivery and is_buyer and order['status'] in ('paid','awaiting_delivery','delivered','completed','disputed','under_review'):
            delivered=dict(delivery)
            try:
                delivered['protected_payload']=delivery_crypto.decrypt_payload(delivered['protected_payload'],it['id'])
            except delivery_crypto.DeliveryCryptoError as exc:
                raise HttpError(503,'Yetkazish ma’lumoti xavfsiz ochilmadi. Encryption kaliti va eski ma’lumotlar migratsiyasini tekshiring.') from exc
            it['delivery']=delivered
        else:
            it['delivery']={'submitted_at':delivery['submitted_at']} if delivery else None
        it.pop('seller_id',None)
        order['items'].append(it)
    order['events']=[dict(x) for x in db.execute('SELECT to_status,note,created_at FROM order_events WHERE order_id=? ORDER BY created_at',(oid,)).fetchall()]
    order['payment']=rowdict(db.execute('SELECT provider,status,amount_minor,currency,created_at FROM payments WHERE order_id=?',(oid,)).fetchone())
    if is_buyer or admin:
        review=db.execute('SELECT status,review_note,buyer_attested_at,submitted_at,reviewed_at FROM account_reviews WHERE order_id=?',(oid,)).fetchone()
        if review:
            slots={row['slot'] for row in db.execute('SELECT slot FROM account_review_evidence WHERE order_id=?',(oid,)).fetchall()}
            order['account_review']={**dict(review),'evidence_slots':sorted(slots)}
    return order

def checkout(db,uid,accept_terms=False,accept_account_risk=False):
    if not accept_terms: raise HttpError(400,'Checkoutdan oldin savdo shartlarini qabul qiling.')
    try: provider=get_provider(MODE,os.environ.get('PAYMENT_PROVIDER','disabled'))
    except RuntimeError as e: raise HttpError(503,'Haqiqiy to‘lov provayderi hali sozlanmagan. Ishlab chiqarish checkout’i yopiq.')
    db.execute('BEGIN IMMEDIATE')
    try:
        # release expired reservations so abandoned carts cannot lock stock forever
        expired_order_filter="o.created_at::timestamptz < CURRENT_TIMESTAMP - INTERVAL '30 minutes'" if DATABASE_URL else "o.created_at < datetime('now','-30 minutes')"
        old=db.execute(f"SELECT o.id,oi.listing_id,oi.quantity FROM orders o JOIN order_items oi ON oi.order_id=o.id WHERE o.status='pending_payment' AND {expired_order_filter}").fetchall()
        for x in old:
            db.execute('UPDATE listings SET reserved=CASE WHEN reserved>? THEN reserved-? ELSE 0 END WHERE id=?',(x['quantity'],x['quantity'],x['listing_id']))
            db.execute("UPDATE orders SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE id=?",(x['id'],))
            db.execute("UPDATE payments SET status='expired',updated_at=CURRENT_TIMESTAMP WHERE order_id=?",(x['id'],))
            event(db,x['id'],None,'pending_payment','cancelled','To‘lov muddati tugadi')
        cart=db.execute('SELECT c.listing_id,c.quantity,l.* FROM carts c JOIN listings l ON l.id=c.listing_id WHERE c.user_id=?',(uid,)).fetchall()
        if not cart: raise HttpError(400,'Savatchangiz bo‘sh.')
        account_lines=[x for x in cart if x['product_type']=='account']
        if account_lines and not accept_account_risk:
            raise HttpError(400,'Akkaunt xarid qilish xavflari va noshir qoidalarini tushunganingizni tasdiqlang.')
        if any(x['seller_account_terms_version']!=ACCOUNT_SELLER_TERMS_VERSION for x in account_lines):
            raise HttpError(409,'Akkaunt e’loni sotuvchi tasdiqlashidan o‘tmagan; xaridni davom ettirib bo‘lmaydi.')
        currencies={x['currency'] for x in cart}
        if len(currencies)!=1: raise HttpError(400,'Turli valyutadagi mahsulotlarni bitta buyurtmada xarid qilib bo‘lmaydi.')
        currency=currencies.pop(); subtotal=0; lines=[]
        for x in cart:
            if x['seller_id']==uid: raise HttpError(400,'O‘zingizning e’loningizni xarid qila olmaysiz.')
            if x['status']!='published': raise HttpError(409,'Savatchadagi e’lonlardan biri endi mavjud emas.')
            if x['stock']-x['reserved']<x['quantity']: raise HttpError(409,'Mahsulot qoldig‘i yetarli emas.')
            subtotal += x['price_minor']*x['quantity']; lines.append(x)
        config=db.execute("SELECT value FROM platform_config WHERE key='commission_bps'").fetchone()
        bps=int(config['value']) if config else 0
        commission=(subtotal*bps)//10000
        oid,reference,idem=ident(),'BG-'+secrets.token_hex(4).upper(),create_token()
        intent=provider.create_intent(oid,subtotal+commission,currency,idem)
        terms=db.execute("SELECT value FROM platform_config WHERE key='terms_version'").fetchone()['value']
        db.execute('INSERT INTO orders(id,reference,buyer_id,currency,subtotal_minor,commission_minor,commission_bps,total_minor,status,payment_mode,accepted_checkout_terms_version,accepted_checkout_terms_at,accepted_account_sale_terms_version,accepted_account_sale_terms_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(oid,reference,uid,currency,subtotal,commission,bps,subtotal+commission,'pending_payment',intent.provider,terms,now_iso(),ACCOUNT_BUYER_TERMS_VERSION if account_lines else '',now_iso() if account_lines else None))
        remainder=commission-sum((y['price_minor']*y['quantity']*bps)//10000 for y in lines)
        for ix,x in enumerate(lines):
            per_fee=(x['price_minor']*x['quantity']*bps)//10000
            if ix < remainder: per_fee += 1
            reservation=db.execute('UPDATE listings SET reserved=reserved+?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND stock-reserved>=?',(x['quantity'],x['listing_id'],x['quantity']))
            if reservation.rowcount!=1: raise HttpError(409,'Mahsulot qoldig‘i band qilindi. Savatchani yangilang.')
            db.execute('INSERT INTO order_items(id,order_id,listing_id,seller_id,title,quantity,unit_price_minor,commission_minor,delivery_method) VALUES(?,?,?,?,?,?,?,?,?)',(ident(),oid,x['listing_id'],x['seller_id'],x['title'],x['quantity'],x['price_minor'],per_fee,x['delivery_method']))
        db.execute('INSERT INTO payments(id,order_id,provider,amount_minor,currency,status,idempotency_key) VALUES(?,?,?,?,?,?,?)',(ident(),oid,intent.provider,intent.amount_minor,intent.currency,'pending',intent.idempotency_key))
        db.execute('DELETE FROM carts WHERE user_id=?',(uid,)); event(db,oid,uid,None,'pending_payment','Sandbox to‘lov yaratildi')
        db.execute('COMMIT'); return {'id':oid,'reference':reference,'status':'pending_payment','total_minor':subtotal+commission,'currency':currency,'mode':'sandbox'}
    except Exception:
        db.execute('ROLLBACK'); raise

class Handler(BaseHTTPRequestHandler):
    server_version='SentryLoot/0.1'
    def oauth_base_url(self):
        if MODE == 'production':
            base=os.environ.get('PUBLIC_BASE_URL','').rstrip('/')
            if not base.startswith('https://'): raise HttpError(503,'Ishlab chiqarishda PUBLIC_BASE_URL HTTPS bo‘lishi kerak.')
            return base
        # In development the browser may use either localhost or 127.0.0.1.
        # Use the request host so the OAuth state cookie and callback share a host.
        host=self.headers.get('Host','localhost:8000').lower()
        if not re.fullmatch(r'(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?',host):
            raise HttpError(400,'Local OAuth host noto‘g‘ri.')
        return 'http://'+host
    def log_message(self, fmt, *args):
        # Request lines can contain OAuth codes, state, or one-time tokens.
        # Do not log raw paths or query strings from application requests.
        return
    def send_json(self, code, data, headers=None):
        payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
        self.send_response(code); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store'); self.send_header('Pragma','no-cache'); self.send_header('Vary','Cookie'); self.secure_headers()
        for k,v in (headers or {}).items():
            for value in (v if isinstance(v,(list,tuple)) else [v]): self.send_header(k,value)
        self.end_headers(); self.wfile.write(payload)
    def secure_headers(self):
        self.send_header('X-Content-Type-Options','nosniff'); self.send_header('X-Frame-Options','DENY'); self.send_header('Referrer-Policy','strict-origin-when-cross-origin'); self.send_header('Permissions-Policy','camera=(self "https://verify.didit.me"), microphone=(self "https://verify.didit.me"), geolocation=()'); self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data: https: blob: https://s3.amazonaws.com; script-src 'self' https://client.crisp.chat https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://client.crisp.chat https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' data: https://client.crisp.chat https://fonts.gstatic.com; style-src-attr 'unsafe-inline'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; connect-src 'self' https://api.frankfurter.dev https://client.crisp.chat https://storage.crisp.chat wss://client.relay.crisp.chat wss://client.relay.rescue.crisp.chat wss://stream.relay.crisp.chat; frame-src 'self' https://client.crisp.chat https://assets.crisp.chat https://*.crisp.help; media-src 'self' blob: https://client.crisp.chat; worker-src 'self' blob: https://client.crisp.chat")
        if MODE=='production': self.send_header('Strict-Transport-Security','max-age=31536000')
    def body(self, limit=MAX_BODY):
        n=int(self.headers.get('Content-Length','0'))
        if n>limit: raise HttpError(413,'So‘rov hajmi cheklovdan oshdi.')
        return self.rfile.read(n) if n else b'{}'
    def cookie(self):
        for part in self.headers.get('Cookie','').split(';'):
            k,sep,v=part.strip().partition('=')
            if sep and k==COOKIE_NAME: return v
        return ''
    def context(self, db):
        uid=None; csrf=None
        raw=decode_session(self.cookie())
        if raw:
            s=db.execute('SELECT user_id,csrf FROM sessions WHERE token_hash=? AND expires_at>?',(hash_token(raw),now_iso())).fetchone()
            if s: uid,csrf=s['user_id'],s['csrf']
        return {'db':db,'uid':uid,'csrf':csrf,'user':user_view(db,uid) if uid else None}
    def set_session(self, token):
        self._set_cookie=f'{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_DAYS*86400}' + ('; Secure' if MODE=='production' else '')
    def dispatch(self):
        parsed=urlparse(self.path); path=parsed.path.rstrip('/') or '/'; method=self.command
        db=connect()
        try:
            ctx=self.context(db)
            csrf_exempt=path=='/api/webhooks/didit'
            if method in ('POST','PATCH','DELETE') and ctx['uid'] and not csrf_exempt:
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),ctx['csrf'] or ''): raise HttpError(403,'Xavfsizlik tokeni noto‘g‘ri. Sahifani yangilang.')
            binary_evidence=method=='POST' and re.fullmatch(r'/api/orders/[A-Za-z0-9_-]{1,100}/account-evidence/[12]',path)
            raw_body=self.body(MAX_IMAGE_BODY) if method=='POST' and (path=='/api/listing-images' or binary_evidence) else self.body() if method in ('POST','PATCH','PUT') and path.startswith('/api/') else b''
            if (path=='/api/listing-images' and method=='POST') or binary_evidence: data={}
            else: data=parse_json(raw_body) if raw_body else {}
            result=self.route(db,ctx,method,path,parse_qs(parsed.query),data,raw_body)
            if isinstance(result,tuple) and len(result)==3: status,data,headers=result
            elif isinstance(result,tuple) and len(result)==2: status,data=result; headers={}
            else: status,data,headers=200,result,{}
            if hasattr(self,'_set_cookie'): headers={**headers,'Set-Cookie':([self._set_cookie] if 'Set-Cookie' not in headers else [self._set_cookie,*headers['Set-Cookie']])}
            self.send_json(status,data,headers)
        except HttpError as e: self.send_json(e.status,{'error':e.message})
        except DB_INTEGRITY_ERRORS as e: self.send_json(409,{'error':'Ma’lumotlar to‘qnashuvi yuz berdi. Kiritilgan qiymatlarni tekshiring.'})
        except Exception as e:
            print('request error:',type(e).__name__)
            self.send_json(500,{'error':'Ichki xatolik yuz berdi.'})
        finally: db.close()
    def do_GET(self):
        if not self.path.startswith('/api/'):
            parsed=urlparse(self.path)
            if parsed.path=='/robots.txt':
                payload=f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /admin\nSitemap: {public_site_base()}/sitemap.xml\n".encode('utf-8')
                self.send_response(200); self.send_header('Content-Type','text/plain; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','public, max-age=3600'); self.secure_headers(); self.end_headers(); self.wfile.write(payload); return
            if parsed.path=='/sitemap.xml':
                payload=public_sitemap_xml()
                self.send_response(200); self.send_header('Content-Type','application/xml; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','public, max-age=300'); self.secure_headers(); self.end_headers(); self.wfile.write(payload); return
            public_route=parsed.path.rstrip('/') or '/'
            if public_route in ('/top-up','/browse','/blog','/guide','/fees','/policies','/support','/help','/terms','/refunds','/seller-policy','/prohibited-items','/contact'):
                payload=seo_page_html(public_route)
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','public, max-age=300'); self.secure_headers(); self.end_headers(); self.wfile.write(payload); return
            topup_match=re.fullmatch(r'/top-up(?:/([a-z0-9-]+))?(?:/([a-z0-9-]+))?',public_route)
            if topup_match:
                slug='/'.join(part for part in topup_match.groups() if part) or None
                payload=seo_page_html('/top-up',slug)
                if payload is None: self.send_error(404); return
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','public, max-age=300'); self.secure_headers(); self.end_headers(); self.wfile.write(payload); return
            blog_match=re.fullmatch(r'/blog/([a-z0-9]+(?:-[a-z0-9]+)*)',public_route)
            if blog_match:
                payload=seo_page_html('/blog',blog_match.group(1))
                if payload is None: self.send_error(404); return
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','public, max-age=300'); self.secure_headers(); self.end_headers(); self.wfile.write(payload); return
            listing_match=re.fullmatch(r'/listing/([A-Za-z0-9_-]{1,100})',parsed.path)
            if listing_match:
                payload=seo_listing_html(listing_match.group(1))
                if payload is None: self.send_error(404); return
                self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(payload))); self.send_header('Cache-Control','no-store'); self.secure_headers(); self.end_headers(); self.wfile.write(payload); return
            f={'/':'index.html','/privacy-policy':'privacy-policy.html','/data-deletion':'data-deletion.html','/static/app.js':'app.js','/static/topup.js':'topup.js','/static/crisp-loader.js':'crisp-loader.js','/static/locales.js':'locales.js','/static/locale-extra.js':'locale-extra.js','/static/legal-locale.js':'legal-locale.js','/static/asia-markets-data.js':'asia-markets-data.js','/static/asia-markets.json':'asia-markets.json','/static/vercel-insights.js':'vercel-insights.js','/static/style.css':'style.css','/static/favicon.svg':'favicon.svg','/static/assets/sentryloot-app-icon.png':'assets/sentryloot-app-icon.png','/static/assets/sentryloot-favicon.png':'assets/sentryloot-favicon.png','/static/assets/sentryloot-logo-crest.jpg':'assets/sentryloot-logo-crest.jpg','/static/assets/sentryloot-logo-full.jpg':'assets/sentryloot-logo-full.jpg','/static/assets/hero-background.jpg':'assets/hero-background.jpg','/static/assets/fortnite-hero-cutout.png':'assets/fortnite-hero-cutout.png','/static/assets/topup-pubg-mobile.svg':'assets/topup-pubg-mobile.svg','/static/assets/topup-mobile-legends.svg':'assets/topup-mobile-legends.svg','/static/assets/topup-free-fire.svg':'assets/topup-free-fire.svg','/static/assets/topup-honor-of-kings.svg':'assets/topup-honor-of-kings.svg'}.get(parsed.path)
            if not f: self.send_error(404); return
            data=(ROOT/'static'/f).read_bytes() if f!='index.html' else (ROOT/'static/index.html').read_bytes()
            ctype='text/html; charset=utf-8' if f.endswith('.html') else ('application/json; charset=utf-8' if f.endswith('.json') else ('application/javascript; charset=utf-8' if f.endswith('.js') else ('image/svg+xml' if f.endswith('.svg') else ('image/jpeg' if f.endswith(('.jpg','.jpeg')) else ('image/png' if f.endswith('.png') else 'text/css; charset=utf-8')))))
            self.send_response(200);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.secure_headers();self.end_headers();self.wfile.write(data);return
        self.dispatch()
    def do_POST(self): self.dispatch()
    def do_PATCH(self): self.dispatch()
    def do_DELETE(self): self.dispatch()
    def route(self,db,ctx,method,path,qs,data,raw_body=b''):
        uid=ctx['uid']
        if path=='/healthz' and method=='GET': return {'ok':True}
        if path=='/api/health' and method=='GET':
            try: payment_state=get_provider(MODE,os.environ.get('PAYMENT_PROVIDER','disabled').strip().lower()).name
            except RuntimeError: payment_state='unconfigured'
            return {'ok':True,'mode':MODE,'database':'supabase-postgres' if DATABASE_URL else 'sqlite',
                    'payments':payment_state,'identity_verification':'didit-configured' if identity_service.is_configured() else 'unconfigured',
                    'account_evidence_storage_credentials':'present' if SUPABASE_URL.startswith('https://') and SUPABASE_SERVICE_ROLE_KEY and re.fullmatch(r'[a-z0-9_-]{1,100}',SUPABASE_ACCOUNT_EVIDENCE_BUCKET) else 'missing',
                    'sales_enabled':production_marketplace_sales_enabled() if MODE=='production' else False,
                    'sales_guard':'closed' if MODE=='production' and not production_marketplace_sales_enabled() else 'preview'}
        if path=='/api/cron/account-deletions' and method=='GET':
            cron_secret=os.environ.get('CRON_SECRET','')
            authorization=self.headers.get('Authorization','')
            if not cron_secret or not hmac.compare_digest(authorization,'Bearer '+cron_secret):
                raise HttpError(401,'Avtorizatsiya talab qilinadi.')
            now=datetime.now(timezone.utc)
            # Run with a two-day buffer so the daily scheduler's timing does not
            # push a request past the publicly promised 30-day deletion window.
            cutoff=now-timedelta(days=28)
            requests=db.execute("SELECT id,user_id,created_at FROM account_deletion_requests WHERE status IN ('pending','reviewing') ORDER BY created_at LIMIT 1000").fetchall()
            erased=0
            for request in requests:
                try:
                    created_at=datetime.fromisoformat(str(request['created_at']).replace('Z','+00:00'))
                    if created_at.tzinfo is None: created_at=created_at.replace(tzinfo=timezone.utc)
                except (TypeError,ValueError):
                    continue
                if created_at>cutoff: continue
                db.execute('BEGIN')
                try:
                    current=db.execute("SELECT user_id FROM account_deletion_requests WHERE id=? AND status IN ('pending','reviewing')",(request['id'],)).fetchone()
                    if current:
                        db.execute('DELETE FROM account_review_evidence WHERE order_id IN (SELECT order_id FROM account_reviews WHERE buyer_id=?)',(current['user_id'],))
                        erase_account_personal_data(db,current['user_id'])
                        db.execute("UPDATE account_deletion_requests SET status='resolved',reviewed_by=NULL,reviewed_at=CURRENT_TIMESTAMP WHERE id=?",(request['id'],))
                        audit(db,None,'deletion_auto_resolved','deletion_request',request['id'],{'personal_data_erased':True,'retention_days':30})
                        erased+=1
                    db.execute('COMMIT')
                except Exception:
                    db.execute('ROLLBACK')
                    raise
            return {'ok':True,'erased':erased,'checked':len(requests)}
        if path=='/api/cron/account-evidence-retention' and method=='GET':
            cron_secret=os.environ.get('CRON_SECRET','')
            authorization=self.headers.get('Authorization','')
            if not cron_secret or not hmac.compare_digest(authorization,'Bearer '+cron_secret): raise HttpError(401,'Avtorizatsiya talab qilinadi.')
            cutoff=datetime.now(timezone.utc)-timedelta(days=30); removed=0
            reviews=db.execute("SELECT order_id,reviewed_at FROM account_reviews WHERE status IN ('approved','refunded') AND reviewed_at IS NOT NULL ORDER BY reviewed_at LIMIT 1000").fetchall()
            for review in reviews:
                try:
                    reviewed_at=datetime.fromisoformat(str(review['reviewed_at']).replace('Z','+00:00'))
                    if reviewed_at.tzinfo is None: reviewed_at=reviewed_at.replace(tzinfo=timezone.utc)
                except (TypeError,ValueError): continue
                if reviewed_at>cutoff: continue
                evidence=db.execute('SELECT slot,object_path FROM account_review_evidence WHERE order_id=?',(review['order_id'],)).fetchall()
                if any(not delete_account_evidence_object(row['object_path']) for row in evidence): continue
                db.execute('DELETE FROM account_review_evidence WHERE order_id=?',(review['order_id'],)); removed+=len(evidence)
            return {'ok':True,'evidence_deleted':removed,'reviews_checked':len(reviews),'retention_days':30}
        if path=='/api/me' and method=='GET': return {'user':ctx['user'],'csrf':ctx['csrf'],'mode':MODE}
        if path=='/api/blog' and method=='GET':
            return [blog_post_view(x) for x in db.execute("SELECT * FROM blog_posts WHERE status='published' ORDER BY published_at DESC,created_at DESC LIMIT 100")]
        if path.startswith('/api/blog/') and method=='GET':
            slug=path.rsplit('/',1)[-1]
            row=db.execute("SELECT * FROM blog_posts WHERE slug=? AND status='published'",(slug,)).fetchone()
            if not row: raise HttpError(404,'Maqola topilmadi.')
            return blog_post_view(row)
        if path=='/api/oauth/providers' and method=='GET': return {'google':bool(os.environ.get('GOOGLE_CLIENT_ID') and os.environ.get('GOOGLE_CLIENT_SECRET')),'facebook':bool(os.environ.get('FACEBOOK_APP_ID') and os.environ.get('FACEBOOK_APP_SECRET'))}
        if path=='/api/oauth/start' and method=='POST':
            provider=data.get('provider')
            if provider not in ('google','facebook'): raise HttpError(400,'Kirish provayderi noto‘g‘ri.')
            oauth_mode=data.get('mode','login')
            if oauth_mode not in ('login','link') or (oauth_mode=='link' and provider!='facebook'): raise HttpError(400,'Facebook bog‘lash so‘rovi noto‘g‘ri.')
            if oauth_mode=='link': require_verified(ctx)
            elif data.get('accept_terms') is not True: raise HttpError(400,'Davom etish uchun foydalanish shartlarini qabul qiling.')
            country=data.get('country','UZ')
            if not isinstance(country,str) or country not in ASIA_COUNTRIES: raise HttpError(400,'Osiyo mamlakatini tanlang.')
            if provider=='google':
                client_id=os.environ.get('GOOGLE_CLIENT_ID','')
                if not client_id or not os.environ.get('GOOGLE_CLIENT_SECRET'): raise HttpError(503,'Google Sign In hali sozlanmagan.')
            else:
                client_id=os.environ.get('FACEBOOK_APP_ID','')
                if not client_id or not os.environ.get('FACEBOOK_APP_SECRET'): raise HttpError(503,'Facebook orqali kirish hali sozlanmagan.')
            check_rate(db,'oauth_start_'+provider,self.client_address[0],8)
            base=self.oauth_base_url()
            callback=base+'/api/oauth/'+provider+'/callback'
            state,nonce=f'{country}.{oauth_mode}.{create_token()}',create_token()
            payload=f'{state}.{nonce}.{int(time.time())}'
            signature=hmac.new(SESSION_SECRET.encode(),(provider+'.'+payload).encode(),hashlib.sha256).hexdigest()
            secure='; Secure' if MODE=='production' else ''
            self._set_cookie=f'bozorgg_oauth_{provider}={payload}.{signature}; Path=/api/oauth/{provider}/callback; HttpOnly; SameSite=Lax; Max-Age=600'+secure
            url=oauth_service.google_authorization_url(client_id,callback,state,nonce) if provider=='google' else oauth_service.facebook_authorization_url(client_id,callback,state)
            return {'authorization_url':url}
        if path in ('/api/oauth/google/callback','/api/oauth/facebook/callback') and method=='GET':
            provider='google' if path.endswith('/google/callback') else 'facebook'
            def cookie_value(name):
                for part in self.headers.get('Cookie','').split(';'):
                    key,sep,value=part.strip().partition('=')
                    if sep and key==name: return value
                return ''
            payload=cookie_value('bozorgg_oauth_'+provider)
            if payload:
                parts=payload.rsplit('.',3)
                saved_state,saved_nonce,saved_at,signature=parts if len(parts)==4 else ('','','','')
            else: saved_state,saved_nonce,saved_at,signature='','','',''
            signed_payload='.'.join((saved_state,saved_nonce,saved_at))
            expected=hmac.new(SESSION_SECRET.encode(),(provider+'.'+signed_payload).encode(),hashlib.sha256).hexdigest() if payload else ''
            supplied_state=qs.get('state',[''])[0]
            code=qs.get('code',[''])[0]
            if not payload or not hmac.compare_digest(signature,expected) or not hmac.compare_digest(str(supplied_state or ''),saved_state): raise HttpError(400,'Kirish so‘rovi muddati o‘tgan yoki noto‘g‘ri. Qayta urinib ko‘ring.')
            try: created=int(saved_at)
            except ValueError: created=0
            if created<int(time.time())-600 or created>int(time.time())+30: raise HttpError(400,'Kirish so‘rovi muddati o‘tgan. Qayta urinib ko‘ring.')
            if not code or len(str(code))>4096: raise HttpError(400,'Provayder avtorizatsiya kodi noto‘g‘ri.')
            base=self.oauth_base_url()
            try: identity=oauth_service.exchange_code(provider,str(code),base+'/api/oauth/'+provider+'/callback',saved_nonce)
            except Exception as exc:
                print('oauth provider error:',provider,type(exc).__name__)
                raise HttpError(401,'Google/Facebook hisobini tasdiqlab bo‘lmadi. Qayta urinib ko‘ring.')
            subject,email,name=identity['subject'],identity['email'],clean_text(identity['name'],'Ism',1,80)
            state_parts=saved_state.split('.')
            oauth_country=state_parts[0] if state_parts else 'UZ'
            oauth_mode=state_parts[1] if len(state_parts)>2 else 'login'
            if oauth_mode not in ('login','link'): raise HttpError(400,'Kirish so‘rovi noto‘g‘ri.')
            if oauth_country not in ASIA_COUNTRIES: raise HttpError(400,'Kirish so‘rovidagi mamlakat noto‘g‘ri.')
            linked=db.execute('SELECT u.id,u.suspended FROM oauth_identities i JOIN users u ON u.id=i.user_id WHERE i.provider=? AND i.subject=?',(provider,subject)).fetchone()
            secure='; Secure' if MODE=='production' else ''
            clear=f'bozorgg_oauth_{provider}=; Path=/api/oauth/{provider}/callback; HttpOnly; SameSite=Lax; Max-Age=0'+secure
            if oauth_mode=='link':
                if not ctx['uid'] or not ctx['user'] or not ctx['user']['email_verified'] or ctx['user']['suspended']:
                    return 302,{'ok':False},{'Location':'/?oauth_error=link_signin_required#login','Set-Cookie':[clear]}
                if linked and linked['id']!=ctx['uid']:
                    return 302,{'ok':False},{'Location':'/?oauth_error=facebook_in_use#login','Set-Cookie':[clear]}
                existing=db.execute('SELECT subject FROM oauth_identities WHERE provider=? AND user_id=?',(provider,ctx['uid'])).fetchone()
                if existing and existing['subject']!=subject:
                    return 302,{'ok':False},{'Location':'/?oauth_error=facebook_already_linked#login','Set-Cookie':[clear]}
                if not linked:
                    db.execute('INSERT INTO oauth_identities(provider,subject,user_id) VALUES(?,?,?)',(provider,subject,ctx['uid']))
                return 302,{'ok':True},{'Location':'/?oauth_linked=facebook#home','Set-Cookie':[clear]}
            if linked:
                if linked['suspended']: raise HttpError(403,'Hisobingiz vaqtincha cheklangan.')
                user_id=linked['id']
            else:
                if db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone():
                    return 302,{'ok':False},{'Location':'/?oauth_error=account_exists#login','Set-Cookie':[clear]}
                terms=db.execute("SELECT value FROM platform_config WHERE key='terms_version'").fetchone()['value']
                user_id=ident()
                db.execute('INSERT INTO users(id,email,password_hash,display_name,country,language,currency,email_verified,accepted_terms_version,accepted_terms_at) VALUES(?,?,?,?,?,?,?,1,?,?)',(user_id,email,password_hash(create_token()),name,oauth_country,'en',ASIA_COUNTRY_CURRENCIES[oauth_country],terms,now_iso()))
                db.execute('INSERT INTO oauth_identities(provider,subject,user_id) VALUES(?,?,?)',(provider,subject,user_id))
            session_token,csrf=session_create(db,user_id); self.set_session(session_token)
            return 302,{'ok':True},{'Location':'/#account','Set-Cookie':[clear]}
        if path=='/api/webhooks/didit' and method=='POST':
            payload=identity_service.verify_webhook(raw_body,self.headers.get('X-Signature-V2',''),self.headers.get('X-Timestamp',''))
            if payload is None: raise HttpError(401,'Didit webhook imzosi yoki vaqti noto‘g‘ri.')
            if payload.get('webhook_type')!='status.updated': return {'ok':True,'ignored':'event type'}
            if MODE=='production' and payload.get('environment')!='live': return {'ok':True,'ignored':'non-live event'}
            session_id=payload.get('session_id')
            if not isinstance(session_id,str) or not session_id: raise HttpError(400,'Didit sessiya identifikatori yo‘q.')
            try:
                event_time=datetime.fromtimestamp(int(payload['timestamp']),timezone.utc).isoformat(timespec='milliseconds')
            except (KeyError,TypeError,ValueError,OverflowError,OSError): raise HttpError(400,'Didit webhook vaqti noto‘g‘ri.')
            profile=db.execute("SELECT * FROM seller_profiles WHERE identity_reference=? AND identity_provider='didit'",(session_id,)).fetchone()
            if not profile: return {'ok':True,'ignored':'unknown session'}
            if profile['identity_last_event_at'] and event_time<=profile['identity_last_event_at']: return {'ok':True,'ignored':'stale event'}
            provider_status=payload.get('status')
            decision=payload.get('decision') if isinstance(payload.get('decision'),dict) else {}
            def feature_passed(key):
                values=decision.get(key)
                return isinstance(values,list) and bool(values) and all(isinstance(x,dict) and x.get('status')=='Approved' for x in values)
            checks_complete=all(feature_passed(key) for key in ('id_verifications','liveness_checks','face_matches'))
            identity_status='verified' if provider_status=='Approved' and checks_complete else ('rejected' if provider_status=='Declined' else 'pending')
            db.execute('UPDATE seller_profiles SET identity_status=?,identity_verified_at=?,identity_last_event_at=? WHERE user_id=?',(identity_status,event_time if identity_status=='verified' else None,event_time,profile['user_id']))
            if identity_status!='verified':
                db.execute('UPDATE seller_profiles SET selling_enabled=0 WHERE user_id=?',(profile['user_id'],))
                db.execute("UPDATE listings SET status='paused',updated_at=CURRENT_TIMESTAMP WHERE seller_id=? AND status='published'",(profile['user_id'],))
            message={'verified':'Didit tekshiruvi yakunlandi. Administrator sotuvchi profilingizni ko‘rib chiqadi.','rejected':'Didit shaxsni tekshirishni tasdiqlamadi. Sotish hozircha yopiq.','pending':'Didit tekshiruvi ko‘rib chiqilmoqda.'}[identity_status]
            notify(db,profile['user_id'],'identity_review','Shaxsni tekshirish holati yangilandi',message,'/seller')
            audit(db,None,'didit_identity_'+identity_status,'seller',profile['user_id'],{'provider':'didit','event_at':event_time,'event_id':payload.get('event_id')})
            return {'ok':True}
        if path=='/api/register' and method=='POST':
            if data.get('accept_terms') is not True: raise HttpError(400,'Ro‘yxatdan o‘tish uchun foydalanish shartlarini qabul qiling.')
            if not email_service.is_configured() and MODE!='development': raise HttpError(503,'Ro‘yxatdan o‘tish uchun xavfsiz email yuborish xizmati konfiguratsiyasi kerak.')
            check_rate(db,'register',self.client_address[0],5)
            email=clean_text(data.get('email'),'Email',3,254).lower(); name=clean_text(data.get('name'),'Ism',2,80); password=data.get('password','')
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(password)<10 or len(password)>256: raise HttpError(400,'To‘g‘ri email va kamida 10 belgili parol kiriting.')
            if email in (os.environ.get('SEED_ADMIN_EMAIL','').lower(),): raise HttpError(409,'Bu email administratorda ishlatiladi.')
            country=data.get('country','UZ')
            if not isinstance(country,str) or country not in ASIA_COUNTRIES: raise HttpError(400,'Osiyo mamlakatini tanlang.')
            currency=ASIA_COUNTRY_CURRENCIES[country]
            user=ident(); terms=db.execute("SELECT value FROM platform_config WHERE key='terms_version'").fetchone()['value']; db.execute('INSERT INTO users(id,email,password_hash,display_name,country,language,currency,accepted_terms_version,accepted_terms_at) VALUES(?,?,?,?,?,?,?,?,?)',(user,email,password_hash(password),name,country,'en',currency,terms,now_iso()))
            raw=create_token(); db.execute('INSERT INTO email_tokens(token_hash,user_id,purpose,expires_at) VALUES(?,?,?,?)',(hash_token(raw),user,'verify',(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()))
            if email_service.is_configured():
                try: email_service.send_action_email(email,name,'verify',raw)
                except Exception: raise HttpError(503,'Hisob yaratildi, ammo tasdiqlash xati yuborilmadi. Birozdan so‘ng yangi xat so‘rang.')
                return 201,{'message':'Hisob yaratildi. Emailingizga tasdiqlash havolasini yubordik.'}
            return 201,{'message':'Hisob yaratildi. Email provider sozlanmaganligi sabab development tokeni ko‘rsatilmoqda.','verification_token':raw}
        if path=='/api/verification/resend' and method=='POST':
            if not email_service.is_configured() and MODE!='development': raise HttpError(503,'Email yuborish xizmati hozircha sozlanmagan.')
            check_rate(db,'verification_resend_ip',self.client_address[0],4)
            email=clean_text(data.get('email'),'Email',3,254).lower()
            check_rate(db,'verification_resend_email',email,3,3600)
            row=db.execute('SELECT id,display_name FROM users WHERE email=? AND email_verified=0 AND suspended=0',(email,)).fetchone()
            raw=None
            if row:
                db.execute("UPDATE email_tokens SET consumed_at=CURRENT_TIMESTAMP WHERE user_id=? AND purpose='verify' AND consumed_at IS NULL",(row['id'],))
                raw=create_token(); db.execute('INSERT INTO email_tokens(token_hash,user_id,purpose,expires_at) VALUES(?,?,?,?)',(hash_token(raw),row['id'],'verify',(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()))
                if email_service.is_configured():
                    try: email_service.send_action_email(email,row['display_name'],'verify',raw)
                    except Exception: raise HttpError(503,'Tasdiqlash xati yuborilmadi. Keyinroq qayta urinib ko‘ring.')
            result={'message':'Agar bu email tasdiqlanmagan hisobga tegishli bo‘lsa, yangi havola yuborildi.'}
            if MODE=='development' and not email_service.is_configured() and raw: result['verification_token']=raw
            return result
        if path=='/api/verify' and method=='POST':
            token=clean_text(data.get('token'),'Token',20,200); tok=db.execute("SELECT * FROM email_tokens WHERE token_hash=? AND purpose='verify' AND consumed_at IS NULL AND expires_at>?",(hash_token(token),now_iso())).fetchone()
            if not tok: raise HttpError(400,'Tasdiqlash havolasi noto‘g‘ri yoki muddati o‘tgan.')
            db.execute("UPDATE email_tokens SET consumed_at=CURRENT_TIMESTAMP WHERE user_id=? AND purpose='verify' AND consumed_at IS NULL",(tok['user_id'],)); db.execute('UPDATE users SET email_verified=1 WHERE id=?',(tok['user_id'],)); raw,csrf=session_create(db,tok['user_id']); self.set_session(raw)
            return {'user':user_view(db,tok['user_id']),'csrf':csrf}
        if path=='/api/password-reset' and method=='POST':
            if not email_service.is_configured() and MODE!='development': raise HttpError(503,'Parolni tiklash uchun xavfsiz email yuborish xizmati konfiguratsiyasi kerak.')
            check_rate(db,'password_reset',self.client_address[0],5)
            email=clean_text(data.get('email'),'Email',3,254).lower(); row=db.execute('SELECT id,display_name FROM users WHERE email=?',(email,)).fetchone(); raw=None
            if row:
                db.execute("UPDATE email_tokens SET consumed_at=CURRENT_TIMESTAMP WHERE user_id=? AND purpose='password_reset' AND consumed_at IS NULL",(row['id'],))
                raw=create_token(); db.execute('INSERT INTO email_tokens(token_hash,user_id,purpose,expires_at) VALUES(?,?,?,?)',(hash_token(raw),row['id'],'password_reset',(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()))
                if email_service.is_configured():
                    try: email_service.send_action_email(email,row['display_name'],'password_reset',raw)
                    except Exception: raise HttpError(503,'Tiklash xati yuborilmadi. Keyinroq qayta urinib ko‘ring.')
            result={'message':'Agar email ro‘yxatdan o‘tgan bo‘lsa, tiklash havolasi yuborildi.'}
            if MODE=='development' and not email_service.is_configured(): result['reset_token']=raw
            return result
        if path=='/api/password-reset/confirm' and method=='POST':
            check_rate(db,'password_reset_confirm',self.client_address[0],8)
            token=clean_text(data.get('token'),'Token',20,200); password=data.get('password','')
            if not isinstance(password,str) or len(password)<10 or len(password)>256: raise HttpError(400,'Yangi parol kamida 10 belgidan iborat bo‘lsin.')
            tok=db.execute("SELECT * FROM email_tokens WHERE token_hash=? AND purpose='password_reset' AND consumed_at IS NULL AND expires_at>?",(hash_token(token),now_iso())).fetchone()
            if not tok: raise HttpError(400,'Tiklash tokeni noto‘g‘ri yoki muddati o‘tgan.')
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash(password),tok['user_id'])); db.execute("UPDATE email_tokens SET consumed_at=CURRENT_TIMESTAMP WHERE user_id=? AND purpose='password_reset' AND consumed_at IS NULL",(tok['user_id'],)); db.execute('DELETE FROM sessions WHERE user_id=?',(tok['user_id'],)); return {'message':'Parol yangilandi. Qayta tizimga kiring.'}
        if path=='/api/login' and method=='POST':
            check_rate(db,'login',self.client_address[0],8)
            email=clean_text(data.get('email'),'Email',3,254).lower(); row=db.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
            if not row or not password_ok(str(data.get('password','')),row['password_hash']): raise HttpError(401,'Email yoki parol noto‘g‘ri.')
            if row['suspended']: raise HttpError(403,'Hisobingiz vaqtincha cheklangan.')
            if not row['email_verified']: raise HttpError(403,'Email tasdiqlanmagan. Ro‘yxatdan o‘tishda olingan havoladan foydalaning.')
            raw,csrf=session_create(db,row['id']); self.set_session(raw); return {'user':user_view(db,row['id']),'csrf':csrf}
        if path=='/api/logout' and method=='POST':
            if uid:
                session_token=decode_session(self.cookie())
                if session_token: db.execute('DELETE FROM sessions WHERE token_hash=?',(hash_token(session_token),))
            self._set_cookie=f'{COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0' + ('; Secure' if MODE=='production' else '')
            return {'ok':True}
        if path=='/api/listing-games' and method=='GET':
            where=["l.status='published'",'l.stock>l.reserved']
            if MODE=='production':
                if not production_marketplace_sales_enabled(): return []
                approved_games=sorted(approved_game_slugs('MARKETPLACE_APPROVED_GAME_SLUGS'))
                if not approved_games: return []
                where.append(f"g.slug IN ({','.join('?' for _ in approved_games)})")
                args=list(approved_games)
                approved_account_games=sorted(approved_game_slugs('MARKETPLACE_APPROVED_ACCOUNT_GAME_SLUGS'))
                if approved_account_games:
                    where.append(f"(l.product_type!='account' OR (g.slug IN ({','.join('?' for _ in approved_account_games)}) AND l.seller_account_terms_version=?))")
                    args.extend(approved_account_games); args.append(ACCOUNT_SELLER_TERMS_VERSION)
                else:
                    where.append("l.product_type!='account'")
            else:
                args=[]
            rows=db.execute(f"SELECT DISTINCT g.id,g.slug,g.name FROM listings l JOIN games g ON g.id=l.game_id JOIN categories c ON c.id=l.category_id JOIN seller_profiles s ON s.user_id=l.seller_id WHERE {' AND '.join(where)} ORDER BY g.name",tuple(args)).fetchall()
            return [dict(row) for row in rows]
        if path=='/api/games' and method=='GET': return [dict(x) for x in db.execute('SELECT id,slug,name FROM games WHERE active=1 ORDER BY name')]
        if path=='/api/categories' and method=='GET': return [dict(x) for x in db.execute('SELECT id,slug,name,product_type FROM categories WHERE active=1 ORDER BY name')]
        if path=='/api/top-up/catalog' and method=='GET':
            # Keep the public catalog recoverable if a deployment started against a
            # database whose schema migration ran without the app startup seeder.
            seed_topup_catalog(db)
            packages=db.execute('SELECT * FROM topup_packages WHERE enabled=1 ORDER BY game_name,amount').fetchall()
            games=[]
            by_slug={}
            for row in packages:
                if row['game_slug'] not in by_slug:
                    game={'slug':row['game_slug'],'name':row['game_name'],'currency':row['currency'],'packages':[]}
                    games.append(game); by_slug[row['game_slug']]=game
                item=topup_public_package(row)
                by_slug[row['game_slug']]['packages'].append(item)
            return games
        topup_match=re.fullmatch(r'/api/top-up/packages/([a-z0-9-]+)/([a-z0-9-]+)',path)
        if topup_match and method=='GET':
            seed_topup_catalog(db)
            row=db.execute('SELECT * FROM topup_packages WHERE game_slug=? AND url_slug=? AND enabled=1',(topup_match.group(1),topup_match.group(2))).fetchone()
            if not row: raise HttpError(404,'Top Up mahsuloti topilmadi.')
            return topup_public_package(row)
        if path=='/api/listings' and method=='GET':
            where=["l.status='published'"]; args=[]
            if MODE=='production':
                if not production_marketplace_sales_enabled(): return {'items':[],'total_count':0,'page':1,'page_size':24,'has_more':False}
                approved_games=sorted(approved_game_slugs('MARKETPLACE_APPROVED_GAME_SLUGS'))
                if not approved_games: return {'items':[],'total_count':0,'page':1,'page_size':24,'has_more':False}
                where.append(f"g.slug IN ({','.join('?' for _ in approved_games)})"); args.extend(approved_games)
                approved_account_games=sorted(approved_game_slugs('MARKETPLACE_APPROVED_ACCOUNT_GAME_SLUGS'))
                if approved_account_games:
                    where.append(f"(l.product_type!='account' OR (g.slug IN ({','.join('?' for _ in approved_account_games)}) AND l.seller_account_terms_version=?))"); args.extend(approved_account_games); args.append(ACCOUNT_SELLER_TERMS_VERSION)
                else:
                    where.append("l.product_type!='account'")
            for key,col in [('game','g.slug'),('category','c.slug'),('type','l.product_type')]:
                val=qs.get(key,[''])[0]
                if val: where.append(f'{col}=?'); args.append(val)
            region=qs.get('region',[''])[0].strip()
            if region: where.append('lower(l.region) LIKE ?'); args.append('%'+region.lower()+'%')
            for key,col in [('platform','l.platform'),('rank','l.attributes_json')]:
                val=qs.get(key,[''])[0].strip()
                if val:
                    if key=='rank':
                        rank_expression="COALESCE(l.attributes_json::jsonb->>'rank','')" if DATABASE_URL else "COALESCE(json_extract(l.attributes_json,'$.rank'),'')"
                        where.append(f'lower({rank_expression}) LIKE ?'); args.append('%'+val.lower()+'%')
                    else: where.append(f'lower({col}) LIKE ?'); args.append('%'+val.lower()+'%')
            server=qs.get('server',[''])[0].strip()
            if server:
                server_expression="COALESCE(l.attributes_json::jsonb->>'server',l.attributes_json::jsonb->>'server_id','')" if DATABASE_URL else "COALESCE(json_extract(l.attributes_json,'$.server'),json_extract(l.attributes_json,'$.server_id'),'')"
                where.append(f'(lower({server_expression}) LIKE ? OR lower(l.region) LIKE ?)'); args.extend([f'%{server.lower()}%',f'%{server.lower()}%'])
            search=qs.get('q',[''])[0].strip()
            if search:
                phrase='"'+search.replace('"','""')+'"'
                qlike=f'%{search.lower()}%'
                if DATABASE_URL:
                    where.append("(l.search_vector @@ plainto_tsquery('simple', ?) OR lower(g.name) LIKE ? OR lower(s.shop_name) LIKE ? OR lower(l.platform) LIKE ? OR lower(l.region) LIKE ? OR lower(l.attributes_json) LIKE ?)"); args += [search,qlike,qlike,qlike,qlike,qlike]
                else:
                    where.append('(l.rowid IN (SELECT rowid FROM listing_search WHERE listing_search MATCH ?) OR lower(g.name) LIKE ? OR lower(s.shop_name) LIKE ? OR lower(l.platform) LIKE ? OR lower(l.region) LIKE ? OR lower(l.attributes_json) LIKE ?)'); args += [phrase,qlike,qlike,qlike,qlike,qlike]
            low=qs.get('min',[''])[0]; high=qs.get('max',[''])[0]
            try:
                if low: where.append('l.price_minor>=?'); args.append(max(0,int(low)))
                if high: where.append('l.price_minor<=?'); args.append(max(0,int(high)))
            except ValueError: raise HttpError(400,'Narx filtri butun son bo‘lishi kerak.')
            sort=qs.get('sort',['newest'])[0]; order={'newest':'l.created_at DESC','price_asc':'l.price_minor ASC','price_desc':'l.price_minor DESC','popular':'(SELECT COUNT(*) FROM order_items oi WHERE oi.listing_id=l.id) DESC,l.created_at DESC'}.get(sort,'l.created_at DESC')
            try: page=max(1,min(10000,int(qs.get('page',['1'])[0])))
            except ValueError: page=1
            limit=24
            count=db.execute(f"SELECT COUNT(*) n FROM listings l JOIN games g ON g.id=l.game_id JOIN categories c ON c.id=l.category_id JOIN seller_profiles s ON s.user_id=l.seller_id WHERE {' AND '.join(where)} AND l.stock>l.reserved",tuple(args)).fetchone()['n']
            rows=db.execute(f"SELECT l.id,l.title,l.description,l.product_type,l.price_minor,l.currency,l.platform,l.region,l.attributes_json,l.delivery_eta,l.stock,l.reserved,(l.stock-l.reserved) available,l.image_url,l.created_at,g.name game_name,g.slug game_slug,c.name category_name,s.shop_name seller_name,s.verification_status,CASE WHEN s.identity_provider='didit' AND s.identity_status='verified' THEN 1 ELSE 0 END AS identity_verified,EXISTS(SELECT 1 FROM favorites fv WHERE fv.user_id=? AND fv.listing_id=l.id) AS is_favorite,(SELECT COUNT(*) FROM reviews rv WHERE rv.seller_id=l.seller_id) review_count,(SELECT AVG(rating) FROM reviews rv WHERE rv.seller_id=l.seller_id) seller_rating FROM listings l JOIN games g ON g.id=l.game_id JOIN categories c ON c.id=l.category_id JOIN seller_profiles s ON s.user_id=l.seller_id WHERE {' AND '.join(where)} AND l.stock>l.reserved ORDER BY {order} LIMIT ? OFFSET ?",(uid or '',*args,limit,(page-1)*limit)).fetchall()
            items=[dict(x) for x in rows]
            for item in items:
                try: attributes=json.loads(item.pop('attributes_json') or '{}')
                except (TypeError,ValueError): attributes={}
                item['attributes']={key:value for key,value in attributes.items() if isinstance(key,str) and not key.startswith('_')} if isinstance(attributes,dict) else {}
            return {'items':items,'total_count':count,'page':page,'page_size':limit,'has_more':page*limit<count}
        if path.startswith('/api/listings/') and method=='GET':
            lid=path.split('/')[-1]; item=listing_detail(db,lid,uid)
            if not item or (item['status']!='published' and item['seller_id']!=uid and not (uid and is_admin(db,uid))): raise HttpError(404,'E’lon topilmadi.')
            if item['status']=='published' and not listing_allowed_for_production(db,item['game_id'],item['product_type']): raise HttpError(404,'E’lon topilmadi.')
            item.pop('seller_id',None)
            item['related']=[dict(x) for x in db.execute('SELECT id,title,price_minor,currency FROM listings WHERE game_id=? AND status=\'published\' AND id<>? ORDER BY created_at DESC LIMIT 4',(item['game_id'],lid))]
            return item
        if path=='/api/cart' and method=='GET':
            require_user(ctx)
            items=[]
            for x in db.execute('SELECT c.listing_id,c.quantity FROM carts c WHERE c.user_id=?',(uid,)):
                v=listing_detail(db,x['listing_id'],uid)
                if v and v['status']=='published': v['quantity']=x['quantity']; items.append(v)
            return {'items':items,'subtotal_minor':sum(x['price_minor']*x['quantity'] for x in items)}
        if path=='/api/orders' and method=='GET':
            require_user(ctx)
            rows=db.execute('SELECT DISTINCT o.* FROM orders o LEFT JOIN order_items i ON i.order_id=o.id WHERE o.buyer_id=? OR i.seller_id=? ORDER BY o.created_at DESC',(uid,uid)).fetchall()
            return [order_view(db,x['id'],uid) for x in rows]
        if path.startswith('/api/orders/') and method=='GET':
            require_user(ctx); oid=path.split('/')[-1]; out=order_view(db,oid,uid,is_admin(db,uid))
            if not out: raise HttpError(404,'Buyurtma topilmadi.')
            return out
        evidence_match=re.fullmatch(r'/api/orders/([^/]+)/account-evidence/([12])',path)
        if evidence_match and method=='POST':
            require_verified(ctx); oid,slot=evidence_match.group(1),int(evidence_match.group(2)); check_rate(db,'account_evidence',uid,12,3600)
            order=db.execute('SELECT * FROM orders WHERE id=? AND buyer_id=?',(oid,uid)).fetchone()
            if not order: raise HttpError(404,'Buyurtma topilmadi.')
            if order['status'] not in ('awaiting_delivery','delivered','under_review'): raise HttpError(409,'Skrinshotni buyurtma yetkazilgandan keyin yuklang.')
            if not db.execute("SELECT 1 FROM order_items i JOIN listings l ON l.id=i.listing_id WHERE i.order_id=? AND l.product_type='account' LIMIT 1",(oid,)).fetchone(): raise HttpError(400,'Skrinshot tekshiruvi faqat akkaunt buyurtmalariga tegishli.')
            review=db.execute('SELECT status FROM account_reviews WHERE order_id=? AND buyer_id=?',(oid,uid)).fetchone()
            if review and review['status'] not in ('collecting','needs_info'): raise HttpError(409,'Admin ko‘rigi boshlangan; dalilni endi almashtirib bo‘lmaydi.')
            object_path=upload_account_evidence(uid,oid,slot,raw_body,self.headers.get('Content-Type',''))
            if not review: db.execute("INSERT INTO account_reviews(order_id,buyer_id,status) VALUES(?,?,'collecting') ON CONFLICT(order_id) DO NOTHING",(oid,uid))
            previous=db.execute('SELECT object_path FROM account_review_evidence WHERE order_id=? AND slot=?',(oid,slot)).fetchone()
            db.execute('INSERT INTO account_review_evidence(order_id,slot,object_path) VALUES(?,?,?) ON CONFLICT(order_id,slot) DO UPDATE SET object_path=excluded.object_path,uploaded_at=CURRENT_TIMESTAMP',(oid,slot,object_path))
            if previous and previous['object_path']!=object_path: delete_account_evidence_object(previous['object_path'])
            return {'slot':slot,'uploaded':True}
        m=re.fullmatch(r'/api/orders/([^/]+)/account-verification/submit',path)
        if m and method=='POST':
            require_verified(ctx); oid=m.group(1)
            if data.get('confirm_privacy') is not True: raise HttpError(400,'Skrinshotlarda parol, OTP, tiklash kodi yoki begona shaxsiy ma’lumot yo‘qligini tasdiqlang.')
            db.execute('BEGIN IMMEDIATE')
            try:
                order=db.execute('SELECT * FROM orders WHERE id=? AND buyer_id=?',(oid,uid)).fetchone()
                if not order: raise HttpError(404,'Buyurtma topilmadi.')
                if order['status'] not in ('awaiting_delivery','delivered','under_review'): raise HttpError(409,'Buyurtma akkaunt tekshiruviga tayyor emas.')
                if not db.execute("SELECT 1 FROM order_items i JOIN listings l ON l.id=i.listing_id WHERE i.order_id=? AND l.product_type='account' LIMIT 1",(oid,)).fetchone(): raise HttpError(400,'Bu buyurtmada akkaunt yo‘q.')
                slots=[r['slot'] for r in db.execute('SELECT slot FROM account_review_evidence WHERE order_id=? ORDER BY slot',(oid,)).fetchall()]
                if slots!=[1,2]: raise HttpError(400,'Davom etish uchun ikkita skrinshotni ham yuklang.')
                review=db.execute('SELECT * FROM account_reviews WHERE order_id=? AND buyer_id=?',(oid,uid)).fetchone()
                if review and review['status'] not in ('collecting','needs_info'): raise HttpError(409,'Tekshiruv allaqachon moderatorga yuborilgan.')
                db.execute("INSERT INTO account_reviews(order_id,buyer_id,status,buyer_attested_at,submitted_at) VALUES(?,?,'pending',?,?) ON CONFLICT(order_id) DO UPDATE SET status='pending',buyer_attested_at=excluded.buyer_attested_at,submitted_at=excluded.submitted_at,review_note='',reviewed_by=NULL,reviewed_at=NULL",(oid,uid,now_iso(),now_iso()))
                old=order['status']; db.execute("UPDATE orders SET status='under_review',updated_at=CURRENT_TIMESTAMP WHERE id=?",(oid,)); event(db,oid,uid,old,'under_review','Xaridor akkauntga kirishni tasdiqlovchi ikki dalil yubordi; moderator tekshiruvi kutilmoqda.')
                for admin in db.execute('SELECT user_id FROM admin_accounts').fetchall(): notify(db,admin['user_id'],'account_review','Akkaunt xaridi tekshiruvi',f'{order["reference"]} uchun xaridor dalillari ko‘rib chiqilishi kerak.','/admin')
                for seller in db.execute('SELECT DISTINCT seller_id FROM order_items WHERE order_id=?',(oid,)).fetchall(): notify(db,seller['seller_id'],'account_review','Akkaunt xaridi ko‘rib chiqilmoqda',f'{order["reference"]} buyurtmasi admin tekshiruvini kutmoqda.','/orders')
                db.execute('COMMIT'); return {'status':'under_review'}
            except Exception:
                db.execute('ROLLBACK'); raise
        if path=='/api/seller/listings' and method=='GET':
            require_user(ctx); seller_ok(db,uid)
            return [listing_detail(db,x['id'],uid) for x in db.execute('SELECT id FROM listings WHERE seller_id=? ORDER BY updated_at DESC',(uid,))]
        if path=='/api/seller/summary' and method=='GET':
            require_user(ctx); seller_ok(db,uid)
            # PostgreSQL SUM(bigint) returns NUMERIC (a Decimal in psycopg), which
            # the standard JSON encoder cannot serialize. Normalize aggregate
            # minor-unit amounts at the API boundary for both PostgreSQL and SQLite.
            earnings=int(db.execute("SELECT COALESCE(SUM(amount_minor),0) amount_minor FROM ledger_entries WHERE user_id=? AND entry_type IN ('seller_earning','refund_adjustment')",(uid,)).fetchone()['amount_minor'] or 0)
            paid_out=-int(db.execute("SELECT COALESCE(SUM(amount_minor),0) amount_minor FROM ledger_entries WHERE user_id=? AND entry_type='payout'",(uid,)).fetchone()['amount_minor'] or 0)
            held=int(db.execute("SELECT COALESCE(SUM(amount_minor),0) amount_minor FROM ledger_entries WHERE user_id=? AND entry_type IN ('escrow_hold','escrow_release')",(uid,)).fetchone()['amount_minor'] or 0)
            pending_payout=int(db.execute("SELECT COALESCE(SUM(amount_minor),0) amount_minor FROM payout_requests WHERE seller_id=? AND status IN ('pending','approved')",(uid,)).fetchone()['amount_minor'] or 0)
            wallet_balance=earnings-paid_out
            return {'listings':[dict(x) for x in db.execute('SELECT status,COUNT(*) count FROM listings WHERE seller_id=? GROUP BY status',(uid,)).fetchall()],'orders':[dict(x) for x in db.execute('SELECT o.status,COUNT(DISTINCT o.id) count FROM orders o JOIN order_items i ON i.order_id=o.id WHERE i.seller_id=? GROUP BY o.status',(uid,)).fetchall()],'earnings':earnings,'wallet':{'currency':'UZS','held_minor':held,'available_minor':max(0,wallet_balance-pending_payout),'pending_payout_minor':pending_payout,'paid_out_minor':paid_out,'automated_withdrawals_enabled':False}}
        if path=='/api/requests' and method=='GET':
            own=qs.get('mine',['0'])[0]=='1'
            if own: require_user(ctx)
            expiry_filter='(r.expires_at IS NULL OR r.expires_at::timestamptz>CURRENT_TIMESTAMP)' if DATABASE_URL else '(r.expires_at IS NULL OR r.expires_at>CURRENT_TIMESTAMP)'
            where=f"r.status='open' AND {expiry_filter}"; args=[uid or '']
            if own: where+=' AND r.requester_id=?';args.append(uid)
            rows=db.execute(f"SELECT r.id,r.game_id,r.category_id,r.title,r.description,r.budget_minor,r.currency,r.expires_at,r.status,r.created_at,CASE WHEN r.requester_id=? THEN 1 ELSE 0 END is_own,'Xaridor' requester,g.name game_name,c.name category_name FROM product_requests r JOIN games g ON g.id=r.game_id LEFT JOIN categories c ON c.id=r.category_id WHERE {where} ORDER BY r.created_at DESC LIMIT 100",args).fetchall()
            return [dict(x) for x in rows]
        m=re.fullmatch(r'/api/requests/([^/]+)/responses',path)
        if m and method=='GET':
            require_user(ctx); req=db.execute('SELECT requester_id FROM product_requests WHERE id=?',(m.group(1),)).fetchone()
            if not req: raise HttpError(404,'So‘rov topilmadi.')
            rows=db.execute('SELECT rr.id,rr.seller_id,rr.message,rr.listing_id,rr.created_at,COALESCE(sp.shop_name,u.display_name) seller_name FROM request_responses rr JOIN users u ON u.id=rr.seller_id LEFT JOIN seller_profiles sp ON sp.user_id=rr.seller_id WHERE rr.request_id=? ORDER BY rr.created_at',(m.group(1),)).fetchall()
            if uid!=req['requester_id'] and not is_admin(db,uid):
                rows=[x for x in rows if x['seller_id']==uid]
                if not rows: raise HttpError(403,'Bu so‘rov javoblarini ko‘rish huquqingiz yo‘q.')
            return [dict(x) for x in rows]
        if path=='/api/conversations' and method=='GET':
            require_user(ctx)
            rows=db.execute('SELECT c.*,l.title listing_title, CASE WHEN c.buyer_id=? THEN su.display_name ELSE bu.display_name END other_name,(SELECT body FROM messages m WHERE m.conversation_id=c.id ORDER BY created_at DESC LIMIT 1) last_message,(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id AND m.sender_id<>? AND m.read_at IS NULL) unread FROM conversations c LEFT JOIN listings l ON l.id=c.listing_id JOIN users su ON su.id=c.seller_id JOIN users bu ON bu.id=c.buyer_id WHERE c.buyer_id=? OR c.seller_id=? ORDER BY c.created_at DESC',(uid,uid,uid,uid)).fetchall()
            return [dict(x) for x in rows]
        if path.startswith('/api/conversations/') and method=='GET':
            require_user(ctx); cid=path.split('/')[-1]; conv=db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone()
            if not conv or uid not in (conv['buyer_id'],conv['seller_id']) and not is_admin(db,uid): raise HttpError(404,'Suhbat topilmadi.')
            db.execute('UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND sender_id<>?',(cid,uid))
            return {'conversation':dict(conv),'messages':[dict(x) for x in db.execute('SELECT id,sender_id,body,created_at,read_at FROM messages WHERE conversation_id=? ORDER BY created_at LIMIT 200',(cid,))]}
        m=re.fullmatch(r'/api/notifications/([^/]+)/read',path)
        if m and method=='POST':
            require_user(ctx); db.execute('UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',(m.group(1),uid)); return {'ok':True}
        if path=='/api/notifications/read-all' and method=='POST':
            require_user(ctx); db.execute('UPDATE notifications SET read_at=CURRENT_TIMESTAMP WHERE user_id=? AND read_at IS NULL',(uid,)); return {'ok':True}
        if path=='/api/notifications' and method=='GET':
            require_user(ctx); return [dict(x) for x in db.execute('SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 50',(uid,))]
        if path=='/api/favorites' and method=='GET':
            require_user(ctx); return [listing_detail(db,x['listing_id'],uid) for x in db.execute('SELECT listing_id FROM favorites WHERE user_id=? ORDER BY created_at DESC',(uid,))]
        if path=='/api/admin/top-up' and method=='GET':
            require_admin(ctx)
            packages=[dict(x) for x in db.execute('SELECT p.*,COALESCE((SELECT SUM(o.quantity) FROM topup_orders o WHERE o.package_id=p.id),0) order_count FROM topup_packages p ORDER BY p.game_name,p.amount')]
            orders=[dict(x) for x in db.execute('SELECT o.*,u.email buyer_email,p.game_name,p.currency package_currency,p.amount FROM topup_orders o JOIN users u ON u.id=o.buyer_id JOIN topup_packages p ON p.id=o.package_id ORDER BY o.created_at DESC LIMIT 100')]
            return {'packages':packages,'orders':orders,'supplier':{'configured':False,'provider':'','message':'Ta’minotchi API tanlanmagan.'},'payments':{'configured':False,'provider':'disabled'}}
        if path=='/api/admin/top-up/packages' and method=='POST':
            aid=require_admin(ctx)
            game_slug=clean_text(data.get('game_slug'),'O‘yin manzili',2,80).lower()
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',game_slug): raise HttpError(400,'O‘yin manzili kichik lotin harflari va tirelardan iborat bo‘lsin.')
            game_name=clean_text(data.get('game_name'),'O‘yin nomi',2,100)
            currency=clean_text(data.get('currency'),'Valyuta turi',2,20)
            if not re.fullmatch(r'[A-Za-z0-9 -]{2,20}',currency): raise HttpError(400,'Valyuta turi harf va raqamlardan iborat bo‘lsin.')
            amount=data.get('amount')
            if not isinstance(amount,int) or isinstance(amount,bool) or amount<1 or amount>1000000000: raise HttpError(400,'Paket miqdori noto‘g‘ri.')
            url_slug=clean_text(data.get('url_slug'),'Paket URL manzili',2,100).lower()
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',url_slug): raise HttpError(400,'Paket manzili kichik lotin harflari, raqam va tirelardan iborat bo‘lsin.')
            price=data.get('price_minor',0)
            if not isinstance(price,int) or isinstance(price,bool) or price<0 or price>1000000000000: raise HttpError(400,'Narx miqdori noto‘g‘ri.')
            coming_soon=data.get('coming_soon',True)
            if not isinstance(coming_soon,bool): raise HttpError(400,'Coming Soon holati noto‘g‘ri.')
            existing=db.execute('SELECT game_name,currency FROM topup_packages WHERE game_slug=? LIMIT 1',(game_slug,)).fetchone()
            if existing and (existing['game_name']!=game_name or existing['currency'].casefold()!=currency.casefold()):
                raise HttpError(409,'Bu o‘yin manzili uchun nom va valyuta avvaldan belgilangan.')
            package_id=game_slug+'-'+url_slug
            db.execute('INSERT INTO topup_packages(id,game_slug,game_name,url_slug,currency,amount,price_minor,enabled,coming_soon,manual_enabled) VALUES(?,?,?,?,?,?,?,1,?,1)',(package_id,game_slug,game_name,url_slug,currency,amount,price,int(coming_soon)))
            audit(db,aid,'topup_package_create','topup_package',package_id,{'game_slug':game_slug,'amount':amount,'currency':currency,'price_minor':price,'coming_soon':coming_soon})
            return 201,{'ok':True,'package':dict(db.execute('SELECT * FROM topup_packages WHERE id=?',(package_id,)).fetchone())}
        admin_topup_package=re.fullmatch(r'/api/admin/top-up/packages/([a-z0-9-]+)',path)
        if admin_topup_package and method=='PATCH':
            aid=require_admin(ctx); package_id=admin_topup_package.group(1)
            package=db.execute('SELECT * FROM topup_packages WHERE id=?',(package_id,)).fetchone()
            if not package: raise HttpError(404,'Top Up paketi topilmadi.')
            fields={}
            if 'price_minor' in data:
                price=data['price_minor']
                if not isinstance(price,int) or isinstance(price,bool) or price<0 or price>1000000000000: raise HttpError(400,'Narx 0 yoki undan katta UZS miqdori bo‘lishi kerak.')
                fields['price_minor']=price
            if 'enabled' in data:
                if not isinstance(data['enabled'],bool): raise HttpError(400,'Faollik qiymati noto‘g‘ri.')
                fields['enabled']=int(data['enabled'])
            if 'manual_enabled' in data:
                if not isinstance(data['manual_enabled'],bool): raise HttpError(400,'Qo‘lda yetkazish qiymati noto‘g‘ri.')
                fields['manual_enabled']=int(data['manual_enabled'])
            if 'coming_soon' in data:
                if not isinstance(data['coming_soon'],bool): raise HttpError(400,'Coming Soon holati noto‘g‘ri.')
                fields['coming_soon']=int(data['coming_soon'])
            if not fields: raise HttpError(400,'Saqlash uchun o‘zgarish topilmadi.')
            assignments=','.join(f'{key}=?' for key in fields)
            db.execute(f'UPDATE topup_packages SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?',(*fields.values(),package_id))
            audit(db,aid,'topup_package_update','topup_package',package_id,fields)
            return {'ok':True,'package':dict(db.execute('SELECT * FROM topup_packages WHERE id=?',(package_id,)).fetchone())}
        if path=='/api/admin/top-up/inventory' and method=='POST':
            aid=require_admin(ctx); package_id=clean_text(data.get('package_id'),'Paket',1,160)
            delta=data.get('delta'); reason=clean_text(data.get('reason'),'Izoh',3,240)
            if not isinstance(delta,int) or isinstance(delta,bool) or delta==0 or abs(delta)>100000: raise HttpError(400,'Ombor o‘zgarishi 1–100000 oralig‘ida bo‘lishi kerak.')
            package=db.execute('SELECT * FROM topup_packages WHERE id=?',(package_id,)).fetchone()
            if not package: raise HttpError(404,'Top Up paketi topilmadi.')
            next_stock=package['stock_on_hand']+delta
            if next_stock<package['stock_reserved']: raise HttpError(409,'Yangi qoldiq band qilingan miqdordan kam bo‘la olmaydi.')
            db.execute('UPDATE topup_packages SET stock_on_hand=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(next_stock,package_id))
            db.execute('INSERT INTO topup_inventory_events(id,package_id,actor_id,delta,reason) VALUES(?,?,?,?,?)',(ident(),package_id,aid,delta,reason))
            audit(db,aid,'topup_inventory_adjust','topup_package',package_id,{'delta':delta,'reason':reason,'stock_on_hand':next_stock})
            return {'ok':True,'stock_on_hand':next_stock,'available':next_stock-package['stock_reserved']}
        if path=='/api/admin/overview' and method=='GET':
            require_admin(ctx)
            return {
                'pending_listings':db.execute("SELECT COUNT(*) n FROM listings WHERE status='pending_review'").fetchone()['n'],
                'open_reports':db.execute("SELECT COUNT(*) n FROM reports WHERE status='open' AND reason!='order_dispute'").fetchone()['n'],
                'open_disputes':db.execute("SELECT COUNT(*) n FROM reports WHERE reason='order_dispute' AND status IN ('open','reviewing')").fetchone()['n'],
                'pending_payouts':db.execute("SELECT COUNT(*) n FROM payout_requests WHERE status IN ('pending','approved')").fetchone()['n'],
                'pending_sellers':db.execute("SELECT COUNT(*) n FROM seller_profiles WHERE verification_status!='verified' OR selling_enabled=0").fetchone()['n'],
                'active_listings':db.execute("SELECT COUNT(*) n FROM listings WHERE status='published'").fetchone()['n'],
                'today_orders':db.execute("SELECT COUNT(*) n FROM orders WHERE created_at::date=CURRENT_DATE" if DATABASE_URL else "SELECT COUNT(*) n FROM orders WHERE date(created_at)=date('now')").fetchone()['n'],
                'completed_orders':db.execute("SELECT COUNT(*) n FROM orders WHERE status='completed'").fetchone()['n'],
                'sandbox_volume_minor':int(db.execute("SELECT COALESCE(SUM(amount_minor),0) n FROM payments WHERE provider='sandbox' AND status='succeeded'").fetchone()['n']),
                'daily_orders':[dict(x) for x in db.execute("SELECT to_char(created_at::date,'YYYY-MM-DD') AS day,COUNT(*) AS count FROM orders WHERE created_at::date>=CURRENT_DATE-6 GROUP BY created_at::date ORDER BY created_at::date" if DATABASE_URL else "SELECT date(created_at) AS day,COUNT(*) AS count FROM orders WHERE date(created_at)>=date('now','-6 day') GROUP BY date(created_at) ORDER BY date(created_at)").fetchall()],
                'orders':[dict(x) for x in db.execute('SELECT status,COUNT(*) n FROM orders GROUP BY status').fetchall()],
                'users':db.execute('SELECT COUNT(*) n FROM users').fetchone()['n'],
                'mode':MODE,
                'config':{r['key']:r['value'] for r in db.execute('SELECT key,value FROM platform_config')}
            }
        if path=='/api/admin/blog' and method=='GET':
            require_admin(ctx)
            return [blog_post_view(x) for x in db.execute('SELECT * FROM blog_posts ORDER BY updated_at DESC LIMIT 200')]
        if path=='/api/admin/listings' and method=='GET':
            require_admin(ctx); return [listing_detail(db,x['id'],uid) for x in db.execute("SELECT id FROM listings WHERE status IN ('pending_review','rejected','published','paused') ORDER BY CASE status WHEN 'pending_review' THEN 0 WHEN 'rejected' THEN 1 WHEN 'published' THEN 2 ELSE 3 END,updated_at DESC LIMIT 200")]
        if path=='/api/admin/reports' and method=='GET':
            require_admin(ctx); return [dict(x) for x in db.execute('SELECT r.*,u.email reporter_email FROM reports r JOIN users u ON u.id=r.reporter_id ORDER BY CASE r.status WHEN \'open\' THEN 0 ELSE 1 END,r.created_at DESC LIMIT 100')]
        if path=='/api/admin/sellers' and method=='GET':
            require_admin(ctx); return [dict(x) for x in db.execute("SELECT s.user_id,s.shop_name,s.bio,s.verification_status,s.selling_enabled,s.identity_status,s.identity_provider,s.identity_verified_at,s.created_at,u.email,u.display_name FROM seller_profiles s JOIN users u ON u.id=s.user_id WHERE s.verification_status!='verified' OR s.selling_enabled=0 OR s.identity_status!='verified' OR s.identity_provider!='didit' ORDER BY CASE s.identity_status WHEN 'verified' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,s.created_at DESC LIMIT 100")]
        if path=='/api/admin/disputes' and method=='GET':
            require_admin(ctx)
            if DATABASE_URL:
                report_sql="SELECT r.id report_id,r.details,r.status report_status,r.resolution,r.created_at,o.id order_id,o.reference,o.status order_status,o.total_minor,o.currency,o.buyer_id,b.email buyer_email,p.provider payment_provider,p.status payment_status,sellers.seller_emails FROM reports r JOIN orders o ON o.id=r.order_id JOIN users b ON b.id=o.buyer_id LEFT JOIN payments p ON p.order_id=o.id LEFT JOIN LATERAL (SELECT string_agg(DISTINCT su.email, ', ') seller_emails FROM order_items i JOIN users su ON su.id=i.seller_id WHERE i.order_id=o.id) sellers ON TRUE WHERE r.reason='order_dispute' AND r.status IN ('open','reviewing') ORDER BY r.created_at LIMIT 100"
            else:
                report_sql="SELECT r.id report_id,r.details,r.status report_status,r.resolution,r.created_at,o.id order_id,o.reference,o.status order_status,o.total_minor,o.currency,o.buyer_id,b.email buyer_email,p.provider payment_provider,p.status payment_status,GROUP_CONCAT(DISTINCT su.email) seller_emails FROM reports r JOIN orders o ON o.id=r.order_id JOIN users b ON b.id=o.buyer_id LEFT JOIN payments p ON p.order_id=o.id LEFT JOIN order_items i ON i.order_id=o.id LEFT JOIN users su ON su.id=i.seller_id WHERE r.reason='order_dispute' AND r.status IN ('open','reviewing') GROUP BY r.id ORDER BY r.created_at LIMIT 100"
            return [dict(x) for x in db.execute(report_sql)]
        if path=='/api/admin/account-reviews' and method=='GET':
            require_admin(ctx)
            rows=db.execute("SELECT ar.order_id,ar.buyer_id,ar.status,ar.buyer_attested_at,ar.submitted_at,o.reference,o.total_minor,o.currency,u.email buyer_email,u.display_name buyer_name FROM account_reviews ar JOIN orders o ON o.id=ar.order_id JOIN users u ON u.id=ar.buyer_id WHERE ar.status='pending' ORDER BY ar.submitted_at LIMIT 100").fetchall()
            try:
                if not rows: raise HttpError(503,'No evidence to review.')
                require_private_evidence_bucket(); storage_private=True
            except HttpError: storage_private=False
            result=[]
            for row in rows:
                item=dict(row); item['evidence']=[]
                for evidence in db.execute('SELECT slot,object_path,uploaded_at FROM account_review_evidence WHERE order_id=? ORDER BY slot',(row['order_id'],)).fetchall():
                    try:
                        if not storage_private: raise HttpError(503,'Evidence bucket is not private.')
                        signed_url=signed_account_evidence_url(evidence['object_path'])
                    except HttpError: signed_url=None
                    item['evidence'].append({'slot':evidence['slot'],'uploaded_at':evidence['uploaded_at'],'url':signed_url})
                if len(item['evidence'])==2: result.append(item)
            return result
        if path=='/api/admin/deletions' and method=='GET':
            require_admin(ctx); return [dict(x) for x in db.execute('SELECT d.*,u.email,u.display_name FROM account_deletion_requests d JOIN users u ON u.id=d.user_id ORDER BY d.created_at DESC LIMIT 100')]
        if path=='/api/admin/payouts' and method=='GET':
            require_admin(ctx); return [dict(x) for x in db.execute('SELECT p.*,u.email,u.display_name FROM payout_requests p JOIN users u ON u.id=p.seller_id ORDER BY p.created_at DESC LIMIT 100')]

        # Write workflows below.
        if path=='/api/account/deletion-request' and method=='POST':
            require_verified(ctx); reason=clean_text(data.get('reason',''),'Sabab',0,1000)
            existing=db.execute("SELECT id,status FROM account_deletion_requests WHERE user_id=? AND status IN ('pending','reviewing') ORDER BY created_at DESC LIMIT 1",(uid,)).fetchone()
            if existing: return {'id':existing['id'],'status':existing['status']}
            rid=ident(); db.execute('INSERT INTO account_deletion_requests(id,user_id,reason) VALUES(?,?,?)',(rid,uid,reason)); audit(db,uid,'account_deletion_request','user',uid); return 201,{'id':rid,'status':'pending'}
        if path=='/api/profile' and method=='POST':
            require_user(ctx)
            fields={}
            if 'display_name' in data: fields['display_name']=clean_text(data['display_name'],'Ism',2,80)
            if 'language' in data:
                if data['language'] not in SUPPORTED_LANGUAGES: raise HttpError(400,'Til tanlovi noto‘g‘ri.')
                fields['language']=data['language']
            if 'country' in data:
                if not isinstance(data['country'],str) or data['country'] not in ASIA_COUNTRIES: raise HttpError(400,'Osiyo mamlakatini tanlang.')
                fields['country']=data['country']
            if 'currency' in data:
                if not isinstance(data['currency'],str) or data['currency'] not in ASIA_CURRENCIES: raise HttpError(400,'Osiyo valyutasini tanlang.')
                fields['currency']=data['currency']
            if fields: db.execute('UPDATE users SET '+', '.join(f'{k}=?' for k in fields)+' WHERE id=?',(*fields.values(),uid))
            return {'user':user_view(db,uid)}
        if path=='/api/seller/identity-session' and method=='POST':
            require_verified(ctx)
            if data.get('consent') is not True: raise HttpError(400,'Didit’ga ma’lumot yuborish uchun rozilikni belgilang.')
            if not identity_service.is_configured(): raise HttpError(503,'Didit hali ulanmagan. Serverda API key, workflow ID va webhook secret sozlanishi kerak.')
            check_rate(db,'didit_session',uid,5,3600)
            user=db.execute('SELECT email FROM users WHERE id=? AND email_verified=1 AND suspended=0',(uid,)).fetchone()
            profile=db.execute('SELECT * FROM seller_profiles WHERE user_id=?',(uid,)).fetchone()
            if not user or not profile: raise HttpError(409,'Avval emailni tasdiqlab, sotuvchi profilini yarating.')
            if profile['identity_status']=='verified' and profile['identity_provider']=='didit': raise HttpError(409,'Shaxs Didit orqali tasdiqlangan.')
            reference='sl-'+hmac.new(SESSION_SECRET.encode('utf-8'),('didit-user:'+uid).encode('utf-8'),hashlib.sha256).hexdigest()[:40]
            try: session=identity_service.create_verification_session(reference)
            except identity_service.IdentityProviderError as exc: raise HttpError(503,str(exc))
            consent_version='kyc-consent-v1'
            db.execute("UPDATE seller_profiles SET identity_reference=?,identity_provider='didit',identity_status='pending',identity_verified_at=NULL,identity_last_event_at=NULL,identity_consent_at=?,identity_consent_version=? WHERE user_id=?",(session['session_id'],now_iso(),consent_version,uid))
            audit(db,uid,'didit_identity_started','seller',uid,{'provider':'didit','consent_version':consent_version})
            return {'url':session['url'],'status':'pending'}
        if path=='/api/seller' and method=='POST':
            require_verified(ctx); name=clean_text(data.get('shop_name'),'Do‘kon nomi',2,80); bio=clean_text(data.get('bio',''),'Tavsif',0,1000)
            db.execute("INSERT INTO seller_profiles(user_id,shop_name,bio,verification_status,selling_enabled) VALUES(?,?,?,'pending',0) ON CONFLICT(user_id) DO UPDATE SET shop_name=excluded.shop_name,bio=excluded.bio",(uid,name,bio))
            audit(db,uid,'seller_onboard','seller',uid); profile=rowdict(db.execute('SELECT shop_name,bio,verification_status,selling_enabled,identity_status,identity_provider FROM seller_profiles WHERE user_id=?',(uid,)).fetchone())
            if profile['verification_status']=='pending':
                for admin in db.execute('SELECT user_id FROM admin_accounts').fetchall(): notify(db,admin['user_id'],'seller_review','Sotuvchi tasdig‘i kutilmoqda',f'{name} do‘koni tekshiruvga yuborildi.','/admin')
            return {'seller':profile}
        if path=='/api/listing-images' and method=='POST':
            require_verified(ctx); seller_ok(db,uid); check_rate(db,'listing_image_upload',uid,30,3600)
            if not production_marketplace_sales_enabled(): raise HttpError(503,'Ishlab chiqarishda savdo uchun to‘lov va huquqiy talablar yakunlanmaguncha e’lon rasmi yuklash yopiq.')
            if not SUPABASE_URL.startswith('https://') or not SUPABASE_SERVICE_ROLE_KEY or not re.fullmatch(r'[a-z0-9_-]{1,100}',SUPABASE_LISTING_IMAGES_BUCKET):
                raise HttpError(503,'Rasm yuklash serverda sozlanmagan. Supabase Storage sozlamalari kerak.')
            if not raw_body or len(raw_body)>MAX_IMAGE_BODY: raise HttpError(413,'Rasm 5 MB dan kichik bo‘lishi kerak.')
            mime=self.headers.get('Content-Type','').split(';',1)[0].strip().lower()
            image_formats={'image/jpeg':'JPEG','image/png':'PNG','image/webp':'WEBP'}
            if mime not in image_formats: raise HttpError(415,'Faqat JPG, PNG yoki WebP rasm yuklash mumkin.')
            try:
                import warnings
                from PIL import Image, ImageOps
                Image.MAX_IMAGE_PIXELS=25_000_000
                with warnings.catch_warnings():
                    warnings.simplefilter('error',Image.DecompressionBombWarning)
                    image=Image.open(io.BytesIO(raw_body))
                    if image.format!=image_formats[mime] or getattr(image,'is_animated',False): raise HttpError(415,'Rasm formati fayl mazmuniga mos emas yoki animatsiyali rasm qo‘llanmaydi.')
                    if image.width*image.height>25_000_000: raise HttpError(413,'Rasm o‘lchami juda katta.')
                    image.load()
                    image=ImageOps.exif_transpose(image).convert('RGB')
                    image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
                    optimized=io.BytesIO(); image.save(optimized,format='WEBP',quality=82,method=5)
                    image_bytes=optimized.getvalue()
            except HttpError: raise
            except ImportError: raise HttpError(503,'Serverda rasmni xavfsiz qayta ishlash kutubxonasi yo‘q.')
            except Image.DecompressionBombError: raise HttpError(413,'Rasm o‘lchami juda katta.')
            except Exception: raise HttpError(400,'Rasm fayli yaroqsiz yoki buzilgan.')
            object_path=f"{hashlib.sha256(str(uid).encode()).hexdigest()[:20]}/{secrets.token_hex(20)}.webp"
            bucket_path=urlquote(SUPABASE_LISTING_IMAGES_BUCKET,safe='')+'/'+urlquote(object_path,safe='/')
            storage_request=UrlRequest(f'{SUPABASE_URL}/storage/v1/object/{bucket_path}',data=image_bytes,method='POST',headers={'Authorization':f'Bearer {SUPABASE_SERVICE_ROLE_KEY}','apikey':SUPABASE_SERVICE_ROLE_KEY,'Content-Type':'image/webp','Cache-Control':'public, max-age=31536000, immutable','x-upsert':'false'})
            try:
                with urlopen_request(storage_request,timeout=15) as response:
                    if response.status not in (200,201): raise HttpError(502,'Rasm storage xizmatiga yuklanmadi.')
            except UrlHTTPError: raise HttpError(502,'Rasm storage xizmatiga yuklanmadi.')
            except UrlURLError: raise HttpError(503,'Rasm storage xizmatiga ulanish vaqtincha ishlamayapti.')
            public_url=f'{SUPABASE_URL}/storage/v1/object/public/{bucket_path}'
            return 201,{'url':public_url,'content_type':'image/webp','size':len(image_bytes)}
        if path=='/api/listings' and method=='POST':
            require_verified(ctx); seller_ok(db,uid); check_rate(db,'listing_create',uid,30,3600)
            submit_for_review=data.get('submit_for_review',False)
            if not isinstance(submit_for_review,bool): raise HttpError(400,'Tekshiruvga yuborish belgisi noto‘g‘ri.')
            game_name=clean_text(data.get('game_name') if data.get('game_name') is not None else data.get('game_id'),'O‘yin nomi',2,80); cat=clean_text(data.get('category_id'),'Kategoriya',1,80)
            if not db.execute('SELECT 1 FROM categories WHERE id=? AND active=1',(cat,)).fetchone(): raise HttpError(400,'Kategoriya topilmadi.')
            title=clean_text(data.get('title'),'Sarlavha',5,120); desc=clean_text(data.get('description'),'Tavsif',20,5000); price=money(data.get('price_minor'))
            stock=data.get('stock',1)
            if not isinstance(stock,int) or stock<0 or stock>10000: raise HttpError(400,'Qoldiq miqdori noto‘g‘ri.')
            typ=db.execute('SELECT product_type FROM categories WHERE id=?',(cat,)).fetchone()['product_type']
            if typ=='account' and data.get('accept_account_terms') is not True:
                raise HttpError(400,'Akkaunt e’lonidan oldin egalik, noshir qoidalari va taqiqlangan holatlar bo‘yicha sotuvchi tasdig‘i kerak.')
            attributes=data.get('attributes',{})
            if not isinstance(attributes,dict) or len(attributes)>30: raise HttpError(400,'Atributlar noto‘g‘ri.')
            images=listing_image_urls(data.get('images',[data.get('image_url')]) if 'images' not in data and data.get('image_url') else data.get('images',[]))
            providers=linked_account_providers(data.get('linked_accounts',attributes.get('linked_accounts',[])))
            if 'server' in attributes: attributes['server']=clean_text(attributes['server'],'Server',0,60)
            attributes={**attributes,'images':images,'linked_accounts':providers}
            image_url=images[0] if images else ''
            if data.get('delivery_method','manual') not in ('manual','protected_text','file','code','service'): raise HttpError(400,'Yetkazish turi noto‘g‘ri.')
            platform=clean_text(data.get('platform',''),'Platforma',0,60); region=clean_text(data.get('region',''),'Hudud',0,60)
            delivery_eta=clean_text(data.get('delivery_eta','24 hours'),'Yetkazish muddati',2,60); requirements=clean_text(data.get('requirements',''),'Shartlar',0,1000)
            game=resolve_game_id(db,game_name)
            require_listing_allowed(db,game,typ)
            account_terms=ACCOUNT_SELLER_TERMS_VERSION if typ=='account' else ''
            account_terms_at=now_iso() if typ=='account' else None
            risk_flags=listing_risk_flags(db,uid,game,typ,title,desc)
            if risk_flags: attributes['_risk_flags']=risk_flags
            lid=ident(); db.execute('INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,platform,region,attributes_json,delivery_method,delivery_eta,requirements,stock,image_url,status,seller_account_terms_version,seller_account_terms_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (lid,uid,game,cat,title,desc,typ,price,platform,region,json.dumps(attributes,ensure_ascii=False),data.get('delivery_method','manual'),delivery_eta,requirements,stock,image_url,'pending_review' if submit_for_review else 'draft',account_terms,account_terms_at))
            if submit_for_review:
                admin=db.execute('SELECT user_id FROM admin_accounts LIMIT 1').fetchone()
                if admin: notify(db,admin['user_id'],'moderation','Yangi e’lon','Tekshirish uchun yangi e’lon yuborildi.','/admin')
            return 201,listing_detail(db,lid,uid)
        m=re.fullmatch(r'/api/listings/([^/]+)/state',path)
        if m and method=='POST':
            require_verified(ctx); seller_ok(db,uid); lid=m.group(1); l=db.execute('SELECT * FROM listings WHERE id=? AND seller_id=?',(lid,uid)).fetchone()
            if not l: raise HttpError(404,'E’lon topilmadi.')
            action=data.get('action')
            if action=='pause' and l['status']=='published': target='paused'
            elif action=='reopen' and l['status']=='paused':
                require_listing_allowed(db,l['game_id'],l['product_type']); target='pending_review'
                if l['product_type']=='account' and l['seller_account_terms_version']!=ACCOUNT_SELLER_TERMS_VERSION:
                    raise HttpError(400,'Akkaunt bo‘yicha yangilangan sotuvchi shartlarini tasdiqlang.')
            elif action=='archive' and l['status'] in ('draft','rejected','paused'): target='archived'
            else: raise HttpError(409,'Ushbu holatda bu amalni bajarib bo‘lmaydi.')
            db.execute('UPDATE listings SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(target,lid)); audit(db,uid,'listing_'+action,'listing',lid); return {'status':target}
        m=re.fullmatch(r'/api/listings/([^/]+)/submit',path)
        if m and method=='POST':
            require_verified(ctx); seller_ok(db,uid); lid=m.group(1); l=db.execute('SELECT * FROM listings WHERE id=? AND seller_id=?',(lid,uid)).fetchone()
            if not l: raise HttpError(404,'E’lon topilmadi.')
            if l['status'] not in ('draft','rejected','paused'): raise HttpError(409,'Bu e’lon hozir moderatsiyaga yuborilmaydi.')
            require_listing_allowed(db,l['game_id'],l['product_type'])
            if l['product_type']=='account' and l['seller_account_terms_version']!=ACCOUNT_SELLER_TERMS_VERSION:
                raise HttpError(400,'Akkaunt e’lonini yuborishdan oldin sotuvchi shartlarini tasdiqlash kerak.')
            db.execute("UPDATE listings SET status='pending_review',moderation_note='',updated_at=CURRENT_TIMESTAMP WHERE id=?",(lid,)); notify(db,next(iter([r['user_id'] for r in db.execute('SELECT user_id FROM admin_accounts LIMIT 20')]),None),'moderation','Yangi e’lon','Tekshirish uchun yangi e’lon yuborildi.','/admin'); return {'status':'pending_review'}
        m=re.fullmatch(r'/api/listings/([^/]+)',path)
        if m and method=='PATCH':
            require_verified(ctx); seller_ok(db,uid); lid=m.group(1); l=db.execute('SELECT * FROM listings WHERE id=? AND seller_id=?',(lid,uid)).fetchone()
            if not l: raise HttpError(404,'E’lon topilmadi.')
            allowed={'title','description','price_minor','platform','region','delivery_eta','requirements','stock','image_url','attributes','game_name','images','linked_accounts'}
            fields={k:data[k] for k in data if k in allowed};
            if 'game_name' in fields: fields['game_name']=clean_text(fields['game_name'],'O‘yin nomi',2,80)
            if 'title' in fields: fields['title']=clean_text(fields['title'],'Sarlavha',5,120)
            if 'description' in fields: fields['description']=clean_text(fields['description'],'Tavsif',20,5000)
            if 'price_minor' in fields: fields['price_minor']=money(fields['price_minor'])
            if 'stock' in fields and (not isinstance(fields['stock'],int) or fields['stock']<l['reserved'] or fields['stock']>10000): raise HttpError(400,'Qoldiq 0–10000 bo‘lishi va band mahsulotlardan kam bo‘lmasligi kerak.')
            for key,label,minimum,maximum in (('platform','Platforma',0,60),('region','Hudud',0,60),('delivery_eta','Yetkazish muddati',2,60),('requirements','Talablar',0,1000)):
                if key in fields: fields[key]=clean_text(fields[key],label,minimum,maximum)
            if 'image_url' in fields:
                legacy_image=clean_text(fields.pop('image_url'),'Rasm manzili',0,500)
                fields['image_url']=listing_image_urls([legacy_image])[0] if legacy_image else ''
            attrs=json.loads(l['attributes_json'] or '{}')
            if not isinstance(attrs,dict): attrs={}
            if 'image_url' in data and 'images' not in data: attrs['images']=[fields['image_url']] if fields.get('image_url') else []
            if 'attributes' in fields:
                if not isinstance(fields['attributes'],dict) or len(fields['attributes'])>30: raise HttpError(400,'Atributlar noto‘g‘ri.')
                attrs.update(fields.pop('attributes'))
                if 'server' in attrs: attrs['server']=clean_text(attrs['server'],'Server',0,60)
            if 'images' in fields:
                images=listing_image_urls(fields.pop('images')); attrs['images']=images; fields['image_url']=images[0] if images else ''
            if 'linked_accounts' in fields: attrs['linked_accounts']=linked_account_providers(fields.pop('linked_accounts'))
            if 'attributes' in data or 'images' in data or 'linked_accounts' in data or 'image_url' in data: fields['attributes_json']=json.dumps(attrs,ensure_ascii=False)
            if 'game_name' in fields: fields['game_id']=resolve_game_id(db,fields.pop('game_name'))
            next_status='pending_review' if fields and l['status']=='published' or fields.get('stock',l['stock'])>0 and l['status']=='sold_out' else None
            if 'attributes' in fields: fields['attributes_json']=json.dumps(fields.pop('attributes'),ensure_ascii=False)
            if fields:
                assignments=[f'{k}=?' for k in fields]; values=list(fields.values())
                if next_status: assignments.extend(['status=?',"moderation_note=''"]); values.append(next_status)
                assignments.append('updated_at=CURRENT_TIMESTAMP')
                db.execute(f'UPDATE listings SET {", ".join(assignments)} WHERE id=?',(*values,lid)); audit(db,uid,'listing_edit','listing',lid,{'fields':sorted(fields),'status':next_status or l['status']})
                if l['status']=='published':
                    for admin in db.execute('SELECT user_id FROM admin_accounts').fetchall(): notify(db,admin['user_id'],'moderation','Tahrirlangan e’lon tekshiruvi',f'{l["title"]} o‘zgartirildi va vaqtincha yashirildi.','/admin')
            return listing_detail(db,lid,uid)
        m=re.fullmatch(r'/api/favorites/([^/]+)',path)
        if m and method=='POST':
            require_user(ctx); lid=m.group(1)
            if not db.execute("SELECT 1 FROM listings WHERE id=? AND status='published'",(lid,)).fetchone(): raise HttpError(404,'E’lon topilmadi.')
            db.execute('INSERT OR IGNORE INTO favorites(user_id,listing_id) VALUES(?,?)',(uid,lid)); return {'saved':True}
        if m and method=='DELETE': require_user(ctx); db.execute('DELETE FROM favorites WHERE user_id=? AND listing_id=?',(uid,m.group(1))); return {'saved':False}
        if path=='/api/cart' and method=='POST':
            require_user(ctx); lid=clean_text(data.get('listing_id'),'E’lon',1,100); qty=data.get('quantity',1)
            if not isinstance(qty,int) or qty<1 or qty>100: raise HttpError(400,'Miqdor 1–100 orasida bo‘lishi kerak.')
            l=db.execute("SELECT * FROM listings WHERE id=? AND status='published'",(lid,)).fetchone()
            if not l: raise HttpError(404,'E’lon topilmadi.')
            if l['seller_id']==uid: raise HttpError(400,'O‘zingizning e’loningizni savatchaga qo‘sha olmaysiz.')
            existing=db.execute('SELECT quantity FROM carts WHERE user_id=? AND listing_id=?',(uid,lid)).fetchone(); qty+=existing['quantity'] if existing else 0
            if qty>l['stock']-l['reserved']: raise HttpError(409,'Mavjud qoldiqdan ko‘p miqdor tanlandi.')
            db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,?) ON CONFLICT(user_id,listing_id) DO UPDATE SET quantity=excluded.quantity,updated_at=CURRENT_TIMESTAMP',(uid,lid,qty)); return {'ok':True,'quantity':qty}
        m=re.fullmatch(r'/api/cart/([^/]+)',path)
        if m and method=='DELETE': require_user(ctx); db.execute('DELETE FROM carts WHERE user_id=? AND listing_id=?',(uid,m.group(1))); return {'ok':True}
        if path=='/api/checkout' and method=='POST':
            require_verified(ctx); return 201,checkout(db,uid,data.get('accept_terms') is True,data.get('accept_account_risk') is True)
        m=re.fullmatch(r'/api/orders/([^/]+)/sandbox-complete',path)
        if m and method=='POST':
            require_verified(ctx)
            if MODE!='development': raise HttpError(403,'Sandbox to‘lov faqat development rejimida ishlaydi.')
            oid=m.group(1); db.execute('BEGIN IMMEDIATE')
            try:
                o=db.execute('SELECT * FROM orders WHERE id=? AND buyer_id=?',(oid,uid)).fetchone()
                if not o: raise HttpError(404,'Buyurtma topilmadi.')
                if o['status']=='paid': db.execute('COMMIT'); return {'status':'paid','idempotent':True}
                if o['status']!='pending_payment': raise HttpError(409,'Buyurtma to‘lovga tayyor emas.')
                p=db.execute("SELECT * FROM payments WHERE order_id=? AND provider='sandbox'",(oid,)).fetchone()
                if not p or p['status']!='pending': raise HttpError(409,'Sandbox to‘lov topilmadi.')
                db.execute("UPDATE payments SET status='succeeded',provider_reference=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",('sandbox-'+secrets.token_hex(6),p['id']))
                db.execute("UPDATE orders SET status='paid',updated_at=CURRENT_TIMESTAMP WHERE id=?",(oid,)); event(db,oid,uid,'pending_payment','paid','Development sandbox payment verified on server')
                for it in db.execute('SELECT * FROM order_items WHERE order_id=?',(oid,)).fetchall():
                    db.execute("UPDATE listings SET stock=stock-?,reserved=reserved-?,status=CASE WHEN stock-?<=0 THEN 'sold_out' ELSE status END,updated_at=CURRENT_TIMESTAMP WHERE id=?",(it['quantity'],it['quantity'],it['quantity'],it['listing_id']))
                    earn=it['unit_price_minor']*it['quantity']-it['commission_minor']
                    db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,it['seller_id'],'escrow_hold',earn,o['currency'],'Sandbox mablag‘i; buyurtma tugamaguncha yechib olinmaydi'))
                    if it['commission_minor']: db.execute('INSERT INTO ledger_entries(id,order_id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?,?)',(ident(),oid,None,'escrow_fee_hold',it['commission_minor'],o['currency'],'Sandbox komissiyasi; buyurtma hal bo‘lguncha ushlab turiladi'))
                    notify(db,it['seller_id'],'order','Yangi buyurtma',f'{o["reference"]} bo‘yicha to‘lov tasdiqlandi.','/orders')
                db.execute('COMMIT')
                for seller in db.execute('SELECT DISTINCT seller_id FROM order_items WHERE order_id=?',(oid,)).fetchall(): email_order_update(db,seller['seller_id'],o['reference'],'paid','Buyurtma to‘lovi tasdiqlandi. Buyurtmani boshqarish uchun hisobingizga kiring.')
                return {'status':'paid','mode':'sandbox'}
            except Exception: db.execute('ROLLBACK'); raise
        m=re.fullmatch(r'/api/orders/([^/]+)/deliver',path)
        if m and method=='POST':
            require_verified(ctx); oid=m.group(1); o=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            if not o: raise HttpError(404,'Buyurtma topilmadi.')
            if o['status'] not in ('paid','awaiting_delivery'): raise HttpError(409,'Buyurtma yetkazishga tayyor emas.')
            iid=clean_text(data.get('item_id'),'Buyurtma mahsuloti',1,100); it=db.execute('SELECT * FROM order_items WHERE id=? AND order_id=? AND seller_id=?',(iid,oid,uid)).fetchone()
            if not it: raise HttpError(403,'Bu mahsulotni yetkazish huquqingiz yo‘q.')
            payload=clean_text(data.get('delivery'),'Yetkazish ma’lumoti',2,5000)
            try: encrypted_payload=delivery_crypto.encrypt_payload(payload,iid)
            except delivery_crypto.DeliveryCryptoError as exc: raise HttpError(503,'Maxfiy yetkazish ma’lumotini saqlash uchun DELIVERY_ENCRYPTION_KEY va cryptography paketi sozlanishi kerak.') from exc
            db.execute('INSERT INTO deliveries(id,order_item_id,seller_id,protected_payload) VALUES(?,?,?,?) ON CONFLICT(order_item_id) DO UPDATE SET protected_payload=excluded.protected_payload,submitted_at=CURRENT_TIMESTAMP',(ident(),iid,uid,encrypted_payload))
            old=o['status']; db.execute("UPDATE orders SET status='awaiting_delivery',updated_at=CURRENT_TIMESTAMP WHERE id=?",(oid,)); event(db,oid,uid,old,'awaiting_delivery','Sotuvchi mahsulotni yubordi'); notify(db,o['buyer_id'],'delivery','Mahsulot yetkazildi','Buyurtmangizdagi mahsulotga kirishingiz mumkin.','/orders'); email_order_update(db,o['buyer_id'],o['reference'],'awaiting_delivery','Sotuvchi buyurtmani yetkazdi. Hisobingizga kirib xavfsiz buyurtma sahifasini tekshiring.'); return {'status':'awaiting_delivery'}
        m=re.fullmatch(r'/api/orders/([^/]+)/complete',path)
        if m and method=='POST':
            require_verified(ctx); oid=m.group(1); db.execute('BEGIN IMMEDIATE')
            try:
                o=db.execute('SELECT * FROM orders WHERE id=? AND buyer_id=?',(oid,uid)).fetchone()
                if not o: raise HttpError(404,'Buyurtma topilmadi.')
                if o['status'] not in ('awaiting_delivery','delivered'): raise HttpError(409,'Bu holatda buyurtmani yakunlab bo‘lmaydi.')
                if db.execute("SELECT 1 FROM order_items i JOIN listings l ON l.id=i.listing_id WHERE i.order_id=? AND l.product_type='account' LIMIT 1",(oid,)).fetchone():
                    raise HttpError(409,'Akkaunt xaridi ikki skrinshot va moderator tasdig‘idan keyin yakunlanadi. Buyurtma sahifasidagi “Akkauntni tekshirtirish” bo‘limidan foydalaning.')
                count=db.execute('SELECT COUNT(*) n FROM order_items i LEFT JOIN deliveries d ON d.order_item_id=i.id WHERE i.order_id=? AND d.id IS NULL',(oid,)).fetchone()['n']
                if count: raise HttpError(409,'Barcha mahsulotlar yetkazilmagan.')
                db.execute("UPDATE orders SET status='completed',updated_at=CURRENT_TIMESTAMP WHERE id=?",(oid,)); event(db,oid,uid,o['status'],'completed','Xaridor buyurtmani yakunladi'); settle_seller_escrow(db,oid)
                sellers=db.execute('SELECT DISTINCT seller_id FROM order_items WHERE order_id=?',(oid,)).fetchall()
                for seller in sellers: notify(db,seller['seller_id'],'order_complete','Buyurtma yakunlandi','Xaridor buyurtmani yakunladi. Mablag‘ sotuvchi balansiga qo‘shildi.','/seller')
                db.execute('COMMIT')
                for seller in sellers: email_order_update(db,seller['seller_id'],o['reference'],'completed','Xaridor buyurtmani yakunladi.')
                return {'status':'completed'}
            except Exception:
                db.execute('ROLLBACK'); raise
        m=re.fullmatch(r'/api/orders/([^/]+)/dispute',path)
        if m and method=='POST':
            require_verified(ctx); oid=m.group(1); why=clean_text(data.get('details'),'Nizo tafsiloti',10,3000); evidence=evidence_link(data.get('evidence_url')); db.execute('BEGIN IMMEDIATE')
            try:
                o=db.execute('SELECT * FROM orders WHERE id=? AND buyer_id=?',(oid,uid)).fetchone()
                if not o: raise HttpError(404,'Buyurtma topilmadi.')
                if o['status'] not in ('paid','awaiting_delivery','delivered'): raise HttpError(409,'Ushbu holatda nizoni ochib bo‘lmaydi.')
                changed=db.execute("UPDATE orders SET status='disputed',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('paid','awaiting_delivery','delivered')",(oid,))
                if changed.rowcount!=1: raise HttpError(409,'Buyurtma holati o‘zgargan; sahifani yangilang.')
                event(db,oid,uid,o['status'],'disputed',why); db.execute('INSERT INTO reports(id,reporter_id,order_id,reason,details,evidence_url) VALUES(?,?,?,?,?,?)',(ident(),uid,oid,'order_dispute',why,evidence))
                for seller in db.execute('SELECT DISTINCT seller_id FROM order_items WHERE order_id=?',(oid,)).fetchall(): notify(db,seller['seller_id'],'dispute','Buyurtma bo‘yicha nizo ochildi',f'{o["reference"]}: moderator ko‘rib chiqadi.','/orders')
                for admin in db.execute('SELECT user_id FROM admin_accounts').fetchall(): notify(db,admin['user_id'],'dispute','Yangi buyurtma nizosi',f'{o["reference"]} buyurtmasi ko‘rib chiqilishi kerak.','/admin')
                db.execute('COMMIT'); return {'status':'disputed'}
            except Exception:
                db.execute('ROLLBACK'); raise
        if path=='/api/requests' and method=='POST':
            require_verified(ctx); check_rate(db,'product_request',uid,5,3600); title=clean_text(data.get('title'),'Sarlavha',5,120); desc=clean_text(data.get('description'),'Tavsif',10,3000); game=clean_text(data.get('game_id'),'O‘yin',1,80)
            if not db.execute('SELECT 1 FROM games WHERE id=?',(game,)).fetchone(): raise HttpError(400,'O‘yin topilmadi.')
            budget=data.get('budget_minor');
            if budget is not None: budget=money(budget)
            expires_sql="(CURRENT_TIMESTAMP + INTERVAL '30 days')::text" if DATABASE_URL else "datetime('now','+30 days')"
            rid=ident(); db.execute(f"INSERT INTO product_requests(id,requester_id,game_id,category_id,title,description,budget_minor,expires_at) VALUES(?,?,?,?,?,?,?,{expires_sql})",(rid,uid,game,data.get('category_id') or None,title,desc,budget)); return 201,{'id':rid,'status':'open'}
        m=re.fullmatch(r'/api/requests/([^/]+)/respond',path)
        if m and method=='POST':
            require_verified(ctx); seller_ok(db,uid); check_rate(db,'request_response',uid,20,3600); rid=m.group(1); req=db.execute("SELECT * FROM product_requests WHERE id=? AND status='open' AND requester_id<>?",(rid,uid)).fetchone()
            if not req: raise HttpError(404,'Ochiq so‘rov topilmadi.')
            msg=clean_text(data.get('message'),'Javob',2,2000); db.execute('INSERT INTO request_responses(id,request_id,seller_id,message,listing_id) VALUES(?,?,?,?,?)',(ident(),rid,uid,msg,data.get('listing_id') or None)); notify(db,req['requester_id'],'request','So‘rovingizga javob','Sotuvchi mahsulot so‘rovingizga javob berdi.','/requests'); return {'ok':True}
        if path=='/api/conversations' and method=='POST':
            require_verified(ctx)
            if data.get('request_id'):
                rid=clean_text(data.get('request_id'),'So‘rov',1,100); seller=clean_text(data.get('seller_id'),'Sotuvchi',1,100)
                req=db.execute("SELECT * FROM product_requests WHERE id=? AND status='open'",(rid,)).fetchone()
                if not req or req['requester_id']!=uid or not db.execute('SELECT 1 FROM request_responses WHERE request_id=? AND seller_id=?',(rid,seller)).fetchone(): raise HttpError(403,'Bu so‘rov javobi bilan suhbat boshlay olmaysiz.')
                conv=db.execute('SELECT id FROM conversations WHERE buyer_id=? AND seller_id=? AND listing_id IS NULL AND order_id IS NULL ORDER BY created_at DESC LIMIT 1',(uid,seller)).fetchone()
                if not conv:
                    cid=ident();db.execute('INSERT INTO conversations(id,buyer_id,seller_id) VALUES(?,?,?)',(cid,uid,seller));conv={'id':cid}
                return {'id':conv['id']}
            lid=clean_text(data.get('listing_id'),'E’lon',1,100); l=db.execute("SELECT * FROM listings WHERE id=? AND status='published'",(lid,)).fetchone()
            if not l or l['seller_id']==uid: raise HttpError(404,'E’lon topilmadi.')
            cid=ident(); db.execute('INSERT OR IGNORE INTO conversations(id,buyer_id,seller_id,listing_id) VALUES(?,?,?,?)',(cid,uid,l['seller_id'],lid)); conv=db.execute('SELECT * FROM conversations WHERE buyer_id=? AND seller_id=? AND listing_id=?',(uid,l['seller_id'],lid)).fetchone(); return {'id':conv['id']}
        m=re.fullmatch(r'/api/conversations/([^/]+)/messages',path)
        if m and method=='POST':
            require_verified(ctx); check_rate(db,'message',uid,40,3600); conv=db.execute('SELECT * FROM conversations WHERE id=?',(m.group(1),)).fetchone()
            if not conv or uid not in (conv['buyer_id'],conv['seller_id']): raise HttpError(404,'Suhbat topilmadi.')
            body=clean_text(data.get('body'),'Xabar',1,2000); mid=ident(); db.execute('INSERT INTO messages(id,conversation_id,sender_id,body) VALUES(?,?,?,?)',(mid,conv['id'],uid,body)); notify(db,conv['seller_id'] if uid==conv['buyer_id'] else conv['buyer_id'],'message','Yangi xabar',body[:160],'/messages'); return {'id':mid}
        if path=='/api/reports' and method=='POST':
            require_user(ctx); check_rate(db,'report',uid,10,3600); reason=clean_text(data.get('reason'),'Sabab',3,100); details=clean_text(data.get('details'),'Tafsilot',10,3000); evidence=evidence_link(data.get('evidence_url')); lid=data.get('listing_id'); oid=data.get('order_id')
            if not lid and not oid: raise HttpError(400,'E’lon yoki buyurtmani ko‘rsating.')
            if lid and not db.execute('SELECT 1 FROM listings WHERE id=?',(lid,)).fetchone(): raise HttpError(404,'E’lon topilmadi.')
            if oid:
                order=db.execute('SELECT buyer_id FROM orders WHERE id=?',(oid,)).fetchone()
                if not order or (uid!=order['buyer_id'] and not db.execute('SELECT 1 FROM order_items WHERE order_id=? AND seller_id=?',(oid,uid)).fetchone()): raise HttpError(404,'Buyurtma topilmadi.')
            rid=ident(); db.execute('INSERT INTO reports(id,reporter_id,listing_id,order_id,reason,details,evidence_url) VALUES(?,?,?,?,?,?,?)',(rid,uid,lid,oid,reason,details,evidence))
            for admin in db.execute('SELECT user_id FROM admin_accounts').fetchall(): notify(db,admin['user_id'],'report','Yangi shikoyat',reason+' · '+details[:120],'/admin')
            return 201,{'id':rid,'status':'open'}
        if path=='/api/reviews/mine' and method=='GET':
            require_user(ctx)
            return [dict(x) for x in db.execute('''SELECT r.id,r.rating,r.body,r.created_at,
                l.id listing_id,l.title listing_title,sp.shop_name seller_name,o.reference order_reference
                FROM reviews r JOIN order_items i ON i.id=r.order_item_id
                JOIN orders o ON o.id=i.order_id JOIN listings l ON l.id=i.listing_id
                JOIN seller_profiles sp ON sp.user_id=r.seller_id
                WHERE r.reviewer_id=? ORDER BY r.created_at DESC LIMIT 100''',(uid,)).fetchall()]
        if path=='/api/reviews' and method=='POST':
            require_verified(ctx); iid=clean_text(data.get('item_id'),'Buyurtma mahsuloti',1,100); rating=data.get('rating'); body=clean_text(data.get('body'),'Sharh',5,1500)
            if not isinstance(rating,int) or rating<1 or rating>5: raise HttpError(400,'Baho 1 dan 5 gacha bo‘lsin.')
            it=db.execute("SELECT i.*,o.status,o.buyer_id FROM order_items i JOIN orders o ON o.id=i.order_id WHERE i.id=?",(iid,)).fetchone()
            if not it or it['buyer_id']!=uid or it['status']!='completed': raise HttpError(403,'Sharh faqat tugallangan xarid uchun mumkin.')
            rid=ident(); db.execute('INSERT INTO reviews(id,order_item_id,reviewer_id,seller_id,rating,body) VALUES(?,?,?,?,?,?)',(rid,iid,uid,it['seller_id'],rating,body)); return 201,{'id':rid}
        if path=='/api/payouts' and method=='GET':
            require_user(ctx); seller_ok(db,uid); return [dict(x) for x in db.execute('SELECT id,amount_minor,currency,status,note,created_at,updated_at FROM payout_requests WHERE seller_id=? ORDER BY created_at DESC LIMIT 50',(uid,))]
        if path=='/api/payouts' and method=='POST':
            require_verified(ctx); seller_ok(db,uid); amount=money(data.get('amount_minor')); cur=clean_text(data.get('currency','UZS'),'Valyuta',3,3)
            if cur!='UZS': raise HttpError(400,'Hozircha sotuvchi hisob-kitobi faqat UZS valyutasida ishlaydi.')
            db.execute('BEGIN IMMEDIATE')
            try:
                balance=db.execute("SELECT COALESCE(SUM(amount_minor),0) n FROM ledger_entries WHERE user_id=? AND entry_type IN ('seller_earning','payout')",(uid,)).fetchone()['n']
                pending=db.execute("SELECT COALESCE(SUM(amount_minor),0) n FROM payout_requests WHERE seller_id=? AND status IN ('pending','approved')",(uid,)).fetchone()['n']
                if amount>balance-pending: raise HttpError(400,'So‘ralgan summa mavjud balansdan oshib ketdi.')
                pid=ident(); db.execute('INSERT INTO payout_requests(id,seller_id,amount_minor,currency) VALUES(?,?,?,?)',(pid,uid,amount,cur)); audit(db,uid,'payout_request','payout',pid); db.execute('COMMIT'); return 201,{'id':pid,'status':'pending','note':'To‘lov tashqi provayder yoqilmaguncha bajarilmaydi.'}
            except Exception: db.execute('ROLLBACK'); raise
        m=re.fullmatch(r'/api/admin/listings/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); lid=m.group(1); action=data.get('action'); note=clean_text(data.get('note',''),'Izoh',0,1000)
            if action not in ('approve','reject','pause'): raise HttpError(400,'Moderatsiya amali noto‘g‘ri.')
            status={'approve':'published','reject':'rejected','pause':'paused'}[action]; l=db.execute("SELECT * FROM listings WHERE id=? AND status IN ('pending_review','published')",(lid,)).fetchone()
            if not l: raise HttpError(404,'Tekshiriladigan e’lon topilmadi.')
            if action=='approve':
                require_listing_allowed(db,l['game_id'],l['product_type'])
                if l['product_type']=='account' and l['seller_account_terms_version']!=ACCOUNT_SELLER_TERMS_VERSION:
                    raise HttpError(400,'Sotuvchi akkaunt savdosi qoidalarini tasdiqlamagan.')
                risk_flags=json.loads(l['attributes_json'] or '{}').get('_risk_flags',[])
                if risk_flags and len(note.strip())<10:
                    raise HttpError(400,'Xavf belgilarini moderator izohida ko‘rib chiqib, kamida 10 belgi bilan qayd eting.')
            db.execute('UPDATE listings SET status=?,moderation_note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,note,lid)); audit(db,aid,'listing_'+action,'listing',lid,{'note':note}); notify(db,l['seller_id'],'moderation','Moderatsiya natijasi',f'E’loningiz holati: {status}. {note}','/seller'); return {'status':status}
        m=re.fullmatch(r'/api/admin/sellers/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); target=m.group(1); action=data.get('action'); note=clean_text(data.get('note'),'Tekshiruv izohi',5,1000)
            if action not in ('approve','reject'): raise HttpError(400,'Sotuvchi uchun tasdiqlash yoki rad etishni tanlang.')
            profile=db.execute('SELECT s.*,u.email_verified FROM seller_profiles s JOIN users u ON u.id=s.user_id WHERE s.user_id=?',(target,)).fetchone()
            if not profile: raise HttpError(404,'Sotuvchi profili topilmadi.')
            if action=='approve' and not profile['email_verified']: raise HttpError(409,'Sotuvchini tasdiqlashdan oldin emaili tasdiqlangan bo‘lishi kerak.')
            if action=='approve' and (profile['identity_status']!='verified' or profile['identity_provider']!='didit'): raise HttpError(409,'Sotuvchini tasdiqlashdan oldin Didit ID, liveness va face-match tekshiruvlari tasdiqlanishi kerak.')
            if profile['verification_status']=='verified' and profile['selling_enabled'] and action=='approve': raise HttpError(409,'Sotuvchi allaqachon tasdiqlangan va faol.')
            status='verified' if action=='approve' else 'rejected'; enabled=1 if action=='approve' else 0
            db.execute('UPDATE seller_profiles SET verification_status=?,selling_enabled=? WHERE user_id=?',(status,enabled,target))
            if not enabled: db.execute("UPDATE listings SET status='paused',updated_at=CURRENT_TIMESTAMP WHERE seller_id=? AND status='published'",(target,))
            audit(db,aid,'seller_'+action,'seller',target,{'note':note}); notify(db,target,'seller_review','Sotuvchi tekshiruvi yakunlandi',('Profilingiz tasdiqlandi. Endi e’lon joylashingiz mumkin. ' if enabled else 'Profil tasdiqlanmadi. Izoh: ')+note,'/seller')
            return {'verification_status':status,'selling_enabled':bool(enabled)}
        m=re.fullmatch(r'/api/admin/account-reviews/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); oid=m.group(1); action=data.get('action'); note=clean_text(data.get('note',''),'Moderator izohi',5,1500)
            if action not in ('approve','request_info','refund_buyer'): raise HttpError(400,'Akkaunt tekshiruvi uchun amal noto‘g‘ri.')
            review=db.execute("SELECT * FROM account_reviews WHERE order_id=? AND status='pending'",(oid,)).fetchone()
            order=db.execute("SELECT * FROM orders WHERE id=? AND status='under_review'",(oid,)).fetchone()
            if not review or not order: raise HttpError(404,'Moderator ko‘rigida turgan akkaunt buyurtmasi topilmadi.')
            evidence=db.execute('SELECT slot,object_path FROM account_review_evidence WHERE order_id=? ORDER BY slot',(oid,)).fetchall()
            if len(evidence)!=2 or [row['slot'] for row in evidence]!=[1,2]: raise HttpError(409,'Ikkala maxfiy skrinshot ham mavjud bo‘lishi shart.')
            payment=db.execute('SELECT * FROM payments WHERE order_id=?',(oid,)).fetchone()
            if MODE!='development' or not payment or payment['provider']!='sandbox' or payment['status']!='succeeded':
                raise HttpError(503,'Bu amal faqat sandbox buyurtmada ishlaydi. Haqiqiy pul uchun tasdiqlangan payment/refund/escrow jarayoni kerak; mablag‘ o‘zgartirilmadi.')
            if action in ('approve','request_info'): require_private_evidence_bucket()
            db.execute('BEGIN IMMEDIATE')
            try:
                if action=='request_info':
                    db.execute("UPDATE account_reviews SET status='needs_info',review_note=?,reviewed_by=?,reviewed_at=? WHERE order_id=? AND status='pending'",(note,aid,now_iso(),oid))
                    event(db,oid,aid,'under_review','under_review','Moderator qo‘shimcha dalil so‘radi: '+note)
                    notify(db,review['buyer_id'],'account_review','Akkaunt tekshiruvi uchun qo‘shimcha ma’lumot kerak',note,'/order/'+oid)
                    result='needs_info'
                elif action=='approve':
                    db.execute("UPDATE account_reviews SET status='approved',review_note=?,reviewed_by=?,reviewed_at=? WHERE order_id=? AND status='pending'",(note,aid,now_iso(),oid))
                    changed=db.execute("UPDATE orders SET status='completed',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='under_review'",(oid,))
                    if changed.rowcount!=1: raise HttpError(409,'Buyurtma holati o‘zgargan; yangilang.')
                    event(db,oid,aid,'under_review','completed','Moderator xaridorning akkauntga kirish dalillarini ko‘rib, buyurtmani tasdiqladi: '+note)
                    settle_seller_escrow(db,oid)
                    result='completed'
                else:
                    db.execute("UPDATE account_reviews SET status='refunded',review_note=?,reviewed_by=?,reviewed_at=? WHERE order_id=? AND status='pending'",(note,aid,now_iso(),oid))
                    changed=db.execute("UPDATE orders SET status='refunded',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='under_review'",(oid,))
                    if changed.rowcount!=1: raise HttpError(409,'Buyurtma holati o‘zgargan; yangilang.')
                    refund_sandbox_escrow(db,oid,review['buyer_id'])
                    db.execute("UPDATE payments SET status='sandbox_refunded',updated_at=CURRENT_TIMESTAMP WHERE order_id=?",(oid,))
                    event(db,oid,aid,'under_review','refunded','Moderator sandbox qaytarimini qayd etdi: '+note)
                    result='refunded'
                audit(db,aid,'account_review_'+action,'order',oid,{'note':note,'evidence_count':2})
                if action=='approve': notify(db,review['buyer_id'],'account_review','Akkaunt tekshiruvi yakunlandi','Moderator ikkala skrinshotni ko‘rib, buyurtmani tasdiqladi. Bu keyinchalik akkaunt tiklanmasligiga kafolat bermaydi.','/order/'+oid)
                elif action=='refund_buyer': notify(db,review['buyer_id'],'account_review','Sandbox qaytarimi qayd etildi','Moderator sandbox qaytarimini qayd etdi; haqiqiy pul o‘tkazilmagan.','/order/'+oid)
                for seller in db.execute('SELECT DISTINCT seller_id FROM order_items WHERE order_id=?',(oid,)).fetchall():
                    seller_message={'request_info':'Xaridordan qo‘shimcha dalil so‘raldi. Mablag‘ hozircha sotuvchi balansiga yozilmadi.','approve':'Moderator tekshiruvni tasdiqladi. Mablag‘ sandbox sotuvchi balansiga yozildi; haqiqiy pul o‘tkazilmadi.','refund_buyer':'Moderator sandbox qaytarimini qayd etdi; haqiqiy pul o‘tkazilmadi.'}[action]
                    notify(db,seller['seller_id'],'account_review','Akkaunt tekshiruvi yangilandi',seller_message,'/orders')
                db.execute('COMMIT')
                return {'status':result,'funds_moved':action in ('approve','refund_buyer'),'real_money_moved':False}
            except Exception:
                db.execute('ROLLBACK'); raise
        m=re.fullmatch(r'/api/admin/disputes/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); oid=m.group(1); action=data.get('action'); note=clean_text(data.get('note'),'Moderator qarori',5,1500)
            if action not in ('request_info','release_seller','refund_buyer'): raise HttpError(400,'Nizo bo‘yicha amal noto‘g‘ri.')
            report=db.execute("SELECT * FROM reports WHERE order_id=? AND reason='order_dispute' AND status IN ('open','reviewing') ORDER BY created_at DESC LIMIT 1",(oid,)).fetchone()
            order=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            if not report or not order or order['status']!='disputed': raise HttpError(404,'Ochiq nizoli buyurtma topilmadi.')
            sellers=[x['seller_id'] for x in db.execute('SELECT DISTINCT seller_id FROM order_items WHERE order_id=?',(oid,)).fetchall()]
            if action=='request_info':
                db.execute("UPDATE reports SET status='reviewing',resolution=? WHERE id=?",(note,report['id'])); audit(db,aid,'dispute_request_info','order',oid,{'note':note})
                notify(db,report['reporter_id'],'dispute_update','Nizongiz ko‘rib chiqilmoqda',note,'/order/'+oid)
                for seller in sellers: notify(db,seller,'dispute_update','Nizo bo‘yicha qo‘shimcha ma’lumot',note,'/order/'+oid)
                return {'status':'reviewing','funds_moved':False}
            payment=db.execute('SELECT * FROM payments WHERE order_id=?',(oid,)).fetchone()
            if MODE!='development' or not payment or payment['provider']!='sandbox' or payment['status']!='succeeded':
                raise HttpError(503,'Haqiqiy nizoni yakunlash uchun provayderning tasdiqlangan refund/escrow adapteri kerak. Hech qanday mablag‘ o‘zgartirilmadi.')
            db.execute('BEGIN IMMEDIATE')
            try:
                if action=='release_seller':
                    changed=db.execute("UPDATE orders SET status='completed',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='disputed'",(oid,))
                    if changed.rowcount!=1: raise HttpError(409,'Nizo allaqachon yakunlangan.')
                    event(db,oid,aid,'disputed','completed',note); settle_seller_escrow(db,oid)
                    result='completed'; buyer_title='Nizo yakunlandi'; buyer_body='Moderator dalillarni ko‘rib, buyurtmani yakunladi. Bu sandbox hisob-kitobi.'; seller_title='Nizo yakunlandi'; seller_body='Buyurtma sandbox sotuvchi balansiga o‘tkazildi. Haqiqiy pul o‘tkazilmagan.'
                else:
                    changed=db.execute("UPDATE orders SET status='refunded',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='disputed'",(oid,))
                    if changed.rowcount!=1: raise HttpError(409,'Nizo allaqachon yakunlangan.')
                    refund_sandbox_escrow(db,oid,order['buyer_id']); db.execute("UPDATE payments SET status='sandbox_refunded',updated_at=CURRENT_TIMESTAMP WHERE order_id=?",(oid,)); event(db,oid,aid,'disputed','refunded',note)
                    result='refunded'; buyer_title='Sandbox qaytarimi qayd etildi'; buyer_body='Sinov buyurtmasi bekor qilindi. Bu haqiqiy pul qaytarimi emas.'; seller_title='Nizo yakunlandi'; seller_body='Sinov buyurtmasi qaytarim bilan yopildi; haqiqiy pul ko‘chirilmagan.'
                db.execute("UPDATE reports SET status='resolved',resolution=? WHERE id=?",(note,report['id'])); audit(db,aid,'dispute_'+action,'order',oid,{'note':note,'payment_mode':'sandbox'})
                notify(db,order['buyer_id'],'dispute_update',buyer_title,buyer_body,'/order/'+oid)
                for seller in sellers: notify(db,seller,'dispute_update',seller_title,seller_body,'/order/'+oid)
                db.execute('COMMIT')
                email_order_update(db,order['buyer_id'],order['reference'],result,'Buyurtma bo‘yicha nizo ko‘rib chiqildi. Batafsil ma’lumotni hisobingizdan tekshiring.')
                for seller in sellers: email_order_update(db,seller,order['reference'],result,'Buyurtma bo‘yicha nizo ko‘rib chiqildi. Batafsil ma’lumotni hisobingizdan tekshiring.')
                return {'status':result,'funds_moved':False,'sandbox_only':True}
            except Exception:
                db.execute('ROLLBACK'); raise
        if path=='/api/admin/config' and method=='POST':
            aid=require_admin(ctx); bps=data.get('commission_bps')
            if not isinstance(bps,int) or bps<0 or bps>3000: raise HttpError(400,'Komissiya 0–3000 bps bo‘lishi kerak.')
            db.execute("INSERT INTO platform_config(key,value) VALUES('commission_bps',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP",(str(bps),)); audit(db,aid,'config_update','platform_config','commission_bps',{'commission_bps':bps}); return {'commission_bps':bps}
        if path=='/api/admin/blog' and method=='POST':
            aid=require_admin(ctx)
            slug=clean_text(data.get('slug'),'Slug',3,80).lower()
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug): raise HttpError(400,'Slug faqat kichik lotin harflari, raqam va tirelardan iborat bo‘lsin.')
            post=validate_blog_post(data)
            status=data.get('status','draft')
            if status not in ('draft','published'): raise HttpError(400,'Maqola holati noto‘g‘ri.')
            pid=ident(); published=now_iso() if status=='published' else None
            db.execute('INSERT INTO blog_posts(id,slug,category_json,title_json,summary_json,body_json,status,author_id,published_at) VALUES(?,?,?,?,?,?,?,?,?)',(pid,slug,*[json.dumps(post[k],ensure_ascii=False) for k in ('category','title','summary','body')],status,aid,published))
            audit(db,aid,'blog_create','blog_post',pid,{'slug':slug,'status':status})
            return 201,{'id':pid,'slug':slug,'status':status}
        m=re.fullmatch(r'/api/admin/blog/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); pid=m.group(1)
            current=db.execute('SELECT * FROM blog_posts WHERE id=?',(pid,)).fetchone()
            if not current: raise HttpError(404,'Maqola topilmadi.')
            slug=clean_text(data.get('slug'),'Slug',3,80).lower()
            if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug): raise HttpError(400,'Slug faqat kichik lotin harflari, raqam va tirelardan iborat bo‘lsin.')
            post=validate_blog_post(data); status=data.get('status')
            if status not in ('draft','published'): raise HttpError(400,'Maqola holati noto‘g‘ri.')
            published=current['published_at'] or now_iso() if status=='published' else None
            db.execute('UPDATE blog_posts SET slug=?,category_json=?,title_json=?,summary_json=?,body_json=?,status=?,published_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(slug,*[json.dumps(post[k],ensure_ascii=False) for k in ('category','title','summary','body')],status,published,pid))
            audit(db,aid,'blog_update','blog_post',pid,{'slug':slug,'status':status})
            return {'id':pid,'slug':slug,'status':status}
        m=re.fullmatch(r'/api/admin/reports/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); status=data.get('status'); resolution=clean_text(data.get('resolution',''),'Qaror',0,1500)
            if status not in ('reviewing','resolved','dismissed'): raise HttpError(400,'Holat noto‘g‘ri.')
            report=db.execute('SELECT reason,order_id FROM reports WHERE id=?',(m.group(1),)).fetchone()
            if report and report['reason']=='order_dispute' and status in ('resolved','dismissed'):
                raise HttpError(400,'Buyurtma nizosini maxsus nizo bo‘limidan yakunlang.')
            db.execute('UPDATE reports SET status=?,resolution=? WHERE id=?',(status,resolution,m.group(1))); audit(db,aid,'report_update','report',m.group(1),{'status':status}); return {'status':status}
        m=re.fullmatch(r'/api/admin/payouts/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); action=data.get('action'); note=clean_text(data.get('note',''),'Izoh',0,1000)
            if action not in ('approve','reject','mark_paid'): raise HttpError(400,'Payout amali noto‘g‘ri.')
            if action=='mark_paid': note=clean_text(data.get('external_reference'),'Tashqi o‘tkazma ID',3,120)
            db.execute('BEGIN IMMEDIATE')
            try:
                p=db.execute('SELECT * FROM payout_requests WHERE id=?',(m.group(1),)).fetchone()
                if not p: raise HttpError(404,'Payout so‘rovi topilmadi.')
                allowed={'approve':'pending','reject':'pending','mark_paid':'approved'}
                if p['status']!=allowed[action]: raise HttpError(409,'Payout so‘rovi oldingi holatini tugatmagan yoki allaqachon ko‘rilgan.')
                status={'approve':'approved','reject':'rejected','mark_paid':'paid'}[action]
                if action=='mark_paid': db.execute('INSERT INTO ledger_entries(id,user_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,?)',(ident(),p['seller_id'],'payout',-p['amount_minor'],p['currency'],'Tashqi o‘tkazma tasdiq raqami: '+note))
                db.execute('UPDATE payout_requests SET status=?,admin_id=?,note=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,aid,note,p['id'])); audit(db,aid,'payout_'+action,'payout',p['id'],{'note':note}); notify(db,p['seller_id'],'payout','Payout so‘rovi yangilandi',('Tashqi o‘tkazma tasdiqlandi. ID: '+note) if action=='mark_paid' else ('So‘rov ma’qullandi; pulni tashqi provayder orqali o‘tkazing.' if action=='approve' else 'Payout so‘rovi rad etildi. '+note),'/seller')
                db.execute('COMMIT'); return {'status':status,'funds_transferred':False,'external_transfer_required':action=='approve'}
            except Exception:
                db.execute('ROLLBACK'); raise
        if path=='/api/admin/users' and method=='GET':
            require_admin(ctx); q=qs.get('q',[''])[0].strip(); return [dict(x) for x in db.execute('SELECT id,email,display_name,email_verified,suspended,created_at FROM users WHERE email LIKE ? OR display_name LIKE ? ORDER BY created_at DESC LIMIT 100',(f'%{q}%',f'%{q}%'))]
        m=re.fullmatch(r'/api/admin/deletions/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); action=data.get('action')
            if action not in ('reviewing','dismissed','resolved'): raise HttpError(400,'O‘chirish so‘rovi amali noto‘g‘ri.')
            request=db.execute('SELECT user_id FROM account_deletion_requests WHERE id=?',(m.group(1),)).fetchone()
            if not request: raise HttpError(404,'O‘chirish so‘rovi topilmadi.')
            db.execute('BEGIN')
            try:
                if action=='resolved': erase_account_personal_data(db,request['user_id'])
                db.execute('UPDATE account_deletion_requests SET status=?,reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP WHERE id=?',(action,aid,m.group(1)))
                audit(db,aid,'deletion_'+action,'deletion_request',m.group(1),{'personal_data_erased':action=='resolved'})
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK')
                raise
            return {'status':action,'personal_data_erased':action=='resolved'}
        m=re.fullmatch(r'/api/admin/users/([^/]+)',path)
        if m and method=='POST':
            aid=require_admin(ctx); target=m.group(1); action=data.get('action'); reason=clean_text(data.get('reason'),'Sabab',5,500)
            if target==aid: raise HttpError(400,'O‘z hisobingizni bu yerdan cheklay olmaysiz.')
            if action not in ('suspend','restore'): raise HttpError(400,'Foydalanuvchi amali noto‘g‘ri.')
            db.execute('UPDATE users SET suspended=? WHERE id=?',(1 if action=='suspend' else 0,target)); db.execute('DELETE FROM sessions WHERE user_id=?',(target,)) if action=='suspend' else None
            if action=='suspend':
                db.execute('UPDATE seller_profiles SET selling_enabled=0 WHERE user_id=?',(target,)); db.execute("UPDATE listings SET status='paused',updated_at=CURRENT_TIMESTAMP WHERE seller_id=? AND status='published'",(target,))
            audit(db,aid,'user_'+action,'user',target,{'reason':reason}); notify(db,target,'account','Hisob holati o‘zgardi',('Hisobingiz vaqtincha cheklangan. Sabab: ' if action=='suspend' else 'Hisobingiz qayta yoqildi. ')+reason,'/account'); return {'status':action}
        if path=='/api/admin/orders' and method=='GET':
            require_admin(ctx); return [dict(x) for x in db.execute('SELECT o.*,u.email buyer_email FROM orders o JOIN users u ON u.id=o.buyer_id ORDER BY o.created_at DESC LIMIT 100')]
        if path.startswith('/api/') and method not in ('GET','POST','PATCH','DELETE'): raise HttpError(405,'Usul qo‘llab-quvvatlanmaydi.')
        raise HttpError(404,'API manzili topilmadi.')

class Server(ThreadingHTTPServer):
    daemon_threads=True


class _VercelRequest(Handler):
    """Adapt one Vercel WSGI request to the existing HTTP request handler."""
    def __init__(self, environ):
        self.command=environ.get('REQUEST_METHOD','GET').upper()
        path=environ.get('PATH_INFO','/') or '/'
        query=environ.get('QUERY_STRING','')
        self.path=path+('?' + query if query else '')
        self.headers=Message()
        for key,value in environ.items():
            if key.startswith('HTTP_'):
                name=key[5:].replace('_','-').title()
                self.headers[name]=value
        if environ.get('CONTENT_TYPE'):
            self.headers['Content-Type']=environ['CONTENT_TYPE']
        if environ.get('CONTENT_LENGTH'):
            self.headers['Content-Length']=environ['CONTENT_LENGTH']
        # Vercel overwrites these headers with the public client address.
        # Prefer its explicit header; validate it before using it as a rate-limit key.
        forwarded=self.headers.get('X-Vercel-Forwarded-For','').split(',')[0].strip()
        try:
            client_ip=str(ipaddress.ip_address(forwarded)) if forwarded else str(ipaddress.ip_address(environ.get('REMOTE_ADDR','0.0.0.0')))
        except ValueError:
            # Ignore a malformed forwarding header and fall back to the platform peer.
            try: client_ip=str(ipaddress.ip_address(environ.get('REMOTE_ADDR','0.0.0.0')))
            except ValueError: client_ip='0.0.0.0'
        self.client_address=(client_ip,0)
        body_limit=MAX_IMAGE_BODY if self.command=='POST' and (path.rstrip('/')=='/api/listing-images' or re.fullmatch(r'/api/orders/[A-Za-z0-9_-]{1,100}/account-evidence/[12]',path.rstrip('/'))) else MAX_BODY
        body=environ.get('wsgi.input',io.BytesIO()).read(body_limit+1)
        self.rfile=io.BytesIO(body)
        self.wfile=io.BytesIO()
        self._status=200
        self._response_headers=[]

    def send_response(self, code, message=None):
        self._status=code

    def send_header(self, key, value):
        self._response_headers.append((key,str(value)))

    def end_headers(self):
        pass

    def send_error(self, code, message=None, explain=None):
        phrase=message or HTTPStatus(code).phrase
        payload=(f'<!doctype html><meta charset="utf-8"><title>{code} {phrase}</title>'
                 f'<h1>{code} {phrase}</h1>').encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class VercelWSGIApplication:
    """Run the existing routes as a WSGI app for Vercel's Python runtime."""
    def __init__(self):
        self._startup_lock=Lock()
        self._startup_complete=False

    def _startup(self):
        if self._startup_complete: return
        with self._startup_lock:
            if self._startup_complete: return
            if MODE=='production':
                if not DATABASE_URL:
                    raise RuntimeError('Set DATABASE_URL to the production Supabase PostgreSQL connection string.')
                if not delivery_crypto.crypto_is_available():
                    raise RuntimeError('Install requirements.txt before starting production.')
                if not delivery_crypto.key_is_configured():
                    raise RuntimeError('Set DELIVERY_ENCRYPTION_KEY before starting production.')
            migrate()
            if MODE=='production':
                db=connect()
                try:
                    legacy=db.execute("SELECT COUNT(*) n FROM deliveries WHERE protected_payload NOT LIKE 'enc:v1:%'").fetchone()['n']
                finally:
                    db.close()
                if legacy:
                    raise RuntimeError('Encrypt existing delivery records with scripts/encrypt_delivery_payloads.py before starting production.')
            self._startup_complete=True

    def __call__(self, environ, start_response):
        self._startup()
        request=_VercelRequest(environ)
        method=request.command
        if method=='HEAD':
            request.do_GET()
        elif method in ('GET','POST','PATCH','DELETE'):
            getattr(request,'do_'+method)()
        else:
            request.send_json(405,{'error':'Usul qo‘llab-quvvatlanmaydi.'})
        try:
            phrase=HTTPStatus(request._status).phrase
        except ValueError:
            phrase='Unknown Status'
        start_response(f'{request._status} {phrase}',request._response_headers)
        body=request.wfile.getvalue()
        return [b'' if method=='HEAD' else body]


# Vercel detects this WSGI application and invokes it per request. The local
# ThreadingHTTPServer remains the entry point when this file is run directly.
app=VercelWSGIApplication()

def main():
    if MODE=='production':
        if not DATABASE_URL:
            raise RuntimeError('Set DATABASE_URL to the production Supabase PostgreSQL connection string.')
        if not delivery_crypto.crypto_is_available():
            raise RuntimeError('Install requirements.txt before starting production.')
        if not delivery_crypto.key_is_configured():
            raise RuntimeError('Set DELIVERY_ENCRYPTION_KEY before starting production.')
    migrate()
    if MODE=='production':
        db=connect()
        try:
            legacy=db.execute("SELECT COUNT(*) n FROM deliveries WHERE protected_payload NOT LIKE 'enc:v1:%'").fetchone()['n']
        finally: db.close()
        if legacy:
            raise RuntimeError('Encrypt existing delivery records with scripts/encrypt_delivery_payloads.py before starting production.')
    host=os.environ.get('HOST','127.0.0.1'); port=int(os.environ.get('PORT','8000'))
    print(f'SentryLoot {MODE} server: http://{host}:{port}')
    Server((host,port),Handler).serve_forever()
if __name__=='__main__': main()

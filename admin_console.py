"""Private administrative reporting. Never calls a payment provider.

Amounts follow the application's stored units (MYR cents, UZS whole som).
Revenue is recognized ledger commission, never gross sales or escrow holds.
Test books are isolated from live accounting; expense corrections are auditable.
"""
from datetime import date, datetime, timedelta, timezone
import re

UNHANDLED = object()
BOOKS = ('live', 'sandbox', 'stripe_test')
CATEGORIES = ('advertising', 'infrastructure', 'provider', 'support', 'other')
SCHEMA = """CREATE TABLE IF NOT EXISTS admin_expenses (
 id TEXT PRIMARY KEY, amount_minor BIGINT NOT NULL CHECK(amount_minor>0),
 currency TEXT NOT NULL, book TEXT NOT NULL CHECK(book IN ('live','sandbox','stripe_test')),
 category TEXT NOT NULL, description TEXT NOT NULL, incurred_on TEXT NOT NULL,
 created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 voided_at TEXT, voided_by TEXT REFERENCES users(id), void_reason TEXT NOT NULL DEFAULT ''
)"""


def migrate(db, postgres=False):
    db.execute(SCHEMA)
    db.execute('CREATE INDEX IF NOT EXISTS idx_admin_expenses_period ON admin_expenses(book,currency,incurred_on)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_ledger_reporting ON ledger_entries(entry_type,currency,created_at,order_id)')
    if postgres:
        db.execute('ALTER TABLE public.admin_expenses ENABLE ROW LEVEL SECURITY')
        db.execute('REVOKE ALL ON public.admin_expenses FROM PUBLIC, anon, authenticated')


def today():
    return datetime.now(timezone.utc).date()


def checked_date(value, core):
    try:
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise ValueError()
        result = date.fromisoformat(value)
        if result < date(2000, 1, 1) or result > today():
            raise ValueError()
        return result
    except ValueError:
        raise core['HttpError'](400, 'Sana 2000-01-01 va bugungi UTC kun oralig‘ida bo‘lsin.')


def checked_scope(book, currency, core):
    if not isinstance(book,str) or not isinstance(currency,str) or book not in BOOKS or currency not in core['ASIA_CURRENCIES']:
        raise core['HttpError'](400, 'Hisob turi yoki valyuta noto‘g‘ri.')


def period(qs, core):
    start = checked_date(qs.get('start', [str(today().replace(day=1))])[0], core)
    end = checked_date(qs.get('end', [str(today())])[0], core)
    if start > end or (end-start).days > 365:
        raise core['HttpError'](400, 'Davr 1–366 kun bo‘lsin; boshlanish sanasi tugash sanasidan keyin bo‘lmasin.')
    book, currency = qs.get('book', ['live'])[0], qs.get('currency', ['UZS'])[0]
    checked_scope(book, currency, core)
    return start, end, book, currency


def mode_sql(book):
    # Closed allowlist, never interpolate a request value into SQL.
    return "o.payment_mode NOT IN ('sandbox','stripe_test','disabled')" if book == 'live' else "o.payment_mode='sandbox'" if book == 'sandbox' else "o.payment_mode='stripe_test'"


def report(db, qs, core):
    start, end, book, currency = period(qs, core)
    lo, hi = str(start), str(end+timedelta(days=1))
    scope = mode_sql(book)
    revenue_kind = 'stripe_test_commission' if book == 'stripe_test' else 'platform_commission'
    revenue_where = f"le.entry_type=? AND le.currency=? AND le.created_at>=? AND le.created_at<? AND {scope}"
    args = (revenue_kind, currency, lo, hi)
    # SUM includes negative reversal entries of the same recognized commission type.
    day_sql = "to_char(le.created_at::timestamptz AT TIME ZONE 'UTC','YYYY-MM-DD')" if core.get('DATABASE_URL') else 'date(le.created_at)'
    income = {r['day']: int(r['amount']) for r in db.execute(f'''SELECT {day_sql} day,SUM(le.amount_minor) amount
        FROM ledger_entries le JOIN orders o ON o.id=le.order_id WHERE {revenue_where} GROUP BY 1''', args)}
    costs = {r['day']: int(r['amount']) for r in db.execute('''SELECT incurred_on day,SUM(amount_minor) amount FROM admin_expenses
        WHERE book=? AND currency=? AND incurred_on>=? AND incurred_on<? AND voided_at IS NULL GROUP BY incurred_on''', (book, currency, lo, hi))}
    daily = []
    cursor = start
    while cursor <= end:
        day = str(cursor); revenue = income.get(day, 0); expense = costs.get(day, 0)
        daily.append({'day': day, 'revenue_minor': revenue, 'expense_minor': expense, 'profit_minor': revenue-expense})
        cursor += timedelta(days=1)
    # GMV is paid merchandise value, with failed/refunded/cancelled orders excluded.
    paid = f"o.currency=? AND o.created_at>=? AND o.created_at<? AND {scope} AND o.status NOT IN ('cancelled','refunded','pending_payment') AND EXISTS(SELECT 1 FROM payments p WHERE p.order_id=o.id AND p.status='succeeded' AND p.provider=o.payment_mode)"
    gmv = db.execute(f'SELECT COALESCE(SUM(o.subtotal_minor),0) amount,COUNT(*) count FROM orders o WHERE {paid}', (currency, lo, hi)).fetchone()
    categories = [dict(r) for r in db.execute('''SELECT category,SUM(amount_minor) amount_minor,COUNT(*) count FROM admin_expenses
        WHERE book=? AND currency=? AND incurred_on>=? AND incurred_on<? AND voided_at IS NULL GROUP BY category ORDER BY amount_minor DESC''', (book, currency, lo, hi))]
    for row in categories:
        row['amount_minor'] = int(row['amount_minor'])
        row['count'] = int(row['count'])
    # Allocate recognized order-level commission by immutable line value. Decimal
    # shares are reconciled to the ledger total below, so totals always agree.
    games = [dict(r) for r in db.execute(f'''WITH fees AS (
        SELECT le.order_id,SUM(le.amount_minor) amount FROM ledger_entries le JOIN orders o ON o.id=le.order_id
        WHERE {revenue_where} GROUP BY le.order_id
    ), gross AS (SELECT i.order_id,SUM(i.quantity*i.unit_price_minor) amount FROM order_items i JOIN fees ON fees.order_id=i.order_id GROUP BY i.order_id)
    SELECT COALESCE(g.name,'Other') name,COALESCE(g.slug,'other') slug,
        SUM(CASE WHEN gross.amount>0 THEN fees.amount*1.0*i.quantity*i.unit_price_minor/gross.amount ELSE 0 END) amount_minor
        FROM fees JOIN gross ON gross.order_id=fees.order_id JOIN order_items i ON i.order_id=fees.order_id
        LEFT JOIN listings l ON l.id=i.listing_id LEFT JOIN games g ON g.id=l.game_id
        GROUP BY g.name,g.slug ORDER BY amount_minor DESC''', args)]
    revenue = sum(x['revenue_minor'] for x in daily); expense = sum(x['expense_minor'] for x in daily)
    for row in games: row['amount_minor'] = round(row['amount_minor'] or 0)
    if games: games[0]['amount_minor'] += revenue-sum(x['amount_minor'] for x in games)
    elif revenue: games = [{'name':'Other','slug':'other','amount_minor':revenue}]
    events = [dict(r) for r in db.execute(f'''SELECT le.id,o.reference,le.amount_minor,le.created_at FROM ledger_entries le JOIN orders o ON o.id=le.order_id
        WHERE {revenue_where} ORDER BY le.created_at DESC,le.id DESC LIMIT 20''', args)]
    expenses = [dict(r) for r in db.execute('''SELECT id,amount_minor,category,description,incurred_on,created_at,voided_at,void_reason
        FROM admin_expenses WHERE book=? AND currency=? AND incurred_on>=? AND incurred_on<?
        ORDER BY incurred_on DESC,created_at DESC,id DESC LIMIT 100''', (book, currency, lo, hi))]
    count = db.execute('SELECT COUNT(*) n FROM admin_expenses WHERE book=? AND currency=? AND incurred_on>=? AND incurred_on<?', (book,currency,lo,hi)).fetchone()['n']
    return {'start':lo,'end':str(end),'book':book,'currency':currency,'test_only':book!='live','timezone':'UTC',
        'gmv_minor':int(gmv['amount']),'paid_orders':gmv['count'],'revenue_minor':revenue,'expense_minor':expense,'profit_minor':revenue-expense,
        'daily':daily,'categories':categories,'games':games,'commissions':events,'expenses':expenses,'expense_count':count,
        'basis':'ledger_commission_minus_recorded_expenses','scope':'marketplace_orders','currencies':sorted(core['ASIA_CURRENCIES'])}


def record_expense(db, ctx, data, core):
    amount = data.get('amount_minor'); book=data.get('book'); currency=data.get('currency')
    checked_scope(book, currency, core)
    if type(amount) is not int or not 1 <= amount <= 10**12:
        raise core['HttpError'](400, 'Xarajat miqdori musbat butun birlikda bo‘lsin (eng ko‘pi 10¹²).')
    category, description, key = data.get('category'), data.get('description'), data.get('id')
    if category not in CATEGORIES or not isinstance(description,str) or not 3 <= len(description.strip()) <= 300:
        raise core['HttpError'](400, 'Kategoriya va 3–300 belgili xarajat izohini kiriting.')
    if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,80}', key):
        raise core['HttpError'](400, 'Xarajat so‘rovini yangilab qayta yuboring.')
    incurred = str(checked_date(data.get('incurred_on'), core))
    values = (amount,currency,book,category,description.strip(),incurred)
    db.execute('BEGIN' if core.get('DATABASE_URL') else 'BEGIN IMMEDIATE')
    try:
        inserted=db.execute('''INSERT INTO admin_expenses(id,amount_minor,currency,book,category,description,incurred_on,created_by)
            VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING RETURNING id''',(key,*values,ctx['uid'])).fetchone()
        if not inserted:
            old=db.execute('SELECT * FROM admin_expenses WHERE id=?',(key,)).fetchone()
            if old['created_by']!=ctx['uid'] or tuple(old[k] for k in ('amount_minor','currency','book','category','description','incurred_on'))!=values:
                raise core['HttpError'](409, 'Bu so‘rov ID si boshqa xarajat uchun ishlatilgan.')
        else: core['audit'](db,ctx['uid'],'expense_recorded','expense',key,{'amount_minor':amount,'currency':currency,'book':book,'category':category})
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK');raise
    return {'id':key,'recorded':True}


def route(db, ctx, method, path, qs, data, core):
    if path == '/api/admin/finance' and method == 'GET':
        core['require_admin'](ctx)
        return report(db, qs, core)
    if path == '/api/admin/expenses' and method == 'POST':
        core['require_admin'](ctx)
        return record_expense(db,ctx,data,core)
    match = re.fullmatch(r'/api/admin/expenses/([A-Za-z0-9_-]{20,80})/void',path)
    if match and method == 'POST':
        core['require_admin'](ctx)
        reason=data.get('reason')
        if not isinstance(reason,str) or not 5<=len(reason.strip())<=300:
            raise core['HttpError'](400,'Bekor qilish sababini 5–300 belgi bilan kiriting.')
        db.execute('BEGIN' if core.get('DATABASE_URL') else 'BEGIN IMMEDIATE')
        try:
            row=db.execute('UPDATE admin_expenses SET voided_at=CURRENT_TIMESTAMP,voided_by=?,void_reason=? WHERE id=? AND voided_at IS NULL RETURNING id',(ctx['uid'],reason.strip(),match[1])).fetchone()
            if not row and not db.execute('SELECT 1 FROM admin_expenses WHERE id=?',(match[1],)).fetchone():
                raise core['HttpError'](404,'Xarajat topilmadi.')
            if row: core['audit'](db,ctx['uid'],'expense_voided','expense',match[1],{'reason':reason.strip()})
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK');raise
        return {'voided':True}
    if path == '/api/admin/audit' and method == 'GET':
        core['require_admin'](ctx)
        # Do not expose arbitrary details_json: old entries can contain private data.
        return [dict(r) for r in db.execute('SELECT id,actor_id,action,entity_type,entity_id,created_at FROM audit_logs ORDER BY created_at DESC,id DESC LIMIT 100')]
    return UNHANDLED

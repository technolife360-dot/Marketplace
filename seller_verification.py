"""Admin-only Didit review data. Store an allowlisted summary, never biometrics."""
import json
import re
from datetime import datetime, timedelta, timezone

PREFIX = 'didit_review:'
CHECKS = ('id_verifications', 'liveness_checks', 'face_matches')


def read(db, uid):
    row = db.execute('SELECT value FROM platform_config WHERE key=?', (PREFIX+uid,)).fetchone()
    try:
        return json.loads(row['value']) if row else {}
    except (ValueError, TypeError):
        return {}


def summary(decision, session_id, status, event_at=None):
    decision = decision if isinstance(decision, dict) else {}
    checks = {}
    for key in CHECKS:
        entries = decision.get(key)
        states = [x.get('status') for x in entries if isinstance(x, dict)] if isinstance(entries, list) else []
        checks[key] = ('Approved' if states and len(states)==len(entries) and all(s == 'Approved' for s in states)
                       else 'Declined' if 'Declined' in states else 'In Review' if states else 'Unavailable')
    docs = decision.get('id_verifications') or []
    doc = docs[0] if isinstance(docs, list) and docs and isinstance(docs[0], dict) else {}
    def text(key, limit=100):
        value = doc.get(key)
        return value[:limit] if isinstance(value, str) else ''
    number = text('document_number')
    return {'session_id': session_id, 'provider_status': status, 'event_at': event_at,
            'checks': checks, 'full_name': text('full_name') or ' '.join(filter(None, [text('first_name'), text('last_name')])),
            'country': text('issuing_state', 3) or text('nationality', 3),
            'document_type': text('document_type', 40), 'document_last4': number[-4:] if number else ''}


def save(db, uid, value):
    db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',
               (PREFIX+uid, json.dumps(value, separators=(',', ':'))))


def state(s):
    if s['verification_status'] == 'rejected': return 'rejected'
    if s['verification_status'] == 'verified' and s['selling_enabled']: return 'approved'
    return 'pending'


def entry(row):
    item = dict(row)
    item['admin_status'] = state(item)
    try: value = json.loads(item.pop('review_json') or '{}')
    except (TypeError, ValueError): value = {}
    item['identity'] = value if value.get('session_id') == item['identity_reference'] else {}
    return item


BASE = """FROM seller_profiles s JOIN users u ON u.id=s.user_id
    LEFT JOIN platform_config c ON c.key='didit_review:'||s.user_id"""
FIELDS = """s.user_id,s.shop_name,s.bio,s.verification_status,s.selling_enabled,s.identity_status,
    s.identity_provider,s.identity_reference,s.identity_verified_at,s.identity_last_event_at,s.created_at,
    u.email,u.display_name,u.country,u.email_verified,c.value review_json"""


def listing(db, qs, core):
    def val(key, default=''): return str(qs.get(key, [default])[0])
    try: page = max(1, min(100000, int(val('page', '1')))); days = int(val('days', '0'))
    except ValueError: raise core['HttpError'](400, 'Invalid verification filter.')
    if days not in (0, 7, 30, 90): raise core['HttpError'](400, 'Choose a supported date range.')
    where, args = [], []
    if days:
        where.append('s.created_at>=?'); args.append((datetime.now(timezone.utc)-timedelta(days=days)).strftime('%Y-%m-%d'))
    status = val('status')
    if status == 'approved': where.append("s.verification_status='verified' AND s.selling_enabled=1")
    elif status == 'rejected': where.append("s.verification_status='rejected'")
    elif status == 'pending': where.append("s.verification_status!='rejected' AND (s.verification_status!='verified' OR s.selling_enabled=0)")
    elif status: raise core['HttpError'](400, 'Invalid verification status.')
    country = val('country')
    if country: where.append('u.country=?'); args.append(country[:3])
    query = val('q').strip()[:100]
    if query:
        where.append("(LOWER(u.display_name) LIKE ? OR LOWER(u.email) LIKE ? OR LOWER(s.shop_name) LIKE ? OR LOWER(s.identity_reference) LIKE ?)")
        args.extend(['%'+query.lower()+'%']*4)
    clause = ' WHERE '+' AND '.join(where) if where else ''
    total = db.execute('SELECT COUNT(*) n '+BASE+clause, args).fetchone()['n']
    rows = db.execute('SELECT '+FIELDS+' '+BASE+clause+' ORDER BY s.created_at DESC,s.user_id LIMIT 25 OFFSET ?', (*args, (page-1)*25)).fetchall()
    counts = db.execute("""SELECT COUNT(*) total,
        COALESCE(SUM(CASE WHEN verification_status='verified' AND selling_enabled=1 THEN 1 ELSE 0 END),0) approved,
        COALESCE(SUM(CASE WHEN verification_status='rejected' THEN 1 ELSE 0 END),0) rejected FROM seller_profiles""").fetchone()
    stats = dict(counts); stats['pending'] = stats['total']-stats['approved']-stats['rejected']
    events = [dict(r) for r in db.execute("""SELECT a.action,a.created_at,a.entity_id,s.shop_name FROM audit_logs a
        LEFT JOIN seller_profiles s ON s.user_id=a.entity_id WHERE a.entity_type='seller'
        AND (a.action LIKE 'didit_identity_%' OR a.action IN ('seller_approve','seller_reject','seller_request_info'))
        ORDER BY a.created_at DESC,a.id DESC LIMIT 12""")]
    chart = [dict(r) for r in db.execute("""SELECT SUBSTR(created_at,1,10) day,action,COUNT(*) count FROM audit_logs
        WHERE entity_type='seller' AND action IN ('seller_approve','seller_reject','didit_identity_started')
        AND created_at>=? GROUP BY SUBSTR(created_at,1,10),action ORDER BY day""",
        ((datetime.now(timezone.utc)-timedelta(days=30)).strftime('%Y-%m-%d'),))]
    last = db.execute("SELECT created_at FROM audit_logs WHERE action IN ('didit_identity_verified','didit_identity_pending','didit_identity_rejected') ORDER BY created_at DESC LIMIT 1").fetchone()
    return {'items':[entry(r) for r in rows], 'total':total, 'page':page, 'page_size':25, 'stats':stats,
            'countries':[r['country'] for r in db.execute('SELECT DISTINCT u.country FROM seller_profiles s JOIN users u ON u.id=s.user_id ORDER BY u.country')],
            'activity':events, 'chart':chart, 'integration':{'configured':core['identity_service'].is_configured(),
            'environment':core['MODE'], 'last_webhook_at':last['created_at'] if last else None,
            'webhook_path':'/api/webhooks/didit'}}


def detail(db, uid, core):
    row = db.execute('SELECT '+FIELDS+' '+BASE+' WHERE s.user_id=?', (uid,)).fetchone()
    if not row: raise core['HttpError'](404, 'Seller not found.')
    result = entry(row)
    events = db.execute("SELECT action,created_at,details_json FROM audit_logs WHERE entity_type='seller' AND entity_id=? ORDER BY created_at DESC,id DESC LIMIT 50", (uid,)).fetchall()
    result['timeline'] = []
    for row in events:
        try: value = json.loads(row['details_json'] or '{}')
        except ValueError: value = {}
        result['timeline'].append({'action':row['action'], 'created_at':row['created_at'], 'note':value.get('note','')})
    return result

"""Browser-specific consent receipts using existing configuration and audit tables."""
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

POLICY_VERSION = '2026-10-30.1'
COOKIE = 'sl_cookie_preferences'
MAX_AGE = 180 * 86400


def token(headers):
    jar = SimpleCookie()
    try:
        jar.load(headers.get('Cookie', ''))
        value = jar[COOKIE].value if COOKIE in jar else ''
    except Exception:
        return ''
    return value if re.fullmatch(r'[A-Za-z0-9_-]{43}', value) else ''


def key(value):
    return 'cookie-consent:' + hashlib.sha256(value.encode()).hexdigest()


def read(db, value):
    if not value:
        return None
    row = db.execute('SELECT value FROM platform_config WHERE key=?', (key(value),)).fetchone()
    try:
        consent = json.loads(row['value']) if row else None
        if (not consent or consent['policy_version'] != POLICY_VERSION
                or datetime.fromisoformat(consent['expires_at']) <= datetime.now(timezone.utc)
                or type(consent['analytics']) is not bool or type(consent['support']) is not bool):
            return None
        return consent
    except (ValueError, KeyError, TypeError):
        return None


def handle(handler, db, ctx, method, data, api):
    value = token(handler.headers)
    if method == 'GET':
        return {'consent': read(db, value)}
    if method != 'POST':
        raise api['HttpError'](405, 'Method not allowed.')
    # Custom header + JSON prevents form CSRF for anonymous browsers. Signed-in
    # requests additionally pass the application's normal CSRF-token check.
    origin = handler.headers.get('Origin', '')
    host = handler.headers.get('Host', '')
    if (handler.headers.get('X-Consent-Request') != '1'
            or handler.headers.get('Sec-Fetch-Site') == 'cross-site'
            or (origin and (urlsplit(origin).netloc != host or urlsplit(origin).scheme not in ('http', 'https')))):
        raise api['HttpError'](403, 'Same-origin consent request required.')
    if not isinstance(data, dict) or set(data) != {'analytics', 'support'} or any(type(data[k]) is not bool for k in data):
        raise api['HttpError'](400, 'Choose analytics and support preferences.')
    api['check_rate'](db, 'cookie-consent', hashlib.sha256(handler.client_address[0].encode()).hexdigest(), limit=30, period=300)
    value = value or secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    consent = {**data, 'essential': True, 'policy_version': POLICY_VERSION,
               'receipt_id': secrets.token_urlsafe(18), 'recorded_at': now.isoformat(timespec='seconds'),
               'expires_at': (now + timedelta(seconds=MAX_AGE)).isoformat(timespec='seconds')}
    db.execute('BEGIN')
    try:
        db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',
                   (key(value), json.dumps(consent)))
        api['audit'](db, ctx['uid'], 'cookie_consent_changed', 'cookie_consent', key(value), consent)
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise
    cookie = f'{COOKIE}={value}; Path=/; HttpOnly; SameSite=Lax; Max-Age={MAX_AGE}'
    if api['MODE'] == 'production':
        cookie += '; Secure'
    return 200, {'consent': consent}, {'Set-Cookie': cookie}

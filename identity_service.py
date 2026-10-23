"""Didit hosted identity verification and signed webhook boundary."""
from __future__ import annotations

from urllib.parse import urlsplit
import hashlib
import hmac
import http.client
import json
import os
import ssl
import time


class IdentityProviderError(Exception):
    pass


def is_configured() -> bool:
    required = all(os.environ.get(name, '').strip() for name in (
        'DIDIT_API_KEY', 'DIDIT_WORKFLOW_ID', 'DIDIT_WEBHOOK_SECRET',
    ))
    if not required:
        return False
    if os.environ.get('MARKETPLACE_MODE', 'development').strip().lower() != 'production':
        return True
    public_url = urlsplit(os.environ.get('PUBLIC_BASE_URL', '').strip())
    return public_url.scheme == 'https' and bool(public_url.hostname) and not public_url.username and not public_url.password


def _api_host() -> str:
    value = os.environ.get('DIDIT_API_BASE_URL', 'https://verification.didit.me').strip().rstrip('/')
    parsed = urlsplit(value)
    if (parsed.scheme != 'https' or parsed.hostname != 'verification.didit.me'
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.path or parsed.query or parsed.fragment):
        raise IdentityProviderError('Didit API manzili ruxsat etilmagan.')
    return parsed.hostname


def create_verification_session(user_reference: str, *, email: str = '', phone: str = '', language: str = 'en') -> dict[str, str]:
    if not is_configured():
        raise IdentityProviderError('Didit ulanishi konfiguratsiya qilinmagan.')
    host = _api_host()
    callback = os.environ.get('PUBLIC_BASE_URL', 'http://localhost:8000').strip().rstrip('/') + '/#seller'
    body = json.dumps({
        'workflow_id': os.environ['DIDIT_WORKFLOW_ID'].strip(),
        'callback': callback,
        'vendor_data': user_reference,
        'language': language if language in ('en', 'uz', 'ru') else 'en',
        'contact_details': {'email': email, **({'phone':phone} if phone else {}), 'send_notification_emails': False},
        'expected_details': {'expected_document_types': ['P', 'ID']},
    }, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'x-api-key': os.environ['DIDIT_API_KEY'].strip(),
        'User-Agent': 'SentryLoot/1.0',
    }
    connection = http.client.HTTPSConnection(host, 443, timeout=12, context=ssl.create_default_context())
    try:
        connection.request('POST', '/v3/session/', body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read(32_768)
        if response.status < 200 or response.status >= 300:
            # Never include upstream bodies: they can expose provider details.
            raise IdentityProviderError('Didit sessiya yaratishni rad etdi. API kaliti, workflow ID va bepul limitni tekshiring.')
        result = json.loads(response_body.decode('utf-8'))
        session_id, verify_url = result.get('session_id'), result.get('url')
        parsed_url = urlsplit(verify_url if isinstance(verify_url, str) else '')
        if (not isinstance(session_id, str) or not session_id or len(session_id) > 100
                or parsed_url.scheme != 'https' or parsed_url.hostname != 'verify.didit.me'
                or parsed_url.username or parsed_url.password):
            raise IdentityProviderError('Didit sessiya javobi noto‘g‘ri.')
        return {'session_id': session_id, 'url': verify_url}
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise IdentityProviderError('Didit xizmatiga hozir ulanib bo‘lmadi.') from exc
    finally:
        connection.close()


def _shorten_floats(value):
    if isinstance(value, dict):
        return {key: _shorten_floats(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_shorten_floats(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def verify_webhook(raw_body: bytes, signature: str, timestamp_header: str) -> dict | None:
    """Verify Didit's V3 canonical-JSON signature and timestamp before returning data."""
    secret = os.environ.get('DIDIT_WEBHOOK_SECRET', '')
    if not secret or not signature or not timestamp_header:
        return None
    try:
        payload = json.loads(raw_body.decode('utf-8'))
        timestamp = payload.get('timestamp') if isinstance(payload, dict) else None
        header_timestamp = int(timestamp_header)
        if isinstance(timestamp, bool) or not isinstance(timestamp, (int, float)) or int(timestamp) != header_timestamp:
            return None
        if abs(int(time.time()) - header_timestamp) > 300:
            return None
        canonical = json.dumps(_shorten_floats(payload), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
        expected = hmac.new(secret.encode('utf-8'), canonical.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            return None
        return payload
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, OverflowError):
        return None


def retrieve_decision(session_id: str) -> dict:
    """Read a bound session only on explicit admin request; never persist media."""
    import re
    if not is_configured() or not isinstance(session_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', session_id):
        raise IdentityProviderError('Didit session is not available.')
    connection = http.client.HTTPSConnection(_api_host(), 443, timeout=8, context=ssl.create_default_context())
    try:
        connection.request('GET', '/v3/session/'+session_id+'/decision/', headers={
            'Accept':'application/json', 'x-api-key':os.environ['DIDIT_API_KEY'].strip(), 'User-Agent':'SentryLoot/1.0'})
        response = connection.getresponse()
        body = response.read(1_048_577)
        if response.status != 200 or len(body)>1_048_576:
            raise IdentityProviderError('Didit report could not be loaded. Please retry.')
        value = json.loads(body.decode('utf-8'))
        if not isinstance(value, dict) or value.get('session_id') != session_id:
            raise IdentityProviderError('Didit returned an unexpected session.')
        return value
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise IdentityProviderError('Didit report is temporarily unavailable.') from exc
    finally:
        connection.close()


def report_media(decision):
    """Only expose known provider media hosts, without forwarding credentials."""
    images = []
    for key, fields in (('id_verifications', (('front_image','Passport / ID front'), ('back_image','Passport / ID back'))),
                        ('liveness_checks', (('reference_image','Selfie'),))):
        entries = decision.get(key) or []
        if not isinstance(entries, list): continue
        for entry in entries[:3]:
            if not isinstance(entry, dict): continue
            for field, label in fields:
                value = entry.get(field)
                parsed = urlsplit(value if isinstance(value, str) else '')
                host = parsed.hostname or ''
                if (parsed.scheme == 'https' and not parsed.username and not parsed.password
                        and any(host == domain or host.endswith('.'+domain) for domain in ('didit.me','amazonaws.com','cloudfront.net'))):
                    images.append({'label':label, 'url':value})
    return images


def phone_request(operation, payload):
    """Standalone Didit phone API. Never return the report, OTP, or upstream body."""
    if operation not in ('send', 'check') or not os.environ.get('DIDIT_API_KEY', '').strip():
        raise IdentityProviderError('Phone verification is not configured yet.')
    connection = http.client.HTTPSConnection(_api_host(), 443, timeout=8, context=ssl.create_default_context())
    try:
        connection.request('POST', '/v3/phone/'+operation+'/',
            body=json.dumps(payload,separators=(',', ':')).encode(), headers={
                'Accept':'application/json', 'Content-Type':'application/json',
                'x-api-key':os.environ['DIDIT_API_KEY'].strip(), 'User-Agent':'SentryLoot/1.0'})
        response = connection.getresponse()
        raw = response.read(65537)
        if response.status == 403:
            raise IdentityProviderError('SMS and WhatsApp verification are not activated. Please contact support.')
        if response.status == 429:
            raise IdentityProviderError('Too many code requests. Please try again later.')
        if response.status == 400:
            raise IdentityProviderError('Check your phone number and verification code.')
        if response.status != 200 or len(raw) > 65536:
            raise IdentityProviderError('Phone verification is temporarily unavailable. Please retry.')
        value = json.loads(raw)
        if not isinstance(value,dict): raise ValueError('Unexpected phone response')
        return value
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise IdentityProviderError('Phone verification is temporarily unavailable. Please retry.') from exc
    finally:
        connection.close()

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


def create_verification_session(user_reference: str) -> dict[str, str]:
    if not is_configured():
        raise IdentityProviderError('Didit ulanishi konfiguratsiya qilinmagan.')
    host = _api_host()
    callback = os.environ.get('PUBLIC_BASE_URL', 'http://localhost:8000').strip().rstrip('/') + '/#seller'
    body = json.dumps({
        'workflow_id': os.environ['DIDIT_WORKFLOW_ID'].strip(),
        'callback': callback,
        'vendor_data': user_reference,
        'language': 'uz',
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

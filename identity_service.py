"""Minimal Sumsub WebSDK token and webhook boundary; identity media stays with Sumsub."""
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
    required = (
        os.environ.get('IDENTITY_PROVIDER', 'disabled').strip().lower() == 'sumsub'
        and bool(os.environ.get('SUMSUB_APP_TOKEN', '').strip())
        and bool(os.environ.get('SUMSUB_SECRET_KEY', ''))
        and bool(os.environ.get('SUMSUB_LEVEL_NAME', '').strip())
        and bool(os.environ.get('SUMSUB_WEBHOOK_SECRET', ''))
    )
    if not required:
        return False
    if os.environ.get('MARKETPLACE_MODE', 'development').strip().lower() != 'production':
        return True
    public_url = urlsplit(os.environ.get('PUBLIC_BASE_URL', '').strip())
    return public_url.scheme == 'https' and bool(public_url.hostname) and not public_url.username and not public_url.password


def _api_host() -> str:
    value = os.environ.get('SUMSUB_API_BASE_URL', 'https://api.sumsub.com').strip().rstrip('/')
    parsed = urlsplit(value)
    host = (parsed.hostname or '').lower()
    if (
        parsed.scheme != 'https'
        or not host.endswith('.sumsub.com')
        or not host.startswith('api.')
        or parsed.username or parsed.password
        or parsed.port not in (None, 443)
        or parsed.path or parsed.query or parsed.fragment
    ):
        raise IdentityProviderError('Sumsub API manzili ruxsat etilmagan.')
    return host


def create_sdk_token(external_user_id: str, email: str) -> str:
    if not is_configured():
        raise IdentityProviderError('Sumsub ulanishi konfiguratsiya qilinmagan.')
    host = _api_host()
    path = '/resources/accessTokens/sdk'
    body = json.dumps({
        'userId': external_user_id,
        'levelName': os.environ['SUMSUB_LEVEL_NAME'].strip(),
        'ttlInSecs': 600,
        'applicantIdentifiers': {'email': email},
    }, separators=(',', ':')).encode('utf-8')
    timestamp = str(int(time.time()))
    signature = hmac.new(
        os.environ['SUMSUB_SECRET_KEY'].encode('utf-8'),
        timestamp.encode('ascii') + b'POST' + path.encode('ascii') + body,
        hashlib.sha256,
    ).hexdigest()
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-App-Token': os.environ['SUMSUB_APP_TOKEN'].strip(),
        'X-App-Access-Ts': timestamp,
        'X-App-Access-Sig': signature,
    }
    connection = http.client.HTTPSConnection(host, 443, timeout=12, context=ssl.create_default_context())
    try:
        connection.request('POST', path, body=body, headers=headers)
        response = connection.getresponse()
        response_body = response.read(16_384)
        if response.status < 200 or response.status >= 300:
            raise IdentityProviderError('Sumsub token berishni rad etdi.')
        result = json.loads(response_body.decode('utf-8'))
        token = result.get('token')
        if not isinstance(token, str) or not token or len(token) > 1024:
            raise IdentityProviderError('Sumsub token javobi noto‘g‘ri.')
        return token
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise IdentityProviderError('Sumsub xizmatiga hozir ulanib bo‘lmadi.') from exc
    finally:
        connection.close()


def verify_webhook(raw_body: bytes, digest: str, digest_alg: str) -> bool:
    secret = os.environ.get('SUMSUB_WEBHOOK_SECRET', '')
    algorithms = {
        'HMAC_SHA256_HEX': hashlib.sha256,
        'HMAC_SHA512_HEX': hashlib.sha512,
    }
    algorithm = algorithms.get(digest_alg.upper())
    if not secret or not digest or algorithm is None:
        return False
    expected = hmac.new(secret.encode('utf-8'), raw_body, algorithm).hexdigest()
    return hmac.compare_digest(expected, digest.lower())

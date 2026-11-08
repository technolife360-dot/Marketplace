"""Private Cloudflare Stream ingestion. Credentials never leave the server."""
import base64
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_BYTES = 200 * 1024 * 1024
MAX_SECONDS = 180


class Unavailable(RuntimeError):
    pass


def configured():
    return bool(re.fullmatch(r'[a-fA-F0-9]{32}', os.getenv('CF_STREAM_ACCOUNT_ID', ''))
                and os.getenv('CF_STREAM_API_TOKEN') and os.getenv('CF_STREAM_SIGNING_KEY_ID')
                and os.getenv('CF_STREAM_SIGNING_KEY_PEM'))


def request(path, method='GET', payload=None, headers=None):
    if not configured():
        raise Unavailable('Video streaming is not configured.')
    url = 'https://api.cloudflare.com/client/v4/accounts/' + os.environ['CF_STREAM_ACCOUNT_ID'] + '/stream' + path
    body = json.dumps(payload).encode() if payload is not None else (b'' if method == 'POST' else None)
    req = Request(url, data=body, method=method, headers={
        'Authorization': 'Bearer ' + os.environ['CF_STREAM_API_TOKEN'],
        'Content-Type': 'application/json', **(headers or {})})
    try:
        with urlopen(req, timeout=12) as response:
            raw = response.read(1024 * 1024)
            data = json.loads(raw) if raw else {}
            if not isinstance(data,dict) or data.get('success') is False:
                raise Unavailable('Video service could not complete this request.')
            return data.get('result', {}), response.headers
    except HTTPError as exc:
        if method == 'DELETE' and exc.code == 404:
            return {}, {}
        raise Unavailable('Video service is temporarily unavailable. Please try again.') from None
    except (URLError, TimeoutError, ValueError):
        raise Unavailable('Video service is temporarily unavailable. Please try again.') from None


def reserve(size, creator):
    expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    metadata = ','.join(k + ' ' + base64.b64encode(str(v).encode()).decode()
                        for k, v in {'maxdurationseconds': MAX_SECONDS, 'expiry': expiry}.items()) + ',requiresignedurls'
    _, headers = request('?direct_user=true', 'POST', headers={
        'Tus-Resumable': '1.0.0', 'Upload-Length': str(size),
        'Upload-Metadata': metadata, 'Upload-Creator': creator})
    uid, location = headers.get('stream-media-id', ''), headers.get('Location', '')
    try:
        parsed = urlsplit(location);port=parsed.port
    except ValueError:raise Unavailable('Video service returned an invalid upload destination.') from None
    if not re.fullmatch('[a-f0-9]{32}', uid) or parsed.scheme != 'https' or parsed.hostname != 'upload.videodelivery.net' or parsed.username or port:
        raise Unavailable('Video service returned an invalid upload destination.')
    return uid, location


def details(uid):
    result=request('/' + uid)[0]
    if not isinstance(result,dict):raise Unavailable('Video service returned an invalid status.')
    return result


def delete(uid):
    request('/' + uid, 'DELETE')


def playback(uid):
    """Local RSA signing scales without a provider request for every play."""
    if not configured() or not re.fullmatch('[a-f0-9]{32}',uid):
        raise Unavailable('Video streaming is not configured.')
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    encode = lambda v: base64.urlsafe_b64encode(v).rstrip(b'=').decode()
    kid = os.environ['CF_STREAM_SIGNING_KEY_ID']
    header = encode(json.dumps({'alg': 'RS256', 'kid': kid}, separators=(',', ':')).encode())
    payload = encode(json.dumps({'sub': uid, 'kid': kid, 'exp': int(time.time()) + 300}, separators=(',', ':')).encode())
    try:
        pem = os.environ['CF_STREAM_SIGNING_KEY_PEM'].replace('\\n', '\n').encode()
        if not pem.startswith(b'-----BEGIN'):
            pem = base64.b64decode(pem)
        key = serialization.load_pem_private_key(pem, password=None)
        signature = key.sign((header + '.' + payload).encode(), padding.PKCS1v15(), hashes.SHA256())
    except (ValueError, TypeError):
        raise Unavailable('Video playback is temporarily unavailable.') from None
    return 'https://iframe.videodelivery.net/' + header + '.' + payload + '.' + encode(signature)

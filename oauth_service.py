"""Server-side Google OpenID Connect and Facebook OAuth helpers (stdlib only)."""
from __future__ import annotations
import base64, hashlib, json, os, secrets, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GOOGLE_ISSUER = 'https://accounts.google.com'
_jwks_cache = {}

def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def unb64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))

def _http_json(url, data=None, headers=None):
    body = urlencode(data).encode() if data is not None else None
    request = Request(url, data=body, headers={'Accept':'application/json', **({'Content-Type':'application/x-www-form-urlencoded'} if body else {}), **(headers or {})})
    with urlopen(request, timeout=12) as response:
        if response.status != 200: raise ValueError('Provider rejected the sign-in request')
        return json.loads(response.read(128 * 1024))

def _jwks(issuer):
    cached = _jwks_cache.get(issuer)
    if cached and cached[0] > time.time(): return cached[1]
    url = 'https://www.googleapis.com/oauth2/v3/certs'
    keys = _http_json(url).get('keys', [])
    if not keys: raise ValueError('Identity provider keys are unavailable')
    _jwks_cache[issuer] = (time.time() + 3600, keys)
    return keys

def verify_id_token(token, provider, client_id, nonce):
    if not isinstance(token, str) or len(token) > 16_384: raise ValueError('Invalid identity token')
    parts = token.split('.')
    if len(parts) != 3: raise ValueError('Invalid identity token')
    header, claims = json.loads(unb64url(parts[0])), json.loads(unb64url(parts[1]))
    if header.get('alg') != 'RS256': raise ValueError('Unsupported identity token signature')
    issuer = GOOGLE_ISSUER
    key = next((item for item in _jwks(issuer) if item.get('kid') == header.get('kid') and item.get('kty') == 'RSA'), None)
    if not key: raise ValueError('Identity provider key not found')
    n, e = int.from_bytes(unb64url(key['n']), 'big'), int.from_bytes(unb64url(key['e']), 'big')
    signature = unb64url(parts[2]); modulus_bytes = (n.bit_length() + 7) // 8
    if len(signature) != modulus_bytes: raise ValueError('Invalid identity token signature')
    signed = pow(int.from_bytes(signature, 'big'), e, n).to_bytes(modulus_bytes, 'big')
    digest_info = bytes.fromhex('3031300d060960864801650304020105000420') + hashlib.sha256((parts[0] + '.' + parts[1]).encode()).digest()
    padding = b'\x00\x01' + b'\xff' * (modulus_bytes-len(digest_info)-3) + b'\x00' + digest_info
    if not secrets.compare_digest(signed, padding): raise ValueError('Invalid identity token signature')
    now = int(time.time())
    if claims.get('iss') not in (GOOGLE_ISSUER, 'accounts.google.com'): raise ValueError('Invalid identity token issuer')
    if claims.get('aud') != client_id or int(claims.get('exp', 0)) <= now or int(claims.get('iat', now+1)) > now+60: raise ValueError('Expired or invalid identity token')
    if not secrets.compare_digest(str(claims.get('nonce', '')), nonce): raise ValueError('Sign-in nonce mismatch')
    if not claims.get('sub'): raise ValueError('Identity provider did not return a subject')
    verified = claims.get('email_verified')
    if verified not in (True, 'true'): raise ValueError('Provider email is not verified')
    email = claims.get('email', '').strip().lower()
    if not email or len(email) > 254: raise ValueError('Provider did not return an email address')
    return {'subject': claims['sub'], 'email': email, 'name': claims.get('name') or email.split('@')[0]}

def google_authorization_url(client_id, redirect_uri, state, nonce):
    return 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({'client_id':client_id,'redirect_uri':redirect_uri,'response_type':'code','scope':'openid email profile','state':state,'nonce':nonce,'prompt':'select_account'})

def facebook_authorization_url(client_id, redirect_uri, state):
    return 'https://www.facebook.com/v22.0/dialog/oauth?' + urlencode({'client_id':client_id,'redirect_uri':redirect_uri,'response_type':'code','scope':'public_profile,email','state':state})

def exchange_code(provider, code, redirect_uri, nonce):
    if provider == 'google':
        client_id, secret = os.environ.get('GOOGLE_CLIENT_ID',''), os.environ.get('GOOGLE_CLIENT_SECRET','')
        if not client_id or not secret: raise ValueError('Google Sign In is not configured')
        response = _http_json('https://oauth2.googleapis.com/token', {'code':code,'client_id':client_id,'client_secret':secret,'redirect_uri':redirect_uri,'grant_type':'authorization_code'})
        return verify_id_token(response.get('id_token'), provider, client_id, nonce)
    client_id, secret = os.environ.get('FACEBOOK_APP_ID',''), os.environ.get('FACEBOOK_APP_SECRET','')
    if not client_id or not secret: raise ValueError('Facebook Login is not configured')
    token = _http_json('https://graph.facebook.com/v22.0/oauth/access_token?' + urlencode({'client_id':client_id,'client_secret':secret,'redirect_uri':redirect_uri,'code':code}))
    access_token = token.get('access_token')
    if not isinstance(access_token, str) or not access_token or len(access_token) > 4096: raise ValueError('Facebook did not return an access token')
    profile = _http_json('https://graph.facebook.com/v22.0/me?fields=id,name,email', headers={'Authorization':'Bearer '+access_token})
    subject, email = profile.get('id'), profile.get('email')
    if not isinstance(subject, str) or not subject or len(subject) > 255: raise ValueError('Facebook did not return a user ID')
    if not isinstance(email, str) or not email.strip() or len(email.strip()) > 254: raise ValueError('Facebook did not return an email address')
    email=email.strip().lower()
    return {'subject':subject,'email':email,'name':profile.get('name') or email.split('@')[0]}

"""Minimal, server-side Google and Apple OpenID Connect helpers (stdlib only)."""
from __future__ import annotations
import base64, hashlib, json, os, secrets, subprocess, time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GOOGLE_ISSUER = 'https://accounts.google.com'
APPLE_ISSUER = 'https://appleid.apple.com'
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
    url = 'https://www.googleapis.com/oauth2/v3/certs' if issuer == GOOGLE_ISSUER else 'https://appleid.apple.com/auth/keys'
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
    issuer = GOOGLE_ISSUER if provider == 'google' else APPLE_ISSUER
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
    if claims.get('iss') not in ((GOOGLE_ISSUER, 'accounts.google.com') if provider == 'google' else (APPLE_ISSUER,)): raise ValueError('Invalid identity token issuer')
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

def apple_authorization_url(client_id, redirect_uri, state, nonce):
    # Apple requires form_post when requesting name/email scopes.
    return 'https://appleid.apple.com/auth/authorize?' + urlencode({'client_id':client_id,'redirect_uri':redirect_uri,'response_type':'code','response_mode':'form_post','scope':'name email','state':state,'nonce':nonce})

def _ec_client_secret(team_id, key_id, client_id, private_key):
    now = int(time.time())
    head = b64url(json.dumps({'alg':'ES256','kid':key_id,'typ':'JWT'},separators=(',',':')).encode())
    body = b64url(json.dumps({'iss':team_id,'iat':now,'exp':now+300,'aud':APPLE_ISSUER,'sub':client_id},separators=(',',':')).encode())
    message = (head + '.' + body).encode()
    pem = private_key.replace('\\n','\n').encode()
    # openssl's dgst needs a private key file; use a private temporary file with restrictive permissions.
    import tempfile
    fd, path = tempfile.mkstemp(prefix='bozorgg-apple-', suffix='.pem')
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd,'wb') as stream: stream.write(pem)
        signature = subprocess.run(['openssl','dgst','-sha256','-sign',path],input=message,stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True).stdout
    finally:
        try: os.unlink(path)
        except OSError: pass
    # DER ECDSA signature -> JOSE's fixed-width r || s encoding.
    def der_int(buf, pos):
        if buf[pos] != 2: raise ValueError('Invalid ECDSA signature')
        size=buf[pos+1]; val=buf[pos+2:pos+2+size]; return int.from_bytes(val,'big'),pos+2+size
    if not signature or signature[0] != 0x30: raise ValueError('Invalid ECDSA signature')
    r, pos = der_int(signature, 2); s, _ = der_int(signature, pos)
    return head + '.' + body + '.' + b64url(r.to_bytes(32,'big') + s.to_bytes(32,'big'))

def exchange_code(provider, code, redirect_uri, nonce):
    if provider == 'google':
        client_id, secret = os.environ.get('GOOGLE_CLIENT_ID',''), os.environ.get('GOOGLE_CLIENT_SECRET','')
        if not client_id or not secret: raise ValueError('Google Sign In is not configured')
        response = _http_json('https://oauth2.googleapis.com/token', {'code':code,'client_id':client_id,'client_secret':secret,'redirect_uri':redirect_uri,'grant_type':'authorization_code'})
        return verify_id_token(response.get('id_token'), provider, client_id, nonce)
    client_id=os.environ.get('APPLE_SERVICE_ID',''); team=os.environ.get('APPLE_TEAM_ID',''); key=os.environ.get('APPLE_KEY_ID',''); private=os.environ.get('APPLE_PRIVATE_KEY','')
    if not all((client_id,team,key,private)): raise ValueError('Apple Sign In is not configured')
    secret=_ec_client_secret(team,key,client_id,private)
    response=_http_json('https://appleid.apple.com/auth/token', {'client_id':client_id,'client_secret':secret,'code':code,'grant_type':'authorization_code','redirect_uri':redirect_uri})
    return verify_id_token(response.get('id_token'), provider, client_id, nonce)

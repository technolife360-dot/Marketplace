"""Server-only Cloudflare R2 object storage for marketplace images."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from urllib.parse import quote, urlparse


def _settings():
    account = os.environ.get('R2_ACCOUNT_ID', '').strip()
    access_key = os.environ.get('R2_ACCESS_KEY_ID', '').strip()
    secret_key = os.environ.get('R2_SECRET_ACCESS_KEY', '').strip()
    listing_bucket = os.environ.get('R2_LISTING_BUCKET', '').strip()
    evidence_bucket = os.environ.get('R2_EVIDENCE_BUCKET', '').strip()
    public_base = os.environ.get('R2_PUBLIC_BASE_URL', '').strip().rstrip('/')
    try:
        parsed = urlparse(public_base)
        valid_port = parsed.port is None
    except ValueError:
        raise RuntimeError('Invalid R2 public domain') from None
    valid_domain = (parsed.scheme == 'https' and bool(parsed.hostname) and
                    not parsed.username and not parsed.password and valid_port and
                    not parsed.path and not parsed.query and not parsed.fragment and
                    parsed.hostname != 'r2.dev' and not parsed.hostname.endswith('.r2.dev') and
                    not parsed.hostname.endswith('.r2.cloudflarestorage.com'))
    valid_buckets = (bool(re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', listing_bucket)) and
                     bool(re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', evidence_bucket)) and
                     listing_bucket != evidence_bucket)
    if not (re.fullmatch(r'[0-9a-fA-F]{32}', account) and access_key and secret_key and valid_buckets and valid_domain):
        raise RuntimeError('Cloudflare R2 account, scoped keys, separate buckets and public custom domain are required')
    return account, access_key, secret_key, listing_bucket, evidence_bucket, public_base


def is_configured():
    try:
        _settings()
        return True
    except RuntimeError:
        return False


@lru_cache(maxsize=1)
def _client():
    import boto3
    from botocore.config import Config

    account, access_key, secret_key, _, _, _ = _settings()
    return boto3.client(
        's3', endpoint_url=f'https://{account}.r2.cloudflarestorage.com',
        aws_access_key_id=access_key, aws_secret_access_key=secret_key,
        region_name='auto', config=Config(signature_version='s3v4',
                                          connect_timeout=5, read_timeout=15, retries={'max_attempts': 2}),
    )


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{20,24}/[0-9a-f]{40,48}\.webp', value):
        raise ValueError('Invalid R2 object key')
    return value


def _listing_key(value):
    # Preserve existing listing URLs; new uploads are separated by their owner role.
    if isinstance(value, str) and value.startswith(('visitor-images/', 'admin-images/')):
        _key(value.split('/', 1)[1])
        return value
    return _key(value)


def is_listing_url(value):
    """Accept only object URLs generated for this deployment's listing bucket."""
    try:
        public_base = _settings()[5]
        prefix = public_base + '/'
        if not isinstance(value, str) or not value.startswith(prefix):
            return False
        _listing_key(value[len(prefix):])
        return True
    except (RuntimeError, ValueError):
        return False


def delete_listing(public_url):
    """Delete an application-owned public image; never accept another domain."""
    if not is_listing_url(public_url):
        raise ValueError('Invalid public image URL')
    _, _, _, bucket, _, public_base = _settings()
    key = _listing_key(public_url[len(public_base) + 1:])
    _client().delete_object(Bucket=bucket, Key=key)


def check_evidence_bucket():
    _, _, _, _, bucket, _ = _settings()
    _client().head_bucket(Bucket=bucket)


def put_evidence(key, body):
    key = _key(key)
    _, _, _, _, bucket, _ = _settings()
    _client().put_object(Bucket=bucket, Key=key, Body=body, ContentType='image/webp',
                         CacheControl='private, no-store')

def put_video_evidence(key,body):
    key=_key(key)
    _,_,_,_,bucket,_=_settings()
    _client().put_object(Bucket=bucket,Key=key,Body=body,ContentType='video/mp4',CacheControl='private, no-store',ContentDisposition='inline; filename="evidence.mp4"')


def evidence_url(key):
    key = _key(key)
    _, _, _, _, bucket, _ = _settings()
    return _client().generate_presigned_url('get_object', Params={'Bucket': bucket, 'Key': key}, ExpiresIn=300)


def delete_evidence(key):
    key = _key(key)
    _, _, _, _, bucket, _ = _settings()
    _client().delete_object(Bucket=bucket, Key=key)


def put_listing(key, body, *, audience='visitor'):
    if audience not in ('visitor','admin'):
        raise ValueError('Invalid public image audience')
    key = ('admin-images/' if audience=='admin' else 'visitor-images/') + _key(key)
    _, _, _, bucket, _, public_base = _settings()
    _client().put_object(Bucket=bucket, Key=key, Body=body, ContentType='image/webp',
                         CacheControl='public, max-age=31536000, immutable')
    return f'{public_base}/{quote(key, safe="/")}'


def put_catalog_art(slug, body):
    """Maintenance-only small public artwork, isolated from visitor uploads.

    The image importer validates/re-encodes raster inputs before calling this.
    Content-addressed keys allow immutable caching without overwriting artwork.
    """
    import hashlib
    if not isinstance(slug,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,98}[a-z0-9]',slug):
        raise ValueError('Invalid catalogue identity')
    if not isinstance(body,bytes) or not 12<len(body)<=24*1024 or body[:4]!=b'RIFF' or body[8:12]!=b'WEBP':
        raise ValueError('Invalid catalogue WebP thumbnail')
    digest=hashlib.sha256(body).hexdigest()[:20]
    key=f'admin-images/catalogue-icons/v1/{slug}-{digest}.webp'
    _,_,_,bucket,_,public_base=_settings()
    _client().put_object(Bucket=bucket,Key=key,Body=body,ContentType='image/webp',
                         CacheControl='public, max-age=31536000, immutable')
    return f'{public_base}/{key}'

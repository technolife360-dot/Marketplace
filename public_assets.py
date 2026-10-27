"""Verified public site artwork hosted directly on Cloudflare R2.

Only known public artwork is mapped. Private evidence and arbitrary URLs are never rewritten.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit

SITE_ASSET_BASE = 'https://images.gamestorehub.com/site-assets/'
BRAND_IMAGE_URL = 'https://gamestorehub.com/static/assets/sentryloot-mark.png'
IMAGE_MANIFEST = json.loads(Path(__file__).with_name('public-image-manifest.json').read_text())

def image_url(value):
    if not isinstance(value, str):
        return value
    try:
        parsed = urlsplit(value)
    except ValueError:
        return value
    if parsed.netloc and (parsed.scheme != 'https' or parsed.netloc != 'gamestorehub.com'):
        return value
    entry = IMAGE_MANIFEST.get(parsed.path)
    if not entry:
        return value
    return entry['url'] + ('?' + parsed.query if parsed.query else '') + ('#' + parsed.fragment if parsed.fragment else '')

def rewrite_payload(value):
    if isinstance(value, dict):
        return {key: rewrite_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [rewrite_payload(item) for item in value]
    return image_url(value)

#!/usr/bin/env python3
"""Move existing public Supabase listing images to R2 after R2 is configured.

Dry-run by default. Set DATABASE_URL in the process environment and pass the
exact old Supabase project URL. The script never reads private evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage_r2


def legacy_url(value, prefix):
    if not isinstance(value, str) or not value.startswith(prefix):
        return False
    parsed = urlparse(value)
    return parsed.scheme == 'https' and not parsed.query and not parsed.fragment and '..' not in parsed.path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--supabase-project-url', required=True, help='Exact https://<project>.supabase.co origin')
    parser.add_argument('--apply', action='store_true', help='Upload and update listing rows')
    args = parser.parse_args()
    origin = args.supabase_project_url.rstrip('/')
    parsed = urlparse(origin)
    if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.supabase.co') or parsed.path or parsed.query or parsed.fragment:
        parser.error('The Supabase project URL must be an HTTPS supabase.co origin')
    prefix = origin + '/storage/v1/object/public/listing-images/'
    database_url = os.environ.get('DATABASE_URL', '').strip()
    if not database_url:
        parser.error('DATABASE_URL must be supplied as a server-side environment variable')
    if args.apply and not storage_r2.is_configured():
        parser.error('Cloudflare R2 is not fully configured')

    import psycopg
    from psycopg.rows import dict_row

    moved = {}
    with psycopg.connect(database_url, row_factory=dict_row) as db:
        rows = db.execute('SELECT id,image_url,attributes_json FROM public.listings').fetchall()
        candidates = []
        for row in rows:
            attrs = json.loads(row['attributes_json'] or '{}')
            images = attrs.get('images', [])
            urls = [row['image_url'] or ''] + (images if isinstance(images, list) else [])
            old = sorted({url for url in urls if legacy_url(url, prefix)})
            if old:
                candidates.append((row, attrs, old))
        print(f'{len(candidates)} listing(s), {len(set(url for _, _, urls in candidates for url in urls))} unique legacy image(s)')
        if not args.apply:
            print('Dry run only; pass --apply after R2 buckets and public domain are ready.')
            return
        for row, attrs, urls in candidates:
            for url in urls:
                if url in moved:
                    continue
                with urlopen(url, timeout=15) as response:
                    if response.headers.get_content_type() != 'image/webp':
                        raise RuntimeError('Legacy image is not WebP; migration stopped')
                    body = response.read(5 * 1024 * 1024 + 1)
                if not body or len(body) > 5 * 1024 * 1024 or body[:4] != b'RIFF' or body[8:12] != b'WEBP':
                    raise RuntimeError('Legacy image is invalid or too large; migration stopped')
                digest = hashlib.sha256(url.encode()).hexdigest()
                moved[url] = storage_r2.put_listing(f'{digest[:20]}/{digest[20:60]}.webp', body)
            new_image = moved.get(row['image_url'], row['image_url'])
            if isinstance(attrs.get('images'), list):
                attrs['images'] = [moved.get(url, url) for url in attrs['images']]
            changed = db.execute('UPDATE public.listings SET image_url=%s,attributes_json=%s WHERE id=%s AND image_url=%s',
                                 (new_image, json.dumps(attrs, ensure_ascii=False), row['id'], row['image_url']))
            if changed.rowcount != 1:
                raise RuntimeError('Listing changed during migration; stopped without overwriting the newer version')
            db.commit()
        print(f'Migrated {len(candidates)} listing(s) and {len(moved)} image(s). Verify URLs before removing legacy objects.')


if __name__ == '__main__':
    main()

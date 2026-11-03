#!/usr/bin/env python3
"""Refresh the read-only Melostore catalogue using existing server credentials.

Run from the project root: python3 scripts/sync_melostore_catalog.py
The current snapshot retains dashboard-only entries and image fallbacks.
"""
import json
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import melostore_catalog as catalog


def fetch(path, key, secret):
    request = Request('https://api.melostore.id/api/v1/h2h/' + path,
                      headers={'Accept': 'application/json', 'X-API-Key': key,
                               'X-Secret-Key': secret, 'User-Agent': 'SentryLoot-Catalog/1.0'})
    with urlopen(request, timeout=60) as response:
        raw = response.read(40000001)
    if len(raw) > 40000000:
        raise ValueError('Catalogue response exceeds the size limit')
    payload = json.loads(raw)
    if payload.get('success') is not True or not isinstance(payload.get('data'), list):
        raise ValueError('Supplier did not return a valid catalogue')
    if payload.get('meta', {}).get('pagination', {}).get('has_more'):
        raise ValueError('Supplier returned an incomplete catalogue; previous snapshot retained')
    return payload


def main():
    env = dict(os.environ)
    env_path = Path(env.get('SENTRYLOOT_ENV_FILE') or Path.home() / 'Desktop/SentryLoot-Secrets/.env')
    if not env_path.is_file():
        env_path = catalog.SNAPSHOT.parent.parent / '.env'
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                name, value = line.split('=', 1)
                env.setdefault(name.strip(), value.strip().strip('\"').strip("'"))
    key, secret = env.get('H2H_API_KEY'), env.get('H2H_API_SECRET') or env.get('H2H_SECRET_KEY')
    if not key or not secret:
        raise ValueError('H2H_API_KEY and H2H_API_SECRET are required')
    brands = fetch('pricelists/categories', key, secret)
    prices = fetch('pricelists', key, secret)
    dashboard = [{key: row[key] for key in ('slug', 'name', 'category', 'image_url')}
                 for row in catalog.snapshot()['items']]
    result = catalog.build_snapshot(brands['data'], prices, dashboard,
                                    datetime.now(timezone.utc).isoformat())
    # Retain the owner's explicitly pinned PUBG offer catalogue.
    previous_pubg = next((row for row in catalog.snapshot()['items'] if row['slug'] == 'pubg-mobile'), None)
    if previous_pubg:
        for item in result['items']:
            if item['slug'] == 'pubg-mobile':
                item['packages'] = previous_pubg['packages']
        result['product_count'] = sum(len(item['packages']) for item in result['items'])
    review_dir = catalog.SNAPSHOT.parent.parent / 'secrets'
    review_dir.mkdir(mode=0o700, exist_ok=True)
    review = review_dir / 'topup-price-review.csv'
    by_sku = {row['sku_code']: row for row in prices['data']}
    with review.open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['game','type','package','sku','supplier_cost_idr','selling_price_usd'])
        for item in result['items']:
            for sku in result['selected_skus'].get(item['slug'], []):
                row = by_sku[sku]
                writer.writerow([item['name'], row.get('type_name',''), row['name'], sku, row['price'], ''])
    review.chmod(0o600)
    temporary = catalog.SNAPSHOT.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')) + '\n')
    temporary.replace(catalog.SNAPSHOT)
    print(f"Published {len(result['items'])} brands and {result['product_count']} packages.")


if __name__ == '__main__':
    try:
        main()
    except HTTPError as error:
        sys.exit(f'Supplier returned HTTP {error.code}; previous catalogue retained.')
    except (URLError, TimeoutError, ValueError) as error:
        sys.exit(f'Catalogue refresh failed ({type(error).__name__}); previous catalogue retained.')

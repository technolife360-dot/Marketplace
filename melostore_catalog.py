"""Published H2H catalogue snapshot. Supplier costs and credentials stay private.

Source contract: https://h2h.melostore.id/en/docs#categories and #getPricelist.
This module exposes catalogue data only; it never places supplier orders.
"""
import copy
import json
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

SNAPSHOT = Path(__file__).resolve().parent / 'data' / 'melostore-catalog.json'
CATEGORIES = ('game', 'gift-card', 'social', 'ewallet', 'airtime-data', 'pln', 'apps-subscriptions')
LEGACY = {'PUBG Mobile (Global)': 'pubg-mobile', 'Mobile Legends (Global)': 'mobile-legends',
          'Free Fire (Global)': 'free-fire', 'Honor of Kings': 'honor-of-kings'}
CATEGORY_NAMES = {'Game': 'game', 'Gift Card': 'gift-card', 'Social': 'social',
                  'Ewallet': 'ewallet', 'Airtime & Data (Pulsa & Data)': 'airtime-data',
                  'PLN': 'pln', 'Aplikasi & Langganan': 'apps-subscriptions'}


def build_snapshot(brands, pricelist, dashboard, captured_at):
    """Whitelist supplier fields and preserve brands not present in the API yet."""
    import re
    source_images = {str(row['id']): row.get('thumbnail') or ''
                     for row in pricelist['meta']['brands']}
    ui_by_name = defaultdict(list)
    for row in dashboard:
        ui_by_name[row['name'].strip()].append(row)
    products = defaultdict(list)
    seen_skus = set()
    for row in pricelist['data']:
        sku = str(row['sku_code'])
        if sku in seen_skus:
            raise ValueError('Duplicate supplier SKU in catalogue')
        seen_skus.add(sku)
        products[str(row['brand_id'])].append({
            'sku': sku, 'name': row['name'], 'status': row['status'],
            'type_name': row.get('type_name') or '',
            'server_name': row.get('server_name') or '',
        })
    items = []
    used_slugs = set()
    matched_ui = set()
    for brand in brands:
        name = brand['name'].strip()
        category = CATEGORY_NAMES.get((brand.get('category') or {}).get('name'))
        if category not in CATEGORIES:
            raise ValueError('Unmapped supplier category')
        matches = ui_by_name[name]
        ui = next((row for row in matches if id(row) not in matched_ui), {})
        if ui:
            matched_ui.add(id(ui))
        slug = LEGACY.get(name) or 'h2h-' + str(brand['brand_id']) + '-' + brand['slug']
        if not re.fullmatch(r'[a-z0-9-]+', slug) or slug in used_slugs:
            raise ValueError('Invalid or duplicate catalogue slug')
        used_slugs.add(slug)
        image = source_images.get(str(brand['brand_id'])) or ui.get('image_url', '')
        items.append({'slug': slug, 'name': name, 'category': category,
                      'image_url': image, 'supplier_brand_id': brand['brand_id'],
                      'supplier_slug': brand['slug'], 'packages': products[str(brand['brand_id'])]})
    for index, row in enumerate(dashboard):
        if id(row) in matched_ui:
            continue
        slug = row.get('slug') or 'h2h-dashboard-' + str(index + 1)
        items.append({'slug': slug, 'name': row['name'], 'category': row['category'],
                      'image_url': row['image_url'], 'packages': []})
    for item in items:
        image = item['image_url']
        if image and not image.startswith('https://cdn.melostore.id/'):
            raise ValueError('Unexpected catalogue image host')
    return {'source': 'https://h2h.melostore.id/dashboard/order',
            'api_source': 'https://api.melostore.id/api/v1/h2h/pricelists',
            'captured_at': captured_at, 'product_count': len(seen_skus), 'items': items}


@lru_cache(maxsize=1)
def snapshot():
    return json.loads(SNAPSHOT.read_text(encoding='utf-8'))


def public_catalog(existing):
    """Keep existing prices, packages, reviews and URLs, enrich with supplier brands."""
    by_slug = {item['slug']: item for item in existing}
    result = []
    for source in snapshot()['items']:
        item = copy.deepcopy(by_slug.pop(source['slug'], None) or {
            'slug': source['slug'], 'name': source['name'], 'currency': '', 'packages': [],
            'review_summary': {'count': 0, 'rating': None}})
        item.update(category=source['category'], image_url=source['image_url'],
                    source='melostore', supplier_name=source['name'],
                    supplier_package_count=len(source['packages']))
        result.append(item)
    result.extend(by_slug.values())
    return result


def brand_detail(slug):
    source = next((row for row in snapshot()['items'] if row['slug'] == slug), None)
    if source is None:
        return None
    return {'slug': source['slug'], 'name': source['name'], 'category': source['category'],
            'image_url': source['image_url'], 'packages': copy.deepcopy(source['packages']),
            'captured_at': snapshot()['captured_at'], 'purchasable': False}


# Approved storefront prices are USD cents, independent of supplier cost and FX.
PUBG_TEST_OFFERS = {
    'pubgmgl60eu-s2': (60, 99), 'pubgmgl120u-s13': (120, 198),
    'pubgmgl325u-s7': (325, 499), 'pubgmgl660u-s7': (660, 899),
    'pubgmgl1800u-s7': (1800, 2499), 'pubgmgl3850u-s7': (3850, 4999),
    'pubgmgl8100uco-s11': (8100, 9999), 'pubgmgl16200uco-s11': (16200, 18999),
    'pubgmgl24300uco-s11': (24300, 28999), 'pubgmgl32400uco-s11': (32400, 37999),
    'pubgmgl40500uco-s11': (40500, 46999),
}


def test_checkout_offer(sku):
    if not isinstance(sku, str) or sku not in PUBG_TEST_OFFERS:
        return None
    brand = brand_detail('pubg-mobile')
    pack = next((p for p in brand['packages'] if p['sku'] == sku and p['status'] == 'active'), None) if brand else None
    if not pack:
        return None
    amount, cents = PUBG_TEST_OFFERS[sku]
    return {'id': 'h2h-test-'+sku, 'sku': sku, 'game_slug': 'pubg-mobile',
            'game_name': brand['name'], 'amount': amount, 'price_minor': cents,
            'currency': 'USD', 'enabled': 1}

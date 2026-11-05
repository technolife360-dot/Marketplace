"""Published H2H catalogue snapshot. Supplier costs and credentials stay private.

Source contract: https://h2h.melostore.id/en/docs#categories and #getPricelist.
This module exposes catalogue data only; it never places supplier orders.
"""
import copy
import json
import re
from decimal import Decimal, InvalidOperation
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


def product_identity(row):
    """Keep bonus, region and eligibility qualifiers; merge only equivalent labels."""
    def normalize(value):
        value = re.sub(r'(?<=\d)[.,](?=\d{3}(?:\D|$))', '', str(value or ''))
        return re.sub(r'\s+', ' ', value.strip().casefold())
    return normalize(row.get('type_name')), normalize(row.get('name'))


def cheapest_active(rows):
    """Choose a real priced SKU per product, never treating missing cost as zero."""
    winners = {}
    for row in rows:
        if row.get('status') != 'active':
            continue
        try:
            price = Decimal(str(row.get('price')))
        except InvalidOperation:
            continue
        if not price.is_finite() or price <= 0:
            continue
        identity = product_identity(row)
        previous = winners.get(identity)
        if previous is None or (price, str(row['sku_code'])) < (Decimal(str(previous['price'])), str(previous['sku_code'])):
            winners[identity] = row
    return list(winners.values())


def customer_fields(row, pricelist):
    form = pricelist.get('meta', {}).get('inquiry_forms', {}).get(row.get('inquiry_form_key'), {})
    return [{key: field[key] for key in ('key', 'name', 'type', 'options', 'required') if key in field}
            for field in form.get('fields', []) if isinstance(field, dict)]


def build_snapshot(brands, pricelist, dashboard, captured_at):
    """Whitelist supplier fields and preserve brands not present in the API yet."""
    import re
    source_images = {str(row['id']): row.get('thumbnail') or ''
                     for row in pricelist['meta']['brands']}
    ui_by_name = defaultdict(list)
    for row in dashboard:
        ui_by_name[row['name'].strip()].append(row)
    products = defaultdict(list)
    priced_products = defaultdict(list)
    seen_skus = set()
    for row in pricelist['data']:
        sku = str(row['sku_code'])
        if sku in seen_skus:
            raise ValueError('Duplicate supplier SKU in catalogue')
        seen_skus.add(sku)
        priced_products[str(row['brand_id'])].append(row)
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
    selected_skus, fields = {}, {}
    for item in items:
        if item['category'] != 'game' or item['slug'] == 'pubg-mobile':
            continue
        chosen = cheapest_active(priced_products.get(str(item.get('supplier_brand_id')), []))
        selected_skus[item['slug']] = [row['sku_code'] for row in chosen]
        for row in chosen:
            fields[row['sku_code']] = customer_fields(row, pricelist)
    return {'selected_skus': selected_skus, 'customer_fields': fields,
            'source': 'https://h2h.melostore.id/dashboard/order',
            'api_source': 'https://api.melostore.id/api/v1/h2h/pricelists',
            'captured_at': captured_at, 'product_count': len(seen_skus), 'items': items}


@lru_cache(maxsize=1)
def snapshot():
    return json.loads(SNAPSHOT.read_text(encoding='utf-8'))


def home_topups():
    """Small public discovery payload; reuse existing supplier routes, without SKUs/costs."""
    featured = json.loads((SNAPSHOT.parent / 'home-topups.json').read_text())
    available = {item['slug'] for item in snapshot()['items']}
    return [{key: item[key] for key in
             ('slug', 'name', 'subtitle', 'image_url', 'image_width', 'image_height')}
            for item in featured if item['slug'] in available]


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


PUBG_UC_IMAGES = {60: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-60-fb20cf08f23726561cad.png',
 120: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-60-fb20cf08f23726561cad.png',
 325: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-325-85435b1177274290ffa4.png',
 660: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-660-d13614ca681176e4933e.png',
 1800: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-1800-7bb36b5b3e0469a1c5ea.png',
 3850: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-3850-85221069277b2a04b20a.png',
 8100: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-8100-2a3df645de68e9091972.png',
 16200: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-16200-2a3df645de68e9091972.png',
 24300: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-24300-2a3df645de68e9091972.png',
 32400: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-32400-2a3df645de68e9091972.png',
 40500: 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-40500-2a3df645de68e9091972.png'}


GAME_BANNERS = {
    'pubg-mobile': 'https://images.gamestorehub.com/site-assets/topup/pubg-mobile/hero-f39ccb5ddd387864bb28.png',
    'mobile-legends': 'https://images.gamestorehub.com/site-assets/topup/mobile-legends/hero-8a7908bdd8f08d46201c.png'
}


def brand_detail(slug):
    source = next((row for row in snapshot()['items'] if row['slug'] == slug), None)
    if source is None:
        return None
    selected = snapshot().get('selected_skus', {}).get(slug)
    packages = copy.deepcopy(source['packages'])
    if selected is not None and slug != 'pubg-mobile':
        allowed = set(selected)
        packages = [pack for pack in packages if pack['sku'] in allowed and pack['status'] == 'active']
        for pack in packages:
            pack['inquiry_fields'] = copy.deepcopy(snapshot().get('customer_fields', {}).get(pack['sku'], []))
    if slug == 'pubg-mobile':
        for pack in packages:
            if pack.get('type_name') not in ('Unknown Cash', 'UC'):
                continue
            label = str(pack.get('name', '')).replace('Unknown Cash', '').replace('UC', '').strip()
            digits = label.replace('.', '').replace(',', '')
            if digits.isdigit() and int(digits) in PUBG_UC_IMAGES:
                pack['image_url'] = PUBG_UC_IMAGES[int(digits)]
    return {'slug': source['slug'], 'name': source['name'], 'category': source['category'],
            'image_url': source['image_url'], 'banner_url': GAME_BANNERS.get(slug, ''), 'packages': packages,
            'captured_at': snapshot()['captured_at'], 'purchasable': False}


# Approved storefront prices are USD cents, independent of supplier cost and FX.
PUBG_TEST_OFFERS = {
    'pubgmgl60eu-s2': (60, 99), 'pubgmgl120u-s13': (120, 198),
    'pubgmgl325u-s7': (325, 499), 'pubgmgl660u-s7': (660, 899),
    'pubgmgl1800u-s7': (1800, 2499), 'pubgmgl3850u-s7': (3850, 4999),
    'pubgmgl8100uco-s11': (8100, 9999), 'pubgmgl16200uco-s11': (16200, 18999),
    'pubgmgl24300uco-s11': (24300, 28999), 'pubgmgl32400uco-s11': (32400, 37999),
    'pubgmgl40500uco-s11': (40500, 46999),
    'pubgmel5ucbp-s101': (1, 549), 'pubgmel1ucbp-s101': (1, 1079),
    'pubgmepl1ucbp-s10': (1, 2699),
    'pubgm60wc-s101': (60, 99), 'pubgm325wc-s101': (325, 499),
    'pubgm660wc-s101': (660, 999), 'pubgm1800wc-s101': (1800, 2499),
    'pubgm3850wc-s101': (3850, 4999), 'pubgm8100wc-s101': (8100, 9999),
    'pubgmucfpp-s101': (1, 89), 'pubgmucmep-s101': (1, 445), 'pubgmucufmp-s101': (1, 269), 'pubgmucwmevp-s101': (1, 269), 'pubgm1ucwdp-s101': (1, 89), 'pubgm2ucwdp-s101': (1, 269),
    'pubgmmucp-s101': (1, 89),
    'pubgmmucpb-s101': (1, 269),
    'pubgmmucpc-s101': (1, 539),
    'pubgmmucpa-s101': (1, 1079),
    'pubgmmucpp-s101': (1, 899),
    'pubgmmucppb-s101': (1, 2699),
    'pubgmmucppc-s101': (1, 5399),
    'pubgmmucppa-s101': (1, 10799),

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

import json
import unittest

import melostore_catalog as catalog


class MelostoreCatalog(unittest.TestCase):
    def test_complete_snapshot_has_unique_urls_and_all_categories(self):
        data = catalog.snapshot()
        items = data['items']
        self.assertGreater(len(items), 700)
        self.assertEqual(len({item['slug'] for item in items}), len(items))
        self.assertEqual({item['category'] for item in items}, set(catalog.CATEGORIES))
        self.assertEqual(sum(len(item['packages']) for item in items), data['product_count'])
        self.assertGreater(data['product_count'], 19000)
        skus = [pack['sku'] for item in items for pack in item['packages']]
        self.assertEqual(len(skus), len(set(skus)))

    def test_existing_prices_reviews_packages_and_extra_admin_brands_are_preserved(self):
        existing = [{'slug': 'pubg-mobile', 'name': 'PUBG Mobile', 'currency': 'UC',
                     'packages': [{'id': 'local-package', 'price_minor': 125000}],
                     'review_summary': {'count': 11, 'rating': 5}},
                    {'slug': 'admin-brand', 'name': 'Admin brand', 'packages': []}]
        result = catalog.public_catalog(existing)
        pubg = next(item for item in result if item['slug'] == 'pubg-mobile')
        self.assertEqual(pubg['packages'], existing[0]['packages'])
        self.assertEqual(pubg['review_summary'], existing[0]['review_summary'])
        self.assertGreater(pubg['supplier_package_count'], 0)
        self.assertEqual(result[-1]['slug'], 'admin-brand')
        pubg['packages'].clear()
        self.assertEqual(len(existing[0]['packages']), 1)

    def test_imported_brand_detail_is_read_only_and_omits_costs(self):
        brand = catalog.brand_detail('pubg-mobile')
        self.assertFalse(brand['purchasable'])
        self.assertGreater(len(brand['packages']), 0)
        for pack in brand['packages']:
            self.assertEqual(set(pack), {'sku', 'name', 'status', 'type_name', 'server_name'})
        serialized = json.dumps(catalog.public_catalog([]))
        self.assertNotIn('H2H_API_KEY', serialized)
        self.assertNotIn('X-Secret-Key', serialized)
        self.assertIsNone(catalog.brand_detail('not-a-real-brand'))

    def test_duplicate_named_regional_brands_keep_independent_urls(self):
        brands = [item for item in catalog.snapshot()['items'] if item['name'] == 'BLEACH Mobile 3D']
        self.assertEqual(len(brands), 2)
        self.assertNotEqual(brands[0]['slug'], brands[1]['slug'])


if __name__ == '__main__':
    unittest.main()

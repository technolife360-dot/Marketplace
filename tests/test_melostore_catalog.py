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
        self.assertGreater(data['product_count'], 10000)
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
            self.assertEqual(set(pack) - {'image_url'}, {'sku', 'name', 'status', 'type_name', 'server_name'})
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


class PubgCurrencyArtworkTests(unittest.TestCase):
    def test_uc_images_are_exposed_by_the_catalog_api_in_package_order(self):
        brand = catalog.brand_detail('pubg-mobile')
        totals = [60,120,325,660,1800,3850,8100,16200,24300,32400,40500]
        images = []
        for total in totals:
            pack=next(p for p in brand['packages'] if p['type_name']=='Unknown Cash' and p['name']==str(total)+' Unknown Cash')
            self.assertEqual(pack['image_url'],catalog.PUBG_UC_IMAGES[total])
            self.assertTrue(pack['image_url'].startswith('https://images.gamestorehub.com/site-assets/topup/pubg-mobile/uc-'))
            images.append(pack['image_url'])
        self.assertEqual(images[0],images[1])
        self.assertEqual(len(set(images)),10)
        raw = next(row for row in catalog.snapshot()['items'] if row['slug']=='pubg-mobile')
        self.assertFalse(any('image_url' in p for p in raw['packages']))


class CheapestSupplierTests(unittest.TestCase):
    def test_lowest_active_cost_wins_and_bonus_conditions_stay_separate(self):
        rows = [
            {'sku_code':'expensive','name':'86 Diamonds','type_name':'Diamonds','status':'active','price':200},
            {'sku_code':'cheap','name':'86 Diamonds','type_name':'Diamonds','status':'active','price':100},
            {'sku_code':'unavailable','name':'86 Diamonds','type_name':'Diamonds','status':'out_of_stock','price':1},
            {'sku_code':'unknown','name':'86 Diamonds','type_name':'Diamonds','status':'active','price':None},
            {'sku_code':'bonus','name':'86 Diamonds (First Top-Up Bonus)','type_name':'Diamonds','status':'active','price':50},
            {'sku_code':'bad','name':'172 Diamonds','type_name':'Diamonds','status':'active','price':'NaN'},
        ]
        self.assertEqual([row['sku_code'] for row in catalog.cheapest_active(rows)], ['cheap','bonus'])
        self.assertEqual(rows[0]['sku_code'],'expensive')

    def test_all_game_selections_are_available_unique_and_costs_are_private(self):
        data=catalog.snapshot()
        for slug, skus in data['selected_skus'].items():
            brand=catalog.brand_detail(slug)
            self.assertEqual({row['sku'] for row in brand['packages']},set(skus))
            self.assertTrue(all(row['status']=='active' for row in brand['packages']))
            self.assertEqual(len(brand['packages']),len({catalog.product_identity(row) for row in brand['packages']}))
            for row in brand['packages']:
                self.assertNotIn('price',row)
                self.assertNotIn('supplier_cost_idr',row)
        self.assertNotIn('pubg-mobile',data['selected_skus'])

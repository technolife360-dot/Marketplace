import json
import unittest
from pathlib import Path
from unittest.mock import patch
import melostore_catalog as catalog

class HomeTopups(unittest.TestCase):
    def test_featured_cards_use_existing_catalog_routes_and_only_public_fields(self):
        rows = catalog.home_topups()
        self.assertEqual([r['name'] for r in rows], ['PUBG Mobile','Mobile Legends','Free Fire','Genshin Impact','VALORANT','Steam'])
        brands = {r['slug']: r for r in catalog.snapshot()['items']}
        for row in rows:
            self.assertEqual(set(row), {'slug','name','subtitle','image_url','image_width','image_height'})
            self.assertTrue(brands[row['slug']]['packages'])
            self.assertTrue(row['image_url'].startswith('https://images.gamestorehub.com/site-assets/home-topups/'))
            self.assertGreater(row['image_width'],0)
        self.assertIn('MYR',rows[-1]['subtitle'])
        self.assertLess(len(json.dumps(rows)),4000)

    def test_retired_catalog_routes_are_not_featured(self):
        with patch.object(catalog, 'snapshot', return_value={'items':[]}):
            self.assertEqual(catalog.home_topups(), [])

    def test_home_retains_original_sections_in_order(self):
        source = Path('static/app.js').read_text()
        selectors = ['${homeGameCarouselMarkup()}', '<section class="home-topups"', '<section class="home-catalog"', '<section data-home-reviews>', '<section class="home-guide"']
        positions = [source.index(s) for s in selectors]
        self.assertEqual(positions, sorted(positions))
        self.assertIn('<div class="product-grid home-listing-grid">${items.slice(0,8).map(marketCard)', source)

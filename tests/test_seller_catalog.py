"""Catalogue relations must work on a clean database, not only in the picker."""
import collections
import sqlite3
import unittest

import app
import seller_catalog


class SellerCatalogTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('CREATE TABLE games(id TEXT PRIMARY KEY,slug TEXT UNIQUE,name TEXT,active INTEGER); CREATE TABLE categories(id TEXT PRIMARY KEY,slug TEXT);')
        self.db.executemany('INSERT INTO categories VALUES(?,?)', [(key,key) for key in seller_catalog.CATEGORIES])

    def tearDown(self):
        self.db.close()

    def test_snapshot_has_real_source_relations_and_no_alias_collisions(self):
        games = seller_catalog.catalogue()['games']
        self.assertGreaterEqual(len(games), 600)
        self.assertLessEqual(len(games), 700)
        aliases = collections.defaultdict(set)
        for game in games:
            self.assertTrue(2 <= len(game['name']) <= 80)
            self.assertRegex(game['id'], r'^[a-z0-9-]{2,100}$')
            self.assertTrue(game['categories'])
            self.assertLessEqual(set(game['categories']), seller_catalog.CATEGORIES)
            for value in [game['id'],game['name'],*game.get('aliases',[])]:
                aliases[seller_catalog.normalize(value)].add(game['id'])
            for evidence in game['categories'].values():
                self.assertTrue(evidence)
                for source in evidence:
                    self.assertIn(source['provider'], ('g2g','eldorado','unipin'))
                    self.assertTrue(source['url'].startswith('https://'))
        self.assertTrue(all(len(ids) == 1 for ids in aliases.values()))

    def test_gift_card_brand_cannot_be_submitted_as_an_account_even_by_id(self):
        for name in ['Apple', 'apple']:
            with self.assertRaises(app.HttpError):
                seller_catalog.validate_selection(self.db,name,'accounts',app.HttpError)
            seller_catalog.validate_selection(self.db,name,'codes',app.HttpError)
        self.db.execute("INSERT INTO games VALUES('old-apple','apple','Apple',1)")
        with self.assertRaises(app.HttpError):
            seller_catalog.validate_selection(self.db,'old-apple','accounts',app.HttpError)

    def test_selecting_new_game_persists_only_that_game_with_canonical_identity(self):
        game = next(game for game in seller_catalog.public_games() if game['id']=='old-school-runescape')
        self.assertEqual(app.resolve_game_id(self.db,'OSRS'),game['id'])
        self.assertEqual(app.resolve_game_id(self.db,game['name']),game['id'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM games').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT active FROM games').fetchone()[0],1)

    def test_existing_game_identity_is_preserved_and_custom_game_stays_private(self):
        self.db.execute("INSERT INTO games VALUES('legacy-pubg','pubg-mobile','PUBG Mobile',1)")
        self.assertEqual(app.resolve_game_id(self.db,'PUBG Mobile'),'legacy-pubg')
        custom = app.resolve_game_id(self.db,'A new game requested by a seller')
        self.assertEqual(self.db.execute('SELECT active FROM games WHERE id=?',(custom,)).fetchone()[0],0)

    def test_public_picker_does_not_expose_source_inventory_or_claim_authorization(self):
        games = seller_catalog.public_games()
        self.assertIn('accounts',seller_catalog.find('PUBG Mobile')['categories'])
        self.assertEqual(set(games[0]), {'id','slug','name','aliases','supported_categories','image_url'})
        self.assertEqual(seller_catalog.catalogue()['authorization'],'competitor_taxonomy_only_not_publisher_permission')

    def test_every_catalogue_image_has_a_small_versioned_public_thumbnail(self):
        images=seller_catalog.artwork()
        games=seller_catalog.public_games()
        self.assertEqual(set(images),{game['id'] for game in games})
        for game in games:
            art=images[game['id']]
            self.assertTrue(game['image_url'])
            self.assertEqual((art['width'],art['height']),(96,96))
            self.assertLessEqual(art['size'],24*1024)
            self.assertGreater(art['size'],0)
            self.assertNotEqual(art['kind'],'needs_review')


if __name__ == '__main__':
    unittest.main()

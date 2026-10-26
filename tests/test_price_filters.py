import sqlite3
import unittest
from unittest.mock import patch
import app

class PriceFilterTests(unittest.TestCase):
    def matches(self,**filters):
        with sqlite3.connect(':memory:') as db:
            db.execute('CREATE TABLE listings(id TEXT,status TEXT,stock INTEGER,reserved INTEGER,price_minor INTEGER,currency TEXT,delivery_minutes INTEGER)')
            db.executemany("INSERT INTO listings VALUES(?,'published',1,0,?,?,?)",[('myr-low',12990,'MYR',15),('myr-high',22900,'MYR',60),('uzs',12990,'UZS',30)])
            with patch.object(app,'MODE','development'):
                where,args=app.catalogue_predicates(db,{key:[value] for key,value in filters.items()})
            return [row[0] for row in db.execute('SELECT l.id FROM listings l WHERE '+' AND '.join(where),args)]

    def test_ringgit_bounds_use_cents_and_do_not_match_other_currencies(self):
        self.assertEqual(self.matches(currency='MYR',min_major='100',max_major='200'),['myr-low'])
        self.assertEqual(self.matches(currency='MYR',min_major='129.90',max_major='129.90'),['myr-low'])
        self.assertEqual(self.matches(currency='MYR',max_major='100'),[])

    def test_existing_raw_price_links_keep_their_meaning(self):
        self.assertEqual(self.matches(min='12000',max='14000'),['myr-low','uzs'])
        self.assertEqual(self.matches(currency='UZS',min_major='12000',max_major='14000'),['uzs'])

    def test_fifteen_minute_delivery_filter_uses_the_same_limit_as_the_menu(self):
        self.assertEqual(self.matches(currency='MYR',delivery='15'),['myr-low'])
        self.assertEqual(self.matches(currency='MYR',delivery='5'),[])

    def test_invalid_or_ambiguous_price_ranges_are_rejected(self):
        for filters in [dict(min_major='100'),dict(currency='BAD',min_major='100'),dict(currency='MYR',min_major='-1'),dict(currency='MYR',min_major='NaN'),dict(currency='MYR',min_major='1.001'),dict(currency='MYR',min_major='200',max_major='100'),dict(currency='MYR',min='1',min_major='100'),dict(currency='MYR',max_major='9999999999999')]:
            with self.subTest(filters=filters),self.assertRaises(app.HttpError):self.matches(**filters)

if __name__=='__main__':unittest.main()

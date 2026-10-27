import json
import unittest
from unittest.mock import patch

import app
import order_history
from tests import test_operations as fixtures


class OrderHistory(unittest.TestCase):
    setUp = fixtures.OperationsFlows.setUp
    tearDown = fixtures.OperationsFlows.tearDown
    route = fixtures.OperationsFlows.route
    ctx = fixtures.OperationsFlows.ctx

    def seed_orders(self, count=65):
        for i in range(count):
            oid = 'history_'+str(i).zfill(4)
            self.db.execute("INSERT INTO orders(id,reference,buyer_id,currency,subtotal_minor,commission_minor,total_minor,status,payment_mode,created_at) VALUES(?,?,?,'MYR',100,5,105,?,'stripe_test','2026-10-27 12:00:00')", (oid, 'BG-HISTORY-'+str(i), self.buyer, 'completed' if i%2 else 'paid'))
            snapshot = json.dumps({'image_url':'/static/assets/topup-pubg-mobile.svg','game_name':'PUBG Mobile','private_credentials':'NEVER_IN_LIST','buyer_fields':[{'key':'private'}]})
            self.db.execute("INSERT INTO order_items(id,order_id,listing_id,seller_id,title,quantity,unit_price_minor,commission_minor,delivery_method,snapshot_json) VALUES(?,?,?,?,?,1,100,5,'manual',?)",('item_'+oid,oid,self.listing,self.seller,'Product '+str(i),snapshot))

    def test_history_is_bounded_and_does_not_load_private_order_detail(self):
        self.seed_orders(65)
        with patch.object(app,'order_view',side_effect=AssertionError('history must not decrypt delivery')):
            result=self.route(self.buyer,'GET','/api/orders?paged=1&role=purchases&limit=20')
            legacy=self.route(self.buyer,'GET','/api/orders')
        self.assertEqual(len(result['items']),20)
        self.assertEqual(len(legacy),20)
        self.assertTrue(result['has_more'])
        self.assertNotIn('NEVER_IN_LIST',json.dumps(result))
        self.assertNotIn('buyer_fields',json.dumps(result))
        with patch.object(app,'order_view',side_effect=AssertionError('history must not load private details')):
            statements=[]
            self.db.set_trace_callback(statements.append)
            try:order_history.page(self.db,self.buyer,{'paged':['1']},vars(app))
            finally:self.db.set_trace_callback(None)
        self.assertEqual(len([sql for sql in statements if sql.lstrip().upper().startswith(('SELECT','WITH'))]),2)

    def test_keyset_paging_with_identical_dates_has_no_duplicates_or_missing_orders(self):
        self.seed_orders(65)
        query='/api/orders?paged=1&role=purchases&limit=20'
        seen=[];cursor=None
        while True:
            result=self.route(self.buyer,'GET',query+('&cursor='+cursor if cursor else ''))
            seen.extend(o['id'] for o in result['items'])
            self.assertLessEqual(len(result['items']),20)
            if not result['has_more']:break
            cursor=result['next_cursor']
        self.assertEqual(len(seen),65);self.assertEqual(len(set(seen)),65)
        self.assertEqual(seen,sorted(seen,reverse=True))

    def test_filters_and_cursor_remain_scoped_to_the_user(self):
        self.seed_orders()
        buyer=self.route(self.buyer,'GET','/api/orders?paged=1&role=purchases&status=completed&limit=5')
        self.assertTrue(all(o['status']=='completed' for o in buyer['items']))
        self.assertEqual(self.route(self.other,'GET','/api/orders?paged=1')['items'],[])
        sales=self.route(self.seller,'GET','/api/orders?paged=1&role=sales&limit=5')
        self.assertTrue(all(o['buyer_id'] is None and o['total_minor']==100 for o in sales['items']))
        for query in ['role=purchases&status=active','role=purchases&status=completed&q=changed']:
            with self.assertRaises(app.HttpError):self.route(self.buyer,'GET','/api/orders?paged=1&'+query+'&cursor='+buyer['next_cursor'])
        for query in ['limit=0','limit=1000000','role=anyone','status=invalid','cursor=not-json','q='+('x'*101)]:
            with self.assertRaises(app.HttpError):self.route(self.buyer,'GET','/api/orders?paged=1&'+query)

    def test_literal_search_and_summary_preview_limit(self):
        self.seed_orders(1)
        self.db.execute("UPDATE order_items SET title='Literal 100%_item' WHERE order_id='history_0000'")
        from urllib.parse import urlencode
        match=self.route(self.buyer,'GET','/api/orders?'+urlencode({'paged':1,'q':'100%_'}))
        self.assertEqual(len(match['items']),1)
        no_match=self.route(self.buyer,'GET','/api/orders?'+urlencode({'paged':1,'q':'%NOT'}))
        self.assertEqual(no_match['items'],[])
        for i in range(3):
            self.db.execute("INSERT INTO order_items(id,order_id,listing_id,seller_id,title,quantity,unit_price_minor,commission_minor,delivery_method) VALUES(?,'history_0000',?,?,'Extra',1,100,5,'manual')",('extra_'+str(i),self.listing,self.seller))
        result=self.route(self.buyer,'GET','/api/orders?paged=1')['items'][0]
        self.assertEqual(result['item_count'],4)
        self.assertEqual(len(result['items']),2)

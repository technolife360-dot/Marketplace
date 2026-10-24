import unittest
from urllib.parse import parse_qs
from tests import test_marketplace as fixtures
import app
import purchase_reviews as reviews

class PurchaseReviewFlows(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    def route(self,uid,method,url,data=None):
        path,_,query=url.partition('?')
        result=self.handler.route(self.db,self.ctx(uid),method,path,parse_qs(query),data or {})
        return result[1] if isinstance(result,tuple) else result
    def market_order(self,status='completed',mode='stripe'):
        oid=app.ident();iid=app.ident()
        self.db.execute("INSERT INTO orders(id,reference,buyer_id,currency,subtotal_minor,commission_minor,commission_bps,total_minor,status,payment_mode) VALUES(?,?,?,'UZS',100,0,0,100,?,?)",(oid,oid,self.buyer,status,mode))
        self.db.execute("INSERT INTO order_items(id,order_id,listing_id,seller_id,title,quantity,unit_price_minor,commission_minor,delivery_method) VALUES(?,?,?,?,'Test purchase',1,100,0,'manual')",(iid,oid,self.listing,self.seller))
        return oid,iid
    def topup_order(self,status='completed',paid=True):
        package=self.db.execute("SELECT id FROM topup_packages WHERE game_slug='pubg-mobile' LIMIT 1").fetchone()['id']
        oid=app.ident()
        self.db.execute("INSERT INTO topup_orders(id,reference,buyer_id,package_id,player_id,quantity,unit_price_minor,status,payment_reference,completed_at) VALUES(?,?,?,?,'123456789',1,100,?,?,?)",(oid,oid,self.buyer,package,status,'verified-reference' if paid else '',app.now_iso() if status=='completed' else None))
        return oid
    def test_topup_only_owner_of_paid_completed_purchase_can_review_once(self):
        oid=self.topup_order()
        for uid in (self.other,self.seller,None):
            with self.assertRaises(app.HttpError):self.route(uid,'POST','/api/top-up/reviews',{'order_id':oid,'rating':5,'body':'Delivered as described.'})
        for oid2 in (self.topup_order('awaiting_payment'),self.topup_order('completed',False)):
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/top-up/reviews',{'order_id':oid2,'rating':5,'body':'Delivered as described.'})
        r=self.route(self.buyer,'POST','/api/top-up/reviews',{'order_id':oid,'rating':5,'body':'Delivered as described.'})
        with self.assertRaises(app.HttpError) as duplicate:self.route(self.buyer,'POST','/api/top-up/reviews',{'order_id':oid,'rating':4,'body':'Another review for same order.'})
        self.assertEqual(duplicate.exception.status,409)
        public=self.route(None,'GET','/api/review-hub/topup/pubg-mobile')
        self.assertEqual((public['count'],public['rating']),(1,5.0));self.assertTrue(public['items'][0]['verified_purchase'])
        self.assertNotIn('player_id',public['items'][0]);self.assertNotIn('order_id',public['items'][0])
        with self.assertRaises(app.HttpError):self.route(self.other,'PATCH','/api/top-up/reviews/'+r['id'],{'rating':1,'body':'Not my own purchase.'})
        self.route(self.buyer,'PATCH','/api/top-up/reviews/'+r['id'],{'rating':4,'body':'Updated review from the buyer.'})
        self.assertEqual(self.route(None,'GET','/api/review-hub/topup/pubg-mobile')['rating'],4.0)
    def test_rating_and_body_validation(self):
        oid=self.topup_order()
        for rating in (True,0,6,'5',2.5):
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/top-up/reviews',{'order_id':oid,'rating':rating,'body':'Valid review text.'})
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/top-up/reviews',{'order_id':oid,'rating':5,'body':'Hi'})
    def test_marketplace_edit_duplicate_and_product_scores_exclude_sandbox(self):
        oid,iid=self.market_order();r=self.route(self.buyer,'POST','/api/reviews',{'item_id':iid,'rating':4,'body':'Matches the description.'})
        with self.assertRaises(app.HttpError):self.route(self.other,'PATCH','/api/reviews/'+r['id'],{'rating':1,'body':'Unauthorized edit.'})
        self.route(self.buyer,'PATCH','/api/reviews/'+r['id'],{'rating':5,'body':'Updated after checking the delivery.'})
        with self.assertRaises(app.HttpError) as duplicate:self.route(self.buyer,'POST','/api/reviews',{'item_id':iid,'rating':3,'body':'Duplicate purchase review.'})
        self.assertEqual(duplicate.exception.status,409)
        _,sandbox=self.market_order(mode='sandbox');self.route(self.buyer,'POST','/api/reviews',{'item_id':sandbox,'rating':1,'body':'Sandbox review must not count.'})
        items=[{'id':self.listing}];reviews.add_listing_scores(self.db,items)
        self.assertEqual((items[0]['product_rating'],items[0]['product_review_count']),(5.0,1))
        r=self.route(None,'GET','/api/review-hub/listing/'+self.listing)
        self.assertEqual(r['count'],1)

    def test_card_seller_stats_count_real_completed_units_across_offers_without_review_multiplication(self):
        _,first=self.market_order()
        self.db.execute('UPDATE order_items SET quantity=3 WHERE id=?',(first,))
        self.route(self.buyer,'POST','/api/reviews',{'item_id':first,'rating':5,'body':'A real completed purchase.'})
        second_listing=app.ident()
        self.db.execute("""INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,stock,status)
            VALUES(?,?,'valorant','accounts','Another offer','Another account from this seller.','account',100,1,'published')""",(second_listing,self.seller))
        _,second=self.market_order()
        self.db.execute('UPDATE order_items SET listing_id=? WHERE id=?',(second_listing,second))
        self.route(self.buyer,'POST','/api/reviews',{'item_id':second,'rating':3,'body':'Another verified purchase.'})
        for status,mode in [('cancelled','stripe'),('paid','stripe'),('completed','sandbox'),('completed','disabled'),('completed','stripe_test')]:
            _,excluded=self.market_order(status,mode)
            self.db.execute('UPDATE order_items SET quantity=100 WHERE id=?',(excluded,))
        _,hidden=self.market_order()
        review=self.route(self.buyer,'POST','/api/reviews',{'item_id':hidden,'rating':1,'body':'This review will be hidden.'})
        self.db.execute('UPDATE reviews SET hidden=1 WHERE id=?',(review['id'],))
        items=[{'id':self.listing,'seller_id':self.seller,'product_type':'account'},
               {'id':second_listing,'seller_id':self.seller,'product_type':'account'},
               {'id':'different-type','seller_id':self.seller,'product_type':'item'},
               {'id':'different-seller','seller_id':self.other,'product_type':'account'}]
        reviews.add_listing_scores(self.db,items)
        for item in items[:2]:
            self.assertEqual((item['seller_card_rating'],item['seller_card_review_count'],item['seller_sales_count']),(4.0,2,5))
        self.assertEqual(items[2]['seller_sales_count'],0)
        self.assertEqual((items[3]['seller_card_rating'],items[3]['seller_card_review_count'],items[3]['seller_sales_count']),(None,0,0))
        detail=self.route(None,'GET','/api/listings/'+self.listing)
        self.assertEqual((detail['seller_card_rating'],detail['seller_sales_count']),(4.0,5))
        related=next(item for item in detail['related'] if item['id']==second_listing)
        self.assertEqual((related['seller_card_rating'],related['seller_sales_count']),(4.0,5))
        catalogue=self.route(None,'GET','/api/listings')['items']
        self.assertEqual(next(item for item in catalogue if item['id']==self.listing)['seller_sales_count'],5)
    def test_reports_seller_reply_and_moderation_preserve_one_review_per_purchase(self):
        _,iid=self.market_order();r=self.route(self.buyer,'POST','/api/reviews',{'item_id':iid,'rating':3,'body':'The buyer describes the delivery.'})
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/reviews/'+r['id']+'/reply',{'body':'Not the seller.'})
        self.route(self.seller,'POST','/api/reviews/'+r['id']+'/reply',{'body':'Thank you for the feedback.'})
        self.route(self.other,'POST','/api/reviews/'+r['id']+'/report',{'reason':'Contains personal information.'})
        self.route(self.other,'POST','/api/reviews/'+r['id']+'/report',{'reason':'Contains personal information.'})
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/admin/review-reports')
        reports=self.route(self.admin,'GET','/api/admin/review-reports');self.assertEqual(len(reports),1)
        self.route(self.admin,'POST','/api/admin/review-reports/'+reports[0]['id'],{'action':'remove','note':'Personal information removed from public view.'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM visible_reviews').fetchone()['n'],0)
        with self.assertRaises(app.HttpError):self.route(self.buyer,'PATCH','/api/reviews/'+r['id'],{'rating':5,'body':'Cannot republish a moderated review.'})
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/reviews',{'item_id':iid,'rating':5,'body':'Cannot create a replacement review.'})
    def test_topup_reply_admin_only_and_mine_contains_completed_purchases(self):
        oid=self.topup_order();r=self.route(self.buyer,'POST','/api/top-up/reviews',{'order_id':oid,'rating':5,'body':'A completed topup purchase.'})
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/top-up/reviews/'+r['id']+'/reply',{'body':'Not a platform admin.'})
        self.route(self.admin,'POST','/api/top-up/reviews/'+r['id']+'/reply',{'body':'Thank you for your purchase.'})
        self.assertEqual(self.route(None,'GET','/api/review-hub/topup/pubg-mobile')['items'][0]['reply'],'Thank you for your purchase.')
        mine=self.route(self.buyer,'GET','/api/review-hub/mine');self.assertEqual(mine[0]['review_id'],r['id'])
        self.assertEqual(self.route(self.other,'GET','/api/review-hub/mine'),[])
        self.assertEqual(reviews.topup_scores(self.db)['pubg-mobile']['count'],1)

    def test_public_pagination_and_catalog_scores_follow_visible_completed_reviews(self):
        for index in range(11):
            oid=self.topup_order();self.route(self.buyer,'POST','/api/top-up/reviews',{'order_id':oid,'rating':5,'body':'Completed purchase feedback number '+str(index)})
        first=self.route(None,'GET','/api/review-hub/topup/pubg-mobile')
        second=self.route(None,'GET','/api/review-hub/topup/pubg-mobile?page=2')
        self.assertEqual((len(first['items']),len(second['items'])),(10,1))
        self.assertTrue(first['has_more']);self.assertFalse(second['has_more'])
        self.assertFalse({r['id'] for r in first['items']} & {r['id'] for r in second['items']})
        catalogue=self.route(None,'GET','/api/top-up/catalog')
        self.assertEqual(next(g for g in catalogue if g['slug']=='pubg-mobile')['review_summary']['count'],11)
        self.db.execute('UPDATE topup_reviews SET hidden=1')
        self.assertEqual(self.route(None,'GET','/api/review-hub/topup/pubg-mobile')['count'],0)
        self.assertNotIn('pubg-mobile',reviews.topup_scores(self.db))

    def test_postgres_review_tables_and_view_are_private(self):
        statements=[]
        class FakeDatabase:
            def execute(self,sql,*args):statements.append(sql)
        reviews.migrate(FakeDatabase(),True)
        for table in reviews.TABLES:
            self.assertIn('ALTER TABLE public.'+table+' ENABLE ROW LEVEL SECURITY',statements)
            self.assertIn('REVOKE ALL ON public.'+table+' FROM PUBLIC, anon, authenticated',statements)
        self.assertTrue(any('visible_reviews WITH (security_invoker=true)' in sql for sql in statements))
        self.assertIn('REVOKE ALL ON public.visible_reviews FROM PUBLIC, anon, authenticated',statements)

    def test_topup_scores_and_eligibility_exclude_sandbox_payment_references(self):
        for reference in ('sandbox','sandbox:old-payment','SANDBOX-test','verified-reference'):
            oid=self.topup_order()
            self.db.execute('UPDATE topup_orders SET payment_reference=? WHERE id=?',(reference,oid))
            self.db.execute('INSERT INTO topup_reviews(id,order_id,reviewer_id,rating,body) VALUES(?,?,?,5,?)',
                            (app.ident(),oid,self.buyer,'Existing purchase review.'))
        catalogue=self.route(None,'GET','/api/top-up/catalog')
        summary=next(game for game in catalogue if game['slug']=='pubg-mobile')['review_summary']
        self.assertEqual(summary,{'count':1,'rating':5.0})
        public=self.route(self.buyer,'GET','/api/review-hub/topup/pubg-mobile')
        self.assertEqual(public['count'],1)
        self.assertEqual(len(public['eligible']),1)
        self.assertEqual(len(self.route(self.buyer,'GET','/api/review-hub/mine')),1)

    def test_languages_masked_names_packages_and_helpful_votes(self):
        oid=self.topup_order();r=self.route(self.buyer,'POST','/api/top-up/reviews',{'order_id':oid,'rating':5,'body':'Fast delivery and useful service.','language':'en'})
        public=self.route(None,'GET','/api/review-hub/topup/pubg-mobile')['items'][0]
        self.assertIn('***',public['reviewer_name']);self.assertEqual(public['language'],'en');self.assertTrue(public['package_name'])
        self.assertEqual(self.route(None,'GET','/api/review-hub/topup/pubg-mobile?language=uz')['filtered_count'],0)
        self.assertEqual(self.route(None,'GET','/api/review-hub/topup/pubg-mobile?language=en')['filtered_count'],1)
        path='/api/top-up/reviews/'+r['id']+'/helpful'
        with self.assertRaises(app.HttpError):self.route(None,'POST',path)
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST',path)
        self.assertEqual(self.route(self.other,'POST',path)['count'],1)
        self.assertEqual(self.route(self.other,'POST',path)['count'],1)
        self.assertEqual(self.route(self.other,'DELETE',path)['count'],0)
        with self.assertRaises(app.HttpError):self.route(self.buyer,'PATCH','/api/top-up/reviews/'+r['id'],{'rating':4,'body':'Edited review in an invalid language.','language':'xx'})

if __name__=='__main__':unittest.main()

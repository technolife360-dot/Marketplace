"""Exercise the new workflows against an isolated SQLite database."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs
import app
import marketplace_features
from tests import test_marketplace as fixtures

class MarketplaceUsability(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    def route(self,uid,method,url,data=None,raw=b''):
        path,_,query=url.partition('?')
        result=self.handler.route(self.db,self.ctx(uid),method,path,parse_qs(query),data or {},raw)
        return result[1] if isinstance(result,tuple) else result
    def item(self,**changes):
        payload={'game_name':'Counter-Strike 2','category_id':'items','title':'Karambit Doppler test skin','description':'A clear description of this test item and its condition.', 'price_minor':42000,'stock':4,'delivery_eta':'5 minutes','platform':'PC','region':'Asia','submit_for_review':True,'attributes':{'item_type':'Knife','condition':'Factory New','float_value':'0.03','item_variant':'Doppler'}}
        payload.update(changes)
        result=self.route(self.seller,'POST','/api/listings',payload)
        self.route(self.admin,'POST','/api/admin/listings/'+result['id'],{'action':'approve'})
        return result['id']
    def test_filters_sort_aliases_and_store_keep_private_data_private(self):
        lid=self.item();self.db.execute('UPDATE users SET last_seen_at=? WHERE id=?',(app.now_iso(),self.seller))
        url='/api/listings?game=counter-strike-2&platform=PC&region=Asia&delivery=5&online=1&verified=1&item_type=knife&condition=Factory&item_variant=Doppler&min=40000&max=43000&sort=recommended'
        results=self.route(None,'GET',url)
        self.assertEqual([i['id'] for i in results['items']],[lid])
        self.assertEqual(self.route(None,'GET','/api/listings?q=CSGO')['items'][0]['id'],lid)
        self.assertEqual(self.route(None,'GET','/api/listings?delivery=60&sort=delivery')['items'][0]['id'],lid)
        self.assertEqual(self.route(None,'GET','/api/listings?max=100')['items'],[])
        self.assertEqual([i['id'] for i in self.route(None,'GET','/api/listings?float_min=0.02&float_max=0.04')['items']],[lid])
        self.assertEqual(self.route(None,'GET','/api/listings?float_min=0.5')['items'],[])
        store=self.route(None,'GET','/api/stores/'+self.seller)
        self.assertTrue(store['identity_verified']);self.assertEqual(store['completed_sales'],0);self.assertIsNone(store['avg_reply_seconds'])
        self.assertNotIn('email',json.dumps(store));self.assertNotIn('password',json.dumps(store))
        self.assertEqual(self.route(None,'GET','/api/listings?seller='+self.other)['items'],[])
        with self.assertRaises(app.HttpError):self.route(None,'GET','/api/listings?delivery=100')
    def test_suggestions_understand_aliases_typo_and_hide_unpublished_items(self):
        lid=self.item()
        self.assertEqual(self.route(None,'GET','/api/search/suggestions?q=CSGO')['games'][0]['slug'],'counter-strike-2')
        self.assertEqual(self.route(None,'GET','/api/search/suggestions?q=Valoran')['games'][0]['slug'],'valorant')
        self.assertEqual(self.route(None,'GET','/api/search/suggestions?q=Karambit')['items'][0]['id'],lid)
        self.db.execute("UPDATE listings SET status='paused' WHERE id=?",(lid,))
        self.assertEqual(self.route(None,'GET','/api/search/suggestions?q=Karambit')['items'],[])
        with patch.object(app,'MODE','production'),patch.dict(app.os.environ,{'MARKETPLACE_INTERNAL_TESTING_ENABLED':'false','MARKETPLACE_SALES_ENABLED':'false'}):
            self.db.execute("UPDATE listings SET status='published' WHERE id=?",(lid,))
            self.assertEqual(self.route(None,'GET','/api/search/suggestions?q=Karambit')['items'],[])
    def test_following_and_favorite_alerts_only_after_approved_publication(self):
        self.route(self.buyer,'POST','/api/stores/'+self.seller+'/follow')
        self.assertEqual(len(self.route(self.buyer,'GET','/api/following')),1)
        lid=self.item()
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND kind='seller_listing'",(self.buyer,)).fetchone()['n'],1)
        self.route(self.buyer,'POST','/api/favorites/'+lid)
        self.route(self.seller,'PATCH','/api/listings/'+lid,{'price_minor':40000})
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND kind='favorite'",(self.buyer,)).fetchone()['n'],0)
        self.route(self.admin,'POST','/api/admin/listings/'+lid,{'action':'approve'})
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND kind='favorite'",(self.buyer,)).fetchone()['n'],1)
        self.route(self.admin,'POST','/api/admin/listings/'+lid,{'action':'approve'})
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND kind='favorite'",(self.buyer,)).fetchone()['n'],1)
        self.route(self.buyer,'DELETE','/api/stores/'+self.seller+'/follow')
        self.assertEqual(self.route(self.buyer,'GET','/api/following'),[])
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/stores/'+self.seller+'/follow')
    def test_duplicate_and_bulk_pause_cannot_mutate_another_sellers_listing(self):
        lid=self.item();copy=self.route(self.seller,'POST','/api/listings/'+lid+'/duplicate')
        row=self.db.execute('SELECT * FROM listings WHERE id=?',(copy['id'],)).fetchone()
        self.assertEqual(row['status'],'draft');self.assertEqual(row['reserved'],0);self.assertEqual(row['delivery_minutes'],5)
        account_copy=self.route(self.seller,'POST','/api/listings/'+self.listing+'/duplicate')
        self.assertEqual(self.route(self.seller,'POST','/api/listings/'+account_copy['id']+'/submit')['status'],'pending_review')
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/listings/'+lid+'/duplicate')
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/listings/bulk-pause',{'ids':[lid,'unknown']})
        self.assertEqual(self.db.execute('SELECT status FROM listings WHERE id=?',(lid,)).fetchone()['status'],'published')
        self.assertEqual(self.route(self.seller,'POST','/api/seller/listings/bulk-pause',{'ids':[lid,self.listing]})['updated'],2)
    def order(self):
        oid=app.ident();iid=app.ident()
        self.db.execute("INSERT INTO orders(id,reference,buyer_id,status,subtotal_minor,commission_minor,total_minor,currency,payment_mode) VALUES(?,?,?,'completed',50000,0,50000,'UZS','sandbox')",(oid,'TEST-'+oid,self.buyer))
        self.db.execute("INSERT INTO order_items(id,order_id,listing_id,seller_id,title,quantity,unit_price_minor,commission_minor,delivery_method) VALUES(?,?,?,?,?,1,50000,0,'manual')",(iid,oid,self.listing,self.seller,'Test purchase'))
        return oid,iid
    def test_review_filters_pagination_and_authenticated_seller_replies(self):
        _,iid=self.order();review=self.route(self.buyer,'POST','/api/reviews',{'item_id':iid,'rating':5,'body':'Everything arrived as described.'})
        rid=self.db.execute('SELECT id FROM reviews WHERE order_item_id=?',(iid,)).fetchone()['id']
        self.route(self.seller,'POST','/api/reviews/'+rid+'/reply',{'body':'Thank you for the review!'})
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/reviews/'+rid+'/reply',{'body':'Pretending to be seller'})
        r=self.route(None,'GET','/api/stores/'+self.seller+'/reviews?sentiment=positive&game=valorant&sort=newest')
        self.assertEqual(r['total_count'],1);self.assertEqual(r['items'][0]['reply'],'Thank you for the review!');self.assertFalse(r['can_reply'])
        self.assertEqual(self.route(None,'GET','/api/stores/'+self.seller+'/reviews?sentiment=negative')['items'],[])
        self.assertEqual(self.route(None,'GET','/api/stores/'+self.seller+'/reviews?game=dota-2')['items'],[])
        self.assertEqual(self.route(None,'GET','/api/stores/'+self.seller)['completed_sales'],1)
    def test_order_conversation_is_idempotent_private_and_read_receipts_work(self):
        oid,_=self.order();data={'order_id':oid,'seller_id':self.seller}
        conv=self.route(self.buyer,'POST','/api/conversations',data)
        self.assertEqual(self.route(self.seller,'POST','/api/conversations',{'order_id':oid})['id'],conv['id'])
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/conversations',data)
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/conversations/'+conv['id'])
        msg=self.route(self.buyer,'POST','/api/conversations/'+conv['id']+'/messages',{'body':'Hello seller'})
        self.assertIsNone(self.db.execute('SELECT read_at FROM messages WHERE id=?',(msg['id'],)).fetchone()['read_at'])
        result=self.route(self.seller,'GET','/api/conversations/'+conv['id'])
        self.assertEqual(result['order']['id'],oid);self.assertIsNotNone(result['messages'][0]['read_at'])
    def test_chat_photos_are_decoded_private_and_only_signed_for_participants(self):
        from PIL import Image
        lid=self.item();cid=self.route(self.buyer,'POST','/api/conversations',{'listing_id':lid})['id']
        self.handler.headers={'Content-Type':'image/png'};buffer=io.BytesIO();Image.new('RGB',(12,12),'purple').save(buffer,format='PNG')
        with patch.object(app,'require_private_evidence_bucket'),patch.object(app.storage_r2,'put_evidence') as upload,patch.object(app.storage_r2,'evidence_url',return_value='https://private.invalid/signed-photo') as signed:
            with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/conversations/'+cid+'/photos',raw=buffer.getvalue())
            upload.assert_not_called()
            self.route(self.buyer,'POST','/api/conversations/'+cid+'/photos',raw=buffer.getvalue())
            self.assertEqual(upload.call_count,1);self.assertTrue(upload.call_args.args[1].startswith(b'RIFF'))
            result=self.route(self.seller,'GET','/api/conversations/'+cid)
            self.assertEqual(result['messages'][0]['image_url'],'https://private.invalid/signed-photo')
            self.assertNotIn('object_path',json.dumps(result));self.assertEqual(signed.call_count,1)
            with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/conversations/'+cid)
            self.assertEqual(signed.call_count,1)
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/conversations/'+cid+'/photos',raw=b'not an image')
    def test_review_history_pagination_and_back_in_stock_notification(self):
        lid=self.item(stock=1)
        self.route(self.buyer,'POST','/api/favorites/'+lid)
        self.db.execute("UPDATE listings SET status='sold_out',stock=0 WHERE id=?",(lid,))
        self.route(self.seller,'PATCH','/api/listings/'+lid,{'stock':3})
        self.route(self.admin,'POST','/api/admin/listings/'+lid,{'action':'approve'})
        notices=self.db.execute("SELECT body FROM notifications WHERE user_id=? AND kind='favorite'",(self.buyer,)).fetchall()
        self.assertEqual(len(notices),1);self.assertIn('yana mavjud',notices[0]['body'])
        for i in range(14):
            _,iid=self.order()
            self.route(self.buyer,'POST','/api/reviews',{'item_id':iid,'rating':5 if i<13 else 2,'body':'A complete local test review.'})
        first=self.route(None,'GET','/api/stores/'+self.seller+'/reviews')
        second=self.route(None,'GET','/api/stores/'+self.seller+'/reviews?page=2')
        self.assertEqual((first['total_count'],len(first['items']),len(second['items'])),(14,12,2))
        self.assertTrue(first['has_more']);self.assertFalse(second['has_more'])
        self.assertTrue(set(r['id'] for r in first['items']).isdisjoint(r['id'] for r in second['items']))
        self.assertEqual(self.route(None,'GET','/api/stores/'+self.seller+'/reviews?sentiment=negative')['total_count'],1)
        self.assertEqual(self.route(None,'GET','/api/stores/'+self.seller)['sales_history'][0]['quantity'],14)

    def test_item_attribute_validation_and_duration(self):
        for value in ('-0.2','1.01','NaN','Infinity','text'):
            with self.assertRaises(app.HttpError):self.item(attributes={'float_value':value})
        for value,expected in [('5 minutes',5),('1 hour',60),('24 soat',1440),('1 kun',1440),('Instant delivery',1),('ask seller',None)]:self.assertEqual(marketplace_features.delivery_minutes(value),expected)

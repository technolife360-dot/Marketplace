import json
import unittest
from datetime import datetime,timedelta,timezone
from urllib.parse import parse_qs
from unittest.mock import patch
import app
import trade_workflows as trade
import marketplace_operations as ops
from tests import test_marketplace as fixtures


class TradeWorkflows(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx

    def route(self,uid,method,url,data=None,raw=b''):
        path,_,query=url.partition('?');self.handler.headers={}
        r=self.handler.route(self.db,self.ctx(uid),method,path,parse_qs(query),data or {},raw)
        return r[1] if isinstance(r,tuple) else r

    def order(self,qty=10,paid=True,typ='item',details=True):
        self.db.execute("UPDATE listings SET product_type=?,category_id=?,stock=?,status='published',delivery_eta='20 minutes',delivery_minutes=20 WHERE id=?",(typ,'accounts' if typ=='account' else 'items',qty,self.listing))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,?)',(self.buyer,self.listing,qty))
        o=app.checkout(self.db,self.buyer,True,True,{self.listing:{'player_id':'Recipient#42'}} if details and typ=='item' else None)
        if paid:self.route(self.buyer,'POST','/api/orders/'+o['id']+'/sandbox-complete',{})
        iid=self.db.execute('SELECT id FROM order_items WHERE order_id=?',(o['id'],)).fetchone()['id']
        return o['id'],iid

    def deliver(self,oid,iid,quantity,key='batch-1'):
        return self.route(self.seller,'POST',f'/api/orders/{oid}/deliver',{'item_id':iid,'quantity':quantity,'delivery':'Delivered game items with transfer reference ABC-123.','request_key':key})

    def test_partial_delivery_is_atomic_idempotent_and_blocks_early_completion(self):
        oid,iid=self.order();self.deliver(oid,iid,6)
        self.assertEqual(self.db.execute('SELECT delivered_quantity FROM order_items WHERE id=?',(iid,)).fetchone()['delivered_quantity'],6)
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM deliveries').fetchone()['n'],0)
        self.assertTrue(self.deliver(oid,iid,6)['idempotent'])
        for qty in (5,0,-1,True,1.5):
            with self.assertRaises(app.HttpError):self.deliver(oid,iid,qty,'invalid-'+str(qty))
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST',f'/api/orders/{oid}/complete')
        self.deliver(oid,iid,4,'batch-2');self.route(self.buyer,'POST',f'/api/orders/{oid}/complete')
        self.assertEqual(self.route(self.buyer,'GET',f'/api/orders/{oid}')['status'],'completed')
        self.assertEqual(self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow')['items'][0]['delivered_quantity'],10)
        self.assertNotIn('Delivered game',self.db.execute('SELECT payload FROM delivery_batches LIMIT 1').fetchone()['payload'])

    def test_buyer_details_are_private_encrypted_and_locked_after_delivery(self):
        oid,iid=self.order(details=False)
        with self.assertRaises(app.HttpError):self.deliver(oid,iid,1)
        self.route(self.buyer,'POST',f'/api/orders/{oid}/buyer-details',{'item_id':iid,'details':{'player_id':'Game#9876','platform':'PC'}})
        self.assertNotIn('Game#9876',self.db.execute('SELECT payload FROM order_buyer_details').fetchone()['payload'])
        self.assertEqual(self.route(self.seller,'GET',f'/api/orders/{oid}/workflow')['items'][0]['buyer_details']['player_id'],'Game#9876')
        with self.assertRaises(app.HttpError):self.route(self.other,'GET',f'/api/orders/{oid}/workflow')
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST',f'/api/orders/{oid}/buyer-details',{'item_id':iid,'details':{'player_id':'Changed'}})
        self.deliver(oid,iid,1)
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST',f'/api/orders/{oid}/buyer-details',{'item_id':iid,'details':{'player_id':'Changed'}})

    def test_game_specific_details_checkout_validation_and_immutable_promises(self):
        self.db.execute("UPDATE listings SET game_id='pubg-mobile',product_type='currency' WHERE id=?",(self.listing,))
        self.assertEqual([f['key'] for f in app.listing_detail(self.db,self.listing)['buyer_fields']],['player_id','server','platform','meeting'])
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.buyer,self.listing))
        with self.assertRaises(app.HttpError):app.checkout(self.db,self.buyer,True,True,{self.listing:{'player_id':'123'}})
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM orders').fetchone()['n'],0)
        o=app.checkout(self.db,self.buyer,True,True,{self.listing:{'player_id':'123','server':'Asia'}})
        self.db.execute("UPDATE listings SET product_type='account' WHERE id=?",(self.listing,))
        item=self.route(self.buyer,'GET',f"/api/orders/{o['id']}/workflow")['items'][0]
        self.assertEqual(item['policy']['days'],7)
        self.assertIn('server',[f['key'] for f in item['buyer_fields']])

    def test_working_hours_adjust_estimate_and_vacation_keeps_existing_orders(self):
        settings={'timezone':'Asia/Tashkent','hours':[{'day':0,'start':'18:00','end':'22:00'}],'vacation':False}
        self.route(self.seller,'POST','/api/seller/availability',settings)
        moment=datetime(2026,10,19,10,0,tzinfo=timezone.utc)
        self.assertEqual(ops.next_open(settings,moment),datetime(2026,10,19,13,0,tzinfo=timezone.utc))
        oid,iid=self.order();self.route(self.seller,'POST','/api/seller/availability',{**settings,'vacation':True})
        availability=self.route(self.seller,'GET','/api/seller/availability')
        self.assertEqual(availability['active_count'],1);self.assertEqual(availability['active_orders'][0]['id'],oid)
        self.assertTrue(app.listing_detail(self.db,self.listing)['availability']['vacation'])
        self.assertIsNone(app.listing_detail(self.db,self.listing)['estimated_delivery_at'])
        self.deliver(oid,iid,10)
        self.db.execute("UPDATE listings SET stock=10,status='published' WHERE id=?",(self.listing,));self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.other,self.listing))
        with self.assertRaises(app.HttpError):app.checkout(self.db,self.other,True,True)

    def request_cancel(self,oid):return self.route(self.buyer,'POST',f'/api/orders/{oid}/cancellation',{'reason':'changed_mind','details':'Please cancel this order before delivery.'})

    def test_unpaid_cancellation_releases_reservation_and_cannot_pay_again(self):
        oid,iid=self.order(paid=False);self.request_cancel(oid)
        self.assertEqual(self.db.execute('SELECT reserved FROM listings WHERE id=?',(self.listing,)).fetchone()['reserved'],0)
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST',f'/api/orders/{oid}/sandbox-complete')
        self.assertEqual(self.route(self.buyer,'GET',f'/api/orders/{oid}')['status'],'cancelled')

    def test_paid_cancellation_requires_seller_agreement_and_preserves_audit(self):
        oid,iid=self.order();self.request_cancel(oid)
        with self.assertRaises(app.HttpError):self.deliver(oid,iid,1)
        with self.assertRaises(app.HttpError):self.request_cancel(oid)
        self.route(self.seller,'POST',f'/api/orders/{oid}/cancellation',{'action':'accept','note':'The items have not been sent; I agree.'})
        w=self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow')
        self.assertEqual(w['cancellations'][0]['status'],'accepted');self.assertEqual(w['order']['status'],'refunded')
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM ledger_entries WHERE entry_type='buyer_refund'").fetchone()['n'],1)
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST',f'/api/orders/{oid}/cancellation',{'action':'accept','note':'Duplicate must not cause a second refund.'})

    def test_disagreement_escalates_and_moderator_can_resume_delivery(self):
        oid,iid=self.order();self.request_cancel(oid)
        self.route(self.seller,'POST',f'/api/orders/{oid}/cancellation',{'action':'reject','note':'The delivery has already been arranged.'})
        self.assertEqual(self.route(self.admin,'GET','/api/order-cases')['cancellations'][0]['status'],'escalated')
        self.route(self.admin,'POST',f'/api/orders/{oid}/cancellation',{'action':'decline','note':'The original delivery agreement remains valid.'})
        self.deliver(oid,iid,10)

    def test_partial_delivery_cancellation_requires_moderator_even_if_seller_agrees(self):
        oid,iid=self.order();self.deliver(oid,iid,6);self.request_cancel(oid)
        self.route(self.seller,'POST',f'/api/orders/{oid}/cancellation',{'action':'accept','note':'Agree but moderator must consider the six sent items.'})
        w=self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow');self.assertEqual(w['cancellations'][0]['status'],'escalated');self.assertEqual(w['order']['status'],'awaiting_delivery')
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM ledger_entries WHERE entry_type='buyer_refund'").fetchone()['n'],0)

    def test_all_product_types_allow_order_evidence_and_private_photo_authorization(self):
        for typ in ('item','currency','service','code','account','digital'):
            oid,iid=self.order(qty=1,typ=typ)
            self.route(self.seller,'POST',f'/api/orders/{oid}/evidence',{'item_id':iid,'body':'Delivery reference, result and verification details.'},raw=b'{"body":"json is not an image"}')
            with self.assertRaises(app.HttpError):self.route(self.other,'POST',f'/api/orders/{oid}/evidence',{'item_id':iid,'body':'Unrelated person cannot submit evidence.'})
            with patch.object(app,'require_private_evidence_bucket'),patch.object(app,'normalize_account_evidence',return_value=b'webp'),patch.object(app.storage_r2,'put_evidence') as put,patch.object(app.storage_r2,'evidence_url',return_value='https://private.invalid/signed'):
                self.handler.headers={'Content-Type':'image/png'}
                trade.route(self.handler,self.db,self.ctx(self.seller),'POST',f'/api/orders/{oid}/evidence',{'item_id':[iid]}, {},b'photo',vars(app))
                put.assert_called_once()
                app.storage_r2._key(put.call_args.args[0])
                w=self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow');self.assertEqual(len(w['artifacts']),2);self.assertNotIn('object_path',w['artifacts'][1])

    def test_after_sale_window_and_policy_are_enforced_and_case_is_tracked(self):
        oid,iid=self.order();self.deliver(oid,iid,10);self.route(self.buyer,'POST',f'/api/orders/{oid}/complete')
        self.assertIsNotNone(self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow')['order']['protection_until'])
        case=self.route(self.buyer,'POST',f'/api/orders/{oid}/after-sale',{'reason':'missing_items','details':'A part of the delivered collection is missing; see transfer log.'})
        self.route(self.seller,'POST','/api/order-cases/'+case['id'],{'body':'Please send the game inventory history.'})
        self.route(self.admin,'POST','/api/order-cases/'+case['id'],{'action':'revise','body':'Evidence supports the buyer. Support will arrange the next steps.'})
        r=self.route(self.buyer,'GET','/api/order-cases/'+case['id']);self.assertEqual(r['case']['remedy'],'manual_followup_required')
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/order-cases/'+case['id'])
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST',f'/api/orders/{oid}/after-sale',{'reason':'missing_items','details':'Duplicate cases must not be created for the same completion.'})
        self.db.execute("UPDATE orders SET protection_until='2000-01-01T00:00:00+00:00' WHERE id=?",(oid,))
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST',f'/api/orders/{oid}/after-sale',{'reason':'missing_items','details':'An expired reporting period must be enforced server side.'})

    def test_dispute_appeal_needs_new_evidence_and_resolved_decision_within_seven_days(self):
        oid,iid=self.order();self.route(self.buyer,'POST',f'/api/orders/{oid}/dispute',{'details':'The seller has not provided delivery.'})
        self.route(self.admin,'POST',f'/api/admin/disputes/{oid}',{'action':'refund_buyer','note':'The evidence supports a sandbox refund.'})
        case=self.route(self.seller,'POST',f'/api/orders/{oid}/appeal',{'reason':'new_evidence','details':'New transfer logs not available during the original review are attached.'})
        self.assertEqual(self.route(self.admin,'GET','/api/order-cases/'+case['id'])['case']['kind'],'appeal')
        self.db.execute("UPDATE reports SET resolved_at='2000-01-01T00:00:00+00:00' WHERE order_id=?",(oid,))
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST',f'/api/orders/{oid}/appeal',{'reason':'new_evidence','details':'An old moderator decision cannot be appealed after its deadline.'})

    def test_saved_search_uses_catalogue_filters_and_deduplicates_notifications(self):
        saved=self.route(self.buyer,'POST','/api/saved-searches',{'name':'Affordable Valorant items','filters':{'game':'valorant','max':'60000','condition':'Factory New'}})
        self.assertEqual(len(self.route(self.buyer,'GET','/api/saved-searches')),1)
        with self.assertRaises(app.HttpError):self.route(self.other,'DELETE','/api/saved-searches/'+saved['id'])
        lid=app.ident();self.db.execute("INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,stock,status,attributes_json) VALUES(?,?,'valorant','items','Factory New test item','An actual matching test listing.','item',55000,10,'published',?)",(lid,self.seller,json.dumps({'condition':'Factory New'})))
        app.marketplace_features.alert_publication(self.db,lid,vars(app));app.marketplace_features.alert_publication(self.db,lid,vars(app))
        notices=self.db.execute("SELECT * FROM notifications WHERE user_id=? AND kind='saved_search'",(self.buyer,)).fetchall();self.assertEqual(len(notices),1);self.assertEqual(notices[0]['href'],'/listing/'+lid)
        self.route(self.buyer,'PATCH','/api/saved-searches/'+saved['id'],{'enabled':False})
        self.route(self.buyer,'DELETE','/api/saved-searches/'+saved['id']);self.assertEqual(self.route(self.buyer,'GET','/api/saved-searches'),[])

    def test_overdue_cancellation_escalates_once_and_followup_has_a_final_state(self):
        oid,iid=self.order();self.request_cancel(oid)
        self.db.execute("UPDATE order_cancellations SET response_due_at='2000-01-01T00:00:00+00:00' WHERE order_id=?",(oid,))
        first=self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow')
        self.assertEqual(first['cancellations'][0]['status'],'escalated')
        count=self.db.execute("SELECT COUNT(*) n FROM notifications WHERE kind='order_case'").fetchone()['n']
        self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow')
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE kind='order_case'").fetchone()['n'],count)
        self.route(self.admin,'POST',f'/api/orders/{oid}/cancellation',{'action':'decline','note':'Delivery must continue under the original agreement.'})
        self.deliver(oid,iid,10);self.route(self.buyer,'POST',f'/api/orders/{oid}/complete')
        case=self.route(self.buyer,'POST',f'/api/orders/{oid}/after-sale',{'reason':'missing_items','details':'One promised attribute is missing; supporting evidence provided.'})
        self.route(self.admin,'POST','/api/order-cases/'+case['id'],{'action':'revise','body':'Seller must provide the missing item as a corrective delivery.'})
        self.assertEqual(self.route(self.buyer,'GET','/api/order-cases/'+case['id'])['case']['status'],'followup')
        self.route(self.buyer,'POST','/api/order-cases/'+case['id'],{'body':'The missing item has now been received and checked.'})
        self.route(self.admin,'POST','/api/order-cases/'+case['id'],{'action':'close_followup','body':'Both parties confirm that the corrective delivery is complete.'})
        self.assertEqual(self.route(self.buyer,'GET','/api/order-cases/'+case['id'])['case']['status'],'resolved')
        appeal=self.route(self.buyer,'POST',f'/api/orders/{oid}/appeal',{'source_id':'case:'+case['id'],'reason':'new_evidence','details':'Additional transfer logs reveal a problem that was not previously considered.'})
        self.assertEqual(self.route(self.buyer,'GET','/api/order-cases/'+appeal['id'])['case']['source_id'],'case:'+case['id'])
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/order-cases/'+case['id'],{'body':'Closed cases cannot be changed.'})

    def test_multiple_sellers_see_only_their_lines_and_all_must_consent(self):
        self.db.execute("INSERT INTO seller_profiles(user_id,shop_name,verification_status,selling_enabled,identity_provider,identity_status) VALUES(?,'Second Shop','verified',1,'didit','verified')",(self.other,))
        second=app.ident()
        self.db.execute("INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,stock,status) VALUES(?,?,'valorant','codes','Second seller code','A separate seller product.','code',10000,5,'published')",(second,self.other))
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,1)',(self.buyer,second))
        oid,iid=self.order(qty=1)
        iid=self.db.execute('SELECT id FROM order_items WHERE order_id=? AND seller_id=?',(oid,self.seller)).fetchone()['id']
        first=self.route(self.seller,'GET',f'/api/orders/{oid}/workflow')
        self.assertEqual(len(first['items']),1);self.assertEqual(first['items'][0]['id'],iid if first['items'][0]['seller_id']==self.seller else '')
        second_line=self.route(self.other,'GET',f'/api/orders/{oid}/workflow')['items'][0]['id']
        with self.assertRaises(app.HttpError):self.deliver(oid,second_line,1)
        self.request_cancel(oid)
        self.route(self.seller,'POST',f'/api/orders/{oid}/cancellation',{'action':'accept','note':'I agree to cancel my part of this order.'})
        self.assertEqual(self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow')['order']['status'],'paid')
        self.route(self.other,'POST',f'/api/orders/{oid}/cancellation',{'action':'accept','note':'I also agree to cancel without delivery.'})
        self.assertEqual(self.route(self.buyer,'GET',f'/api/orders/{oid}/workflow')['order']['status'],'refunded')

if __name__=='__main__':unittest.main()

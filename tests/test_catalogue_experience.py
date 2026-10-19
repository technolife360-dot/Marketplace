import base64
import io
import json
import unittest
import zipfile
from urllib.parse import parse_qs
from unittest.mock import patch
from tests import test_marketplace as fixtures
from tests import test_http_workflows as http
import app
import catalogue_experience as ex

class ExperienceFlows(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    def route(self,uid,method,url,data=None,raw=b''):
        path,_,query=url.partition('?');self.handler.headers={}
        r=self.handler.route(self.db,self.ctx(uid),method,path,parse_qs(query),data or {},raw)
        return r[1] if isinstance(r,tuple) else r
    def item(self,typ='item'):
        self.db.execute("UPDATE listings SET product_type=?,category_id=?,stock=10,status='published',attributes_json=? WHERE id=?",(typ,'codes' if typ=='code' else 'items',json.dumps({'item_name':'Karambit','condition':'Factory New','item_type':'Knife','float_value':'0.03'}) if typ=='item' else '{}',self.listing))
        return self.listing
    def csv(self,title='Imported collection item'):
        import csv
        out=io.StringIO();w=csv.DictWriter(out,fieldnames=['game_name','category_id','title','description','price_minor','stock','platform','region','delivery_eta','requirements','item_name']);w.writeheader();w.writerow({'game_name':'Counter-Strike 2','category_id':'items','title':title,'description':'A clearly described collection item with its exact condition and delivery details.','price_minor':'45000','stock':'5','platform':'PC','region':'Global','delivery_eta':'20 minutes','requirements':'Provide your player ID for delivery.','item_name':'Collection item'});return out.getvalue().encode()
    def order(self,typ='item',qty=2):
        self.item(typ);self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,?)',(self.buyer,self.listing,qty))
        order=app.checkout(self.db,self.buyer,True,True,{self.listing:{'player_id':'TestPlayer#42'}} if typ=='item' else {})
        return order['id']
    def conversation(self):return self.route(self.buyer,'POST','/api/conversations',{'listing_id':self.listing})['id']

    def test_context_schema_and_facets_use_real_matching_counts(self):
        self.item();self.db.execute("UPDATE listings SET game_id='counter-strike-2' WHERE id=?",(self.listing,))
        r=self.route(None,'GET','/api/catalogue/facets?game=counter-strike-2&category=items')
        self.assertIn('float_value',[v['key'] for v in r['fields']]);self.assertEqual(r['facets']['condition'][0],{'value':'Factory New','count':1})
        code=self.route(None,'GET','/api/catalogue/schema?game=counter-strike-2&type=code')
        self.assertIn('redemption_region',[v['key'] for v in code['fields']]);self.assertNotIn('float_value',[v['key'] for v in code['fields']])
        self.assertEqual(self.route(None,'GET','/api/listings?game=counter-strike-2&condition=Battle-Scarred')['total_count'],0)
    def test_multilingual_game_and_typo_product_search(self):
        self.item();self.db.execute("UPDATE listings SET game_id='counter-strike-2',title='Karambit collection skin' WHERE id=?",(self.listing,))
        for q in ('кс2','kontr strayk','csgo','counter strike'):
            self.assertEqual(self.route(None,'GET','/api/listings?q='+q)['total_count'],1)
        result=self.route(None,'GET','/api/listings?q=karambti')
        self.assertEqual(result['total_count'],1);self.assertEqual(result['corrected_query'],'karambit')
    def test_equivalent_offers_do_not_mix_regions_platforms_or_variants(self):
        self.item();self.db.execute("UPDATE listings SET platform='PC',region='Global' WHERE id=?",(self.listing,))
        second=app.ident();self.db.execute("INSERT INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,stock,status,platform,region,attributes_json) SELECT ?,seller_id,game_id,category_id,'Another Karambit offer',description,product_type,49000,5,'published',platform,region,attributes_json FROM listings WHERE id=?",(second,self.listing))
        r=self.route(None,'GET','/api/catalogue/offers/'+self.listing);self.assertEqual(len(r['items']),2)
        self.db.execute("UPDATE listings SET region='Europe' WHERE id=?",(second,));self.assertEqual(len(self.route(None,'GET','/api/catalogue/offers/'+self.listing)['items']),1)
    def test_price_watch_preferences_and_deduplicated_alerts(self):
        self.item();self.route(self.buyer,'POST','/api/price-watches/'+self.listing,{'target_minor':40000})
        self.db.execute('UPDATE listings SET price_minor=39000 WHERE id=?',(self.listing,));ex.price_alerts(self.db,self.listing,vars(app));ex.price_alerts(self.db,self.listing,vars(app))
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND kind='favorite'",(self.buyer,)).fetchone()['n'],1)
        self.route(self.buyer,'POST','/api/experience/settings',{'favorite':False});self.db.execute('UPDATE listings SET price_minor=30000 WHERE id=?',(self.listing,));ex.price_alerts(self.db,self.listing,vars(app))
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND kind='favorite'",(self.buyer,)).fetchone()['n'],1)
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/price-watches/'+self.listing,{'target_minor':True})
    def test_collections_are_account_scoped_capped_and_replaceable(self):
        self.route(self.buyer,'POST','/api/collections/compare',{'ids':[self.listing]})
        self.assertEqual(self.route(self.buyer,'GET','/api/collections/compare')['ids'],[self.listing]);self.assertEqual(self.route(self.other,'GET','/api/collections/compare')['ids'],[])
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/collections/compare',{'ids':['a','b','c','d']})
        self.route(self.buyer,'POST','/api/collections/compare',{'ids':[]});self.assertTrue(self.route(self.buyer,'GET','/api/collections/compare')['initialized']);self.assertEqual(self.route(self.buyer,'GET','/api/collections/compare')['ids'],[])
    def test_chat_history_search_cursor_privacy_and_send_retry(self):
        cid=self.conversation()
        for n in range(125):self.db.execute('INSERT INTO messages(id,conversation_id,sender_id,body) VALUES(?,?,?,?)',(app.ident(),cid,self.buyer,'special needle' if n==3 else 'Message '+str(n)))
        r=self.route(self.seller,'GET','/api/conversations/'+cid);self.assertEqual(len(r['messages']),50);self.assertTrue(r['has_more'])
        older=self.route(self.seller,'GET','/api/conversations/'+cid+'?before='+r['next_before']);self.assertEqual(len(older['messages']),50);self.assertFalse({m['id'] for m in r['messages']}&{m['id'] for m in older['messages']})
        searched=self.route(self.seller,'GET','/api/conversations/'+cid+'?q=special');self.assertEqual(len(searched['messages']),1);self.assertIsNotNone(searched['messages'][0]['read_at'])
        first=self.route(self.seller,'POST','/api/conversations/'+cid+'/messages',{'body':'A response','request_key':'same-draft'});again=self.route(self.seller,'POST','/api/conversations/'+cid+'/messages',{'body':'A response','request_key':'same-draft'})
        self.assertEqual(first['id'],again['id']);self.assertTrue(again['idempotent'])
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/conversations/'+cid+'?q=special')
    def test_chat_archive_mute_report_and_saved_replies(self):
        cid=self.conversation();self.route(self.buyer,'POST',f'/api/conversations/{cid}/preferences',{'archived':True,'muted':True})
        self.assertEqual(self.route(self.buyer,'GET','/api/conversations'),[]);self.assertEqual(self.route(self.buyer,'GET','/api/conversations?archived=1')[0]['id'],cid)
        self.route(self.seller,'POST',f'/api/conversations/{cid}/messages',{'body':'Muted conversation message'})
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE user_id=? AND kind='message'",(self.buyer,)).fetchone()['n'],0)
        report=self.route(self.buyer,'POST',f'/api/conversations/{cid}/report',{'details':'An inappropriate repeated request needs moderator review.'});self.assertTrue(report['id'])
        quick=self.route(self.seller,'POST','/api/seller/quick-replies',{'title':'Delivery hours','body':'We deliver during the published working hours.'})
        self.assertEqual(len(quick),1)
        with self.assertRaises(app.HttpError):self.route(self.other,'POST',f'/api/conversations/{cid}/report',{'details':'Unrelated user must not report this private chat.'})
    def test_csv_import_preview_commit_and_replay_have_no_partial_side_effects(self):
        initial=self.db.execute('SELECT COUNT(*) n FROM listings').fetchone()['n']
        r=self.route(self.seller,'POST','/api/seller/import/preview?format=csv',raw=self.csv());self.assertTrue(r['valid']);self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM listings').fetchone()['n'],initial)
        imported=self.route(self.seller,'POST','/api/seller/import/'+r['id']+'/commit');self.assertEqual(imported['count'],1);self.assertEqual(self.db.execute('SELECT status FROM listings WHERE id=?',(imported['ids'][0],)).fetchone()['status'],'draft')
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/import/'+r['id']+'/commit')
        invalid=self.route(self.seller,'POST','/api/seller/import/preview?format=csv',raw=self.csv(title='x'));self.assertFalse(invalid['valid'])
        with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/import/'+invalid['id']+'/commit')
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/seller/import/'+r['id']+'/commit')
    def test_xlsx_reads_values_and_rejects_formula_or_zip_bomb(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1" t="inlineStr"><is><t>title</t></is></c></row><row><c r="A2" t="inlineStr"><is><t>Sample item</t></is></c></row></sheetData></worksheet>')
        self.assertEqual(ex.parse_import(out.getvalue(),'xlsx'),[{'title':'Sample item'}])
        bad=io.BytesIO()
        with zipfile.ZipFile(bad,'w') as z:z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c r="A1"><f>HYPERLINK("https://bad.invalid")</f><v>1</v></c></row></sheetData></worksheet>')
        with self.assertRaises(ValueError):ex.parse_import(bad.getvalue(),'xlsx')
    def test_code_inventory_is_encrypted_private_and_allocated_once(self):
        self.item('code');self.db.execute('UPDATE listings SET stock=2 WHERE id=?',(self.listing,))
        added=self.route(self.seller,'POST',f'/api/seller/listings/{self.listing}/codes',{'codes':['CODE-ALPHA-123','CODE-BETA-456']});self.assertEqual(added['added'],2)
        self.assertNotIn('CODE-ALPHA',self.db.execute('SELECT cipher FROM seller_code_inventory LIMIT 1').fetchone()['cipher'])
        with self.assertRaises(app.HttpError):self.route(self.other,'GET',f'/api/seller/listings/{self.listing}/codes')
        self.route(self.seller,'POST',f'/api/seller/listings/{self.listing}/sales-settings',{'min_quantity':1,'unit_label':'code','automatic_delivery':True})
        self.assertEqual(self.db.execute('SELECT status FROM listings WHERE id=?',(self.listing,)).fetchone()['status'],'pending_review')
        self.db.execute("UPDATE listings SET status='published' WHERE id=?",(self.listing,)) # Moderator approval of changed sales terms.
        self.db.execute('INSERT INTO carts(user_id,listing_id,quantity) VALUES(?,?,2)',(self.buyer,self.listing));order=app.checkout(self.db,self.buyer,True,True)
        self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete")
        result=self.route(self.buyer,'GET',f"/api/orders/{order['id']}");self.assertEqual(result['status'],'delivered');self.assertIn('CODE-ALPHA',result['items'][0]['delivery']['protected_payload'])
        self.assertTrue(self.route(self.buyer,'POST',f"/api/orders/{order['id']}/sandbox-complete")['idempotent']);self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM delivery_batches').fetchone()['n'],1)
        self.assertNotIn('CODE-ALPHA',json.dumps(self.route(self.seller,'GET','/api/listings/'+self.listing)))
    def test_minimum_quantity_compatibility_and_stock_alert(self):
        self.item('code');self.db.execute("UPDATE listings SET min_quantity=3,platform='Steam',region='Europe',attributes_json=? WHERE id=?",(json.dumps({'redemption_region':'Europe'}),self.listing))
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/cart',{'listing_id':self.listing,'quantity':1})
        self.route(self.buyer,'POST','/api/cart',{'listing_id':self.listing,'quantity':3})
        with self.assertRaises(app.HttpError):app.checkout(self.db,self.buyer,True,True,buyer_context={self.listing:{'platform':'Xbox','region':'US'}})
        self.assertFalse(ex.compatibility(dict(self.db.execute('SELECT * FROM listings WHERE id=?',(self.listing,)).fetchone()),{'platform':'Steam','region':'EU'}))
        self.route(self.seller,'POST',f'/api/seller/listings/{self.listing}/stock-alert',{'threshold':2});self.db.execute('UPDATE listings SET stock=2 WHERE id=?',(self.listing,));ex.stock_check(self.db,self.listing,vars(app));ex.stock_check(self.db,self.listing,vars(app))
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE kind='low_stock'").fetchone()['n'],1)
    def test_analytics_deduplicates_views_and_seller_insights_are_private(self):
        self.item();self.route(self.buyer,'POST','/api/catalogue/view',{'listing_id':self.listing});self.route(self.buyer,'POST','/api/catalogue/view',{'listing_id':self.listing})
        r=self.route(self.seller,'GET','/api/seller/insights?days=7');views=[v for v in r['listings'] if v['kind']=='view'];self.assertEqual(views[0]['total'],1);self.assertEqual(r['quality']['orders'],0)
        with self.assertRaises(app.HttpError):self.route(self.buyer,'GET','/api/seller/insights')
    def test_email_is_opt_in_and_queue_never_contains_private_chat_body(self):
        cid=self.conversation();self.route(self.buyer,'POST','/api/experience/settings',{'email':True})
        self.route(self.seller,'POST',f'/api/conversations/{cid}/messages',{'body':'Never put this private message in an email.'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) n FROM notification_outbox').fetchone()['n'],1)
        with patch.object(app.email_service,'is_configured',return_value=True),patch.object(app.email_service,'send_marketplace_alert') as send:
            ex.dispatch_emails(self.db,vars(app));send.assert_called_once();self.assertNotIn('private message',repr(send.call_args))
        with patch.object(app.email_service,'is_configured',return_value=True),patch.object(app.email_service,'send_marketplace_alert') as send:ex.dispatch_emails(self.db,vars(app));send.assert_not_called()
    def test_structured_moderation_corrections_are_owner_only(self):
        self.db.execute("UPDATE listings SET status='pending_review' WHERE id=?",(self.listing,));fix={'image_url':'Upload a clear photo of the exact item being sold.'}
        self.route(self.admin,'POST','/api/admin/listings/'+self.listing,{'action':'reject','note':'The product photo needs correction.','corrections':fix})
        self.assertEqual(self.route(self.seller,'GET','/api/listings/'+self.listing)['corrections'],fix)
        with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/listings/'+self.listing)
    def test_public_store_and_game_pages_have_canonical_metadata_and_real_404s(self):
        store=ex.seo_html('/store/'+self.seller,vars(app)).decode();self.assertIn('/store/'+self.seller,store);self.assertIn('Seller Shop',store)
        self.db.execute('UPDATE seller_profiles SET bio=? WHERE user_id=?',(r'Rare \1 <script>alert(1)</script>',self.seller))
        escaped=ex.seo_html('/store/'+self.seller,vars(app)).decode();self.assertIn(r'\1 &lt;script&gt;',escaped);self.assertNotIn('<script>alert(1)</script>',escaped)
        self.assertIsNone(ex.seo_html('/store/not-found',vars(app)))
        game=ex.seo_html('/games/counter-strike-2/items',vars(app)).decode();self.assertIn('Before you buy',game);self.assertIn('/games/counter-strike-2/items',game)
    def test_all_active_games_have_account_schema_and_numeric_validation(self):
        for game in ('counter-strike-2','pubg-mobile','mobile-legends','free-fire','honor-of-kings','roblox','valorant','genshin-impact','dota-2'):
            fields=ex.schema(game,'account');self.assertTrue(fields);self.assertIn('account_level',[f['key'] for f in fields])
        with self.assertRaises(app.HttpError):ex.validate_game({'account_level':'not-a-level'},'roblox','account',vars(app))

if __name__=='__main__':unittest.main()

class MonitoringMailTests(unittest.TestCase):
    def test_monitor_recipient_and_run_url_are_restricted(self):
        import email_service
        with patch.object(email_service,'is_configured',return_value=True),patch.object(email_service,'_deliver') as deliver:
            with self.assertRaises(ValueError):email_service.send_monitor_alert('unexpected@example.test','Health','https://github.com/technolife360-dot/Marketplace/actions/runs/123')
            with self.assertRaises(ValueError):email_service.send_monitor_alert('sentryloot@gamestorehub.com','Health','https://untrusted.invalid/123')
            email_service.send_monitor_alert('sentryloot@gamestorehub.com','Health','https://github.com/technolife360-dot/Marketplace/actions/runs/123')
            deliver.assert_called_once();message=deliver.call_args.args[0]
            self.assertEqual(message['To'],'sentryloot@gamestorehub.com')
            self.assertNotIn('Authorization',str(message))

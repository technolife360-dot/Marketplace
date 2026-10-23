"""Signed Didit events and admin-only review workflow against isolated storage."""
import json
import time
import unittest
from unittest.mock import patch

import app
import seller_verification as verification
from tests import test_marketplace as fixtures


class SellerVerificationFlows(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    route=fixtures.MarketplaceFlows.route

    def pending(self):
        self.db.execute("UPDATE seller_profiles SET identity_reference='session-123',selling_enabled=0,verification_status='pending' WHERE user_id=?",(self.seller,))
        app.account_contacts.save(self.db,self.seller,'+60123456789')
        self.db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('account_phone_verified:'+self.seller,'+60123456789'))

    def test_admin_only_list_detail_report_and_decision(self):
        self.pending()
        for uid in (None,self.buyer,self.seller):
            for method,path,data in [('GET','/api/admin/verification',{}),('GET','/api/admin/verification/'+self.seller,{}),('POST','/api/admin/verification/'+self.seller+'/report',{}),('POST','/api/admin/sellers/'+self.seller,{'action':'approve','note':'Checked by admin'})]:
                with self.assertRaises(app.HttpError) as e:self.route(uid,method,path,data)
                self.assertIn(e.exception.status,(401,403))
        result=self.route(self.admin,'GET','/api/admin/verification')
        self.assertEqual(result['stats']['pending'],1)
        self.assertEqual(result['items'][0]['admin_status'],'pending')
        self.assertNotIn('password_hash',str(result))
        self.assertNotIn('DIDIT_API_KEY',str(result))

    def test_reviewer_can_request_info_then_approve_and_log_the_reason(self):
        self.pending()
        result=self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':'request_info','note':'Explain your product ownership.','expected_session':'session-123'})
        self.assertFalse(result['selling_enabled'])
        self.assertEqual(self.route(self.admin,'GET','/api/admin/verification/'+self.seller)['timeline'][0]['note'],'Explain your product ownership.')
        result=self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':'approve','note':'All identity checks reviewed.','expected_session':'session-123'})
        self.assertTrue(result['selling_enabled'])
        self.assertEqual(self.route(self.admin,'GET','/api/admin/verification')['stats']['approved'],1)

    def test_approval_blocks_missing_didit_stale_session_and_self_review(self):
        self.pending()
        for params,status in [({'expected_session':'other'},409),({},409)]:
            if not params:self.db.execute("UPDATE seller_profiles SET identity_status='pending' WHERE user_id=?",(self.seller,))
            with self.assertRaises(app.HttpError) as e:self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':'approve','note':'Reviewed the checks',**params})
            self.assertEqual(e.exception.status,status)
        self.db.execute('INSERT INTO admin_accounts(user_id) VALUES(?)',(self.seller,))
        with self.assertRaises(app.HttpError) as e:self.route(self.seller,'POST','/api/admin/sellers/'+self.seller,{'action':'approve','note':'Approve my profile'})
        self.assertEqual(e.exception.status,403)

    def test_webhook_keeps_only_summary_and_never_enables_sales(self):
        self.pending()
        payload={'timestamp':int(time.time()),'webhook_type':'status.updated','session_id':'session-123','status':'Approved',
            'decision':{'id_verifications':[{'status':'Approved','first_name':'Test','last_name':'Person','document_number':'PRIVATE123456','front_image':'https://media.didit.me/private.jpg','date_of_birth':'1990-01-01','issuing_state':'UZB','document_type':'Passport'}],
                        'liveness_checks':[{'status':'Approved','reference_image':'https://media.didit.me/selfie.jpg'}],'face_matches':[{'status':'Approved'}]}}
        self.handler.headers={}
        with patch.object(app.identity_service,'verify_webhook',return_value=payload):
            self.route(None,'POST','/api/webhooks/didit')
        saved=verification.read(self.db,self.seller)
        self.assertEqual(saved['document_last4'],'3456')
        for private in ('PRIVATE123456','private.jpg','selfie.jpg','1990-01-01'):
            self.assertNotIn(private,json.dumps(saved))
        self.assertEqual(saved['checks']['face_matches'],'Approved')
        self.assertEqual(self.db.execute('SELECT selling_enabled FROM seller_profiles WHERE user_id=?',(self.seller,)).fetchone()['selling_enabled'],0)
        # Duplicate/stale provider events must not overwrite a later decision.
        payload['status']='Declined'
        with patch.object(app.identity_service,'verify_webhook',return_value=payload):
            self.assertEqual(self.route(None,'POST','/api/webhooks/didit')['ignored'],'stale event')
        self.assertEqual(verification.read(self.db,self.seller)['provider_status'],'Approved')

    def test_filtered_queue_reports_all_states_and_does_not_invent_missing_checks(self):
        self.pending()
        self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':'approve','note':'Reviewed the identity'})
        result=self.handler.route(self.db,self.ctx(self.admin),'GET','/api/admin/verification',{'status':['approved'],'q':['Seller Shop']},{})
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['identity'],{})
        result=self.handler.route(self.db,self.ctx(self.admin),'GET','/api/admin/verification',{'status':['pending']},{})
        self.assertEqual(result['total'],0)

    def test_secure_report_is_on_demand_audited_and_not_persisted(self):
        self.pending()
        decision={'session_id':'session-123','status':'Approved','id_verifications':[{'status':'Approved','document_number':'SECRET1234','front_image':'https://media.didit.me/signed.jpg'}]}
        with patch.object(app.identity_service,'retrieve_decision',return_value=decision) as remote:
            self.route(self.admin,'GET','/api/admin/verification/'+self.seller)
            remote.assert_not_called()
            result=self.route(self.admin,'POST','/api/admin/verification/'+self.seller+'/report')
        self.assertEqual(result['media'][0]['url'],'https://media.didit.me/signed.jpg')
        self.assertEqual(result['identity']['document_last4'],'1234')
        self.assertEqual(verification.read(self.db,self.seller),{})
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM audit_logs WHERE action='didit_report_viewed'").fetchone()['n'],1)

    def test_webhook_summary_and_status_roll_back_together_on_storage_failure(self):
        self.pending()
        self.db.execute("UPDATE seller_profiles SET identity_status='pending' WHERE user_id=?",(self.seller,))
        payload={'timestamp':int(time.time()),'webhook_type':'status.updated','session_id':'session-123','status':'Approved',
            'decision':{key:[{'status':'Approved'}] for key in verification.CHECKS}}
        self.handler.headers={}
        with patch.object(app.identity_service,'verify_webhook',return_value=payload),patch.object(verification,'save',side_effect=RuntimeError('storage unavailable')):
            with self.assertRaises(RuntimeError):self.route(None,'POST','/api/webhooks/didit')
        current=self.db.execute('SELECT identity_status,identity_last_event_at FROM seller_profiles WHERE user_id=?',(self.seller,)).fetchone()
        self.assertEqual(current['identity_status'],'pending')
        self.assertIsNone(current['identity_last_event_at'])
        with patch.object(app.identity_service,'verify_webhook',return_value=payload):
            self.assertTrue(self.route(None,'POST','/api/webhooks/didit')['ok'])
        self.assertEqual(verification.read(self.db,self.seller)['checks']['id_verifications'],'Approved')

    def test_exact_decision_goes_to_bell_and_email_once_without_manual_text(self):
        for action in ('approve','reject'):
            self.pending()
            self.db.execute("UPDATE seller_profiles SET identity_status='verified' WHERE user_id=?",(self.seller,))
            with patch.object(app.email_service,'is_configured',return_value=True),patch.object(app.email_service,'send_verification_update') as send:
                result=self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':action})
                self.assertTrue(result['email_sent'])
                send.assert_called_once()
                self.assertEqual(send.call_args.args[0],'seller@test.invalid')
                self.assertEqual(send.call_args.args[3],verification.DECISION_MESSAGES[action])
                notification=self.db.execute('SELECT body FROM notifications WHERE id=?',(send.call_args.args[4],)).fetchone()
                self.assertEqual(notification['body'],verification.DECISION_MESSAGES[action])
                with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':action})
                app.catalogue_experience.dispatch_emails(self.db,vars(app))
                send.assert_called_once()

    def test_request_information_remains_manual_and_failed_email_can_retry(self):
        self.pending()
        with self.assertRaises(app.HttpError):self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':'request_info','note':''})
        text='Please upload a clear photo with all four document corners visible.'
        with patch.object(app.email_service,'is_configured',return_value=True),patch.object(app.email_service,'send_verification_update',side_effect=RuntimeError('temporary unavailable')):
            result=self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':'request_info','note':text})
        self.assertFalse(result['email_sent'])
        queued=self.db.execute('SELECT notification_id,status FROM notification_outbox').fetchone()
        self.assertEqual(queued['status'],'failed')
        with patch.object(app.email_service,'is_configured',return_value=True),patch.object(app.email_service,'send_verification_update') as send:
            self.assertEqual(app.catalogue_experience.dispatch_emails(self.db,vars(app))['sent'],1)
            self.assertEqual(send.call_args.args[3],text)
            self.assertEqual(send.call_args.args[4],queued['notification_id'])
            self.assertEqual(app.catalogue_experience.dispatch_emails(self.db,vars(app))['sent'],0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) n FROM notifications WHERE kind='seller_verification_decision'").fetchone()['n'],1)

    def test_failed_transaction_never_sends_a_decision_email(self):
        self.pending()
        with patch.object(app,'notify',side_effect=RuntimeError('notification storage failed')),patch.object(app.email_service,'send_verification_update') as send:
            with self.assertRaises(RuntimeError):self.route(self.admin,'POST','/api/admin/sellers/'+self.seller,{'action':'reject'})
        send.assert_not_called()
        self.assertEqual(self.db.execute('SELECT verification_status FROM seller_profiles WHERE user_id=?',(self.seller,)).fetchone()['verification_status'],'pending')

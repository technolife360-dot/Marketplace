"""Phone OTP, account ownership and Didit contact forwarding with isolated storage."""
import time
import unittest
from unittest.mock import patch

import app
import account_contacts as contacts
from tests import test_marketplace as fixtures


class PhoneVerificationFlows(unittest.TestCase):
    setUp = fixtures.MarketplaceFlows.setUp
    tearDown = fixtures.MarketplaceFlows.tearDown
    ctx = fixtures.MarketplaceFlows.ctx
    route = fixtures.MarketplaceFlows.route

    def send(self, uid=None, channel='sms'):
        uid = uid or self.buyer
        with patch.object(app.identity_service,'phone_request',return_value={'status':'Success','request_id':'phone-request-1'}) as remote:
            result = self.route(uid,'POST','/api/phone/send',{'phone':'+60 (12) 345-6789','channel':channel})
        return result, remote

    def approved(self, uid=None):
        pending = contacts.challenge(self.db,uid or self.buyer)
        return {'status':'Approved','request_id':pending['request_id'],'vendor_data':pending['reference'],
                'phone':{'status':'Approved','full_number':pending['phone']}}

    def test_phone_send_and_check_require_an_authenticated_verified_account(self):
        for path in ('/api/phone/send','/api/phone/check'):
            with self.assertRaises(app.HttpError) as error:self.route(None,'POST',path,{})
            self.assertEqual(error.exception.status,401)
        self.db.execute('UPDATE users SET email_verified=0 WHERE id=?',(self.buyer,))
        with self.assertRaises(app.HttpError):self.send()

    def test_both_channels_send_normalized_phone_but_do_not_mark_it_verified(self):
        for uid,channel in ((self.buyer,'sms'),(self.other,'whatsapp')):
            result,remote=self.send(uid,channel)
            self.assertTrue(result['sent'])
            self.assertEqual(remote.call_args.args[1]['phone_number'],'+60123456789')
            self.assertEqual(remote.call_args.args[1]['options']['preferred_channel'],channel)
            self.assertFalse(app.user_view(self.db,uid)['phone_verified'])
            self.assertEqual(contacts.read(self.db,uid),'')
            with self.assertRaises(app.HttpError) as error:self.send(uid,channel)
            self.assertEqual(error.exception.status,429)

    def test_correct_bound_code_updates_phone_and_is_consumed_once(self):
        self.send()
        with patch.object(app.identity_service,'phone_request',return_value=self.approved()) as remote:
            result=self.route(self.buyer,'POST','/api/phone/check',{'code':'482135'})
        self.assertTrue(result['verified'])
        self.assertEqual(result['user']['phone'],'+60123456789')
        self.assertTrue(result['user']['phone_verified'])
        self.assertIsNone(contacts.challenge(self.db,self.buyer))
        self.assertEqual(remote.call_args.args[1]['code'],'482135')
        self.assertNotIn('482135',str(self.db.execute('SELECT value FROM platform_config').fetchall()))
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/phone/check',{'code':'482135'})

    def test_wrong_codes_have_a_local_attempt_limit_and_never_change_the_phone(self):
        self.send()
        with patch.object(app.identity_service,'phone_request',return_value={'status':'Failed'}) as remote:
            for _ in range(4):
                with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/phone/check',{'code':'000000'})
        self.assertEqual(remote.call_count,3)
        self.assertFalse(contacts.verified(self.db,self.buyer))

    def test_cross_account_expired_and_mismatched_provider_results_fail_closed(self):
        self.send()
        with self.assertRaises(app.HttpError):self.route(self.other,'POST','/api/phone/check',{'code':'482135'})
        for changed in ({'request_id':'different-session'},{'vendor_data':'different-user'}, {'phone':{'status':'Approved','full_number':'+998901234567'}}):
            with patch.object(app.identity_service,'phone_request',return_value={**self.approved(),**changed}):
                with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/phone/check',{'code':'482135'})
        self.assertFalse(contacts.verified(self.db,self.buyer))
        pending=contacts.challenge(self.db,self.buyer);pending['expires_at']=time.time()-1
        contacts.store(self.db,contacts.CHALLENGE_PREFIX+self.buyer,pending)
        with patch.object(app.identity_service,'phone_request') as remote:
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/phone/check',{'code':'482135'})
            remote.assert_not_called()

    def test_provider_not_activated_is_not_reported_as_a_sent_code(self):
        with patch.object(app.identity_service,'phone_request',side_effect=app.identity_service.IdentityProviderError('SMS and WhatsApp verification are not activated. Please contact support.')):
            with self.assertRaises(app.HttpError) as error:self.route(self.buyer,'POST','/api/phone/send',{'phone':'+60123456789','channel':'sms'})
        self.assertEqual(error.exception.status,503)
        self.assertIsNone(contacts.challenge(self.db,self.buyer))

    def test_unverified_phone_cannot_bypass_profile_or_didit_requirements(self):
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/profile',{'phone':'+60123456789'})
        self.db.execute("UPDATE seller_profiles SET identity_status='not_started' WHERE user_id=?",(self.seller,))
        with patch.object(app.identity_service,'is_configured',return_value=True),patch.object(app.identity_service,'create_verification_session') as remote:
            with self.assertRaises(app.HttpError):self.route(self.seller,'POST','/api/seller/identity-session',{'consent':True})
            remote.assert_not_called()

    def test_didit_uses_verified_account_contacts_not_client_supplied_identity(self):
        self.send(self.seller)
        with patch.object(app.identity_service,'phone_request',return_value=self.approved(self.seller)):
            self.route(self.seller,'POST','/api/phone/check',{'code':'482135'})
        self.db.execute("UPDATE seller_profiles SET identity_status='not_started' WHERE user_id=?",(self.seller,))
        with patch.object(app.identity_service,'is_configured',return_value=True),patch.object(app.identity_service,'create_verification_session',return_value={'session_id':'session-contacts','url':'https://verify.didit.me/session/contacts'}) as remote:
            self.route(self.seller,'POST','/api/seller/identity-session',{'consent':True,'email':'attacker@example.test','phone':'+998901234567'})
        self.assertEqual(remote.call_args.kwargs['email'],'seller@test.invalid')
        self.assertEqual(remote.call_args.kwargs['phone'],'+60123456789')
        detail=self.route(self.admin,'GET','/api/admin/verification/'+self.seller)
        self.assertEqual(detail['phone'],'+60123456789')
        self.assertTrue(detail['phone_verified'])

    def test_invalid_phone_and_channel_do_not_call_the_provider(self):
        for phone,channel in (('12345','sms'),('+123<script>','whatsapp'),('+60123456789','email')):
            with patch.object(app.identity_service,'phone_request') as remote:
                with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/phone/send',{'phone':phone,'channel':channel})
                remote.assert_not_called()

    def test_country_selector_supports_worldwide_national_formats(self):
        countries=self.route(self.buyer,'GET','/api/phone/countries')
        codes={row['country']:row['dial_code'] for row in countries}
        self.assertGreater(len(codes),200)
        self.assertEqual([codes[c] for c in ('UZ','MY','GB','US')],['+998','+60','+44','+1'])
        self.assertEqual(contacts.normalize_phone('90 123 45 67','UZ'),'+998901234567')
        self.assertEqual(contacts.normalize_phone('07400 123456','GB'),'+447400123456')
        self.assertEqual(contacts.normalize_phone('012 3456789','MY'),'+60123456789')
        for country,phone in (('MY','+998901234567'),('XX','1234567'),({},'1234567')):
            with self.assertRaises(ValueError):contacts.normalize_phone(phone,country)

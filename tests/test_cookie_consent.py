import json
import unittest
from http.cookies import SimpleCookie
from tests import test_http_workflows as workflows

class CookieConsentHTTP(unittest.TestCase):
    setUp = workflows.HTTPWorkflows.setUp
    tearDown = workflows.HTTPWorkflows.tearDown
    signed_client = workflows.HTTPWorkflows.signed_client

    def save(self, client=None, analytics=True, support=True, **extra):
        return (client or self.guest).request('POST','/api/cookie-consent',
            {'analytics':analytics,'support':support,**extra},headers={'X-Consent-Request':'1'})

    def test_default_denies_optional_and_does_not_create_identifier(self):
        status,body,headers=self.guest.request('GET','/api/cookie-consent')
        self.assertEqual(status,200)
        self.assertIsNone(body['consent'])
        self.assertNotIn('Set-Cookie',headers)

    def test_accept_persist_revoke_and_audit(self):
        status,accepted,headers=self.save()
        self.assertEqual(status,200)
        self.assertTrue(accepted['consent']['analytics'])
        cookie=SimpleCookie();cookie.load(headers['Set-Cookie'])
        self.assertTrue(cookie['sl_cookie_preferences']['httponly'])
        self.assertEqual(cookie['sl_cookie_preferences']['samesite'],'Lax')
        self.guest.cookie=headers['Set-Cookie'].split(';')[0]
        self.assertEqual(self.guest.request('GET','/api/cookie-consent')[1],accepted)
        _,rejected,_=self.save(analytics=False,support=False)
        self.assertNotEqual(accepted['consent']['receipt_id'],rejected['consent']['receipt_id'])
        self.assertFalse(self.guest.request('GET','/api/cookie-consent')[1]['consent']['support'])
        rows=self.db.execute("SELECT details_json FROM audit_logs WHERE action='cookie_consent_changed' ORDER BY created_at,id").fetchall()
        self.assertEqual(len(rows),2)
        self.assertEqual({json.loads(r['details_json'])['analytics'] for r in rows},{True,False})

    def test_guest_signed_in_csrf_and_cross_origin_validation(self):
        self.assertEqual(self.guest.request('POST','/api/cookie-consent',{'analytics':True,'support':True})[0],403)
        self.assertEqual(self.guest.request('POST','/api/cookie-consent',{'analytics':True,'support':True},headers={'X-Consent-Request':'1','Origin':'https://evil.test','Host':'localhost:8000'})[0],403)
        self.assertEqual(self.save(analytics='true')[0],400)
        self.assertEqual(self.save(self.seller)[0],200)
        self.assertEqual(self.seller.request('POST','/api/cookie-consent',{'analytics':False,'support':False},csrf=False,headers={'X-Consent-Request':'1'})[0],403)

    def test_expired_or_forged_receipt_never_enables_optional_services(self):
        self.guest.cookie='sl_cookie_preferences=forged'
        self.assertIsNone(self.guest.request('GET','/api/cookie-consent')[1]['consent'])
        _,_,headers=self.save()
        self.guest.cookie=headers['Set-Cookie'].split(';')[0]
        row=self.db.execute("SELECT key,value FROM platform_config WHERE key LIKE 'cookie-consent:%'").fetchone()
        value=json.loads(row['value']);value['expires_at']='2000-01-01T00:00:00+00:00'
        self.db.execute('UPDATE platform_config SET value=? WHERE key=?',(json.dumps(value),row['key']))
        self.assertIsNone(self.guest.request('GET','/api/cookie-consent')[1]['consent'])

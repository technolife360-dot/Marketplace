import json
import os
import unittest
from unittest.mock import patch

import email_service


class ResendEmailTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{
            'EMAIL_PROVIDER':'resend','RESEND_API_KEY':'unit-test-key',
            'EMAIL_FROM':'SentryLoot <no-reply@mail.gamestorehub.com>',
            'PUBLIC_BASE_URL':'https://sentryloot.example','MARKETPLACE_MODE':'production'
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_resend_delivery_uses_server_key_and_sends_text_and_branded_html(self):
        class Response:
            status=200
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def read(self,n): return b'{"id":"email-test"}'
        with patch.object(email_service,'urlopen',return_value=Response()) as send:
            email_service.send_action_email('buyer@example.test','Test Buyer','verify','secure-token')
        req=send.call_args.args[0]
        payload=json.loads(req.data.decode())
        self.assertEqual(req.full_url,'https://api.resend.com/emails')
        self.assertEqual(req.get_header('Authorization'),'Bearer unit-test-key')
        self.assertEqual(payload['to'],['buyer@example.test'])
        self.assertIn('SENTRY',payload['html'])
        self.assertIn('secure-token',payload['text'])
        self.assertIn('Email manzilingizni tasdiqlang',payload['subject'])

    def test_template_escapes_user_name_and_order_content(self):
        with patch.object(email_service,'_deliver') as deliver:
            email_service.send_order_update('buyer@example.test','<script>alert(1)</script>','SL-123','paid','To‘lov tasdiqlandi')
        message=deliver.call_args.args[0]
        html=message.get_body(preferencelist=('html',)).get_content()
        self.assertNotIn('<script>',html)
        self.assertIn('&lt;script&gt;',html)
        self.assertIn('SL-123',html)
        self.assertIn('max-width:600px',html)

    def test_english_and_russian_email_templates_follow_account_language(self):
        for language,subject in [('en','Confirm your email'),('ru','Подтвердите')]:
            with self.subTest(language=language), patch.object(email_service,'_deliver') as deliver:
                email_service.send_action_email('buyer@example.test','<Buyer>','verify','private-token',language=language)
                message=deliver.call_args.args[0]
                html=message.get_body(preferencelist=('html',)).get_content()
                self.assertIn(subject,str(message['Subject']))
                self.assertIn('private-token',html)
                self.assertIn('&lt;Buyer&gt;',html)
                self.assertIn('lang="'+language+'"',html)
                self.assertNotIn('Salom,',html)
                self.assertNotIn('Xavfsiz o‘yin bozori',html)
                self.assertNotIn('Bu avtomatik xizmat xabari',html)

    def test_resend_not_configured_without_server_side_key(self):
        with patch.dict(os.environ,{'RESEND_API_KEY':'','EMAIL_API_KEY':''}):
            self.assertFalse(email_service.is_configured())

    def test_verification_email_contains_exact_decision_and_stable_retry_key(self):
        import seller_verification
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,n):return b'{"id":"verification-email-test"}'
        for action,description in seller_verification.DECISION_MESSAGES.items():
            with patch.object(email_service,'urlopen',return_value=Response()) as send:
                email_service.send_verification_update('seller@example.test','<Seller>','Identity verification '+action,description,'notification-123')
            request=send.call_args.args[0];payload=json.loads(request.data)
            self.assertIn(description,payload['text'])
            self.assertEqual(payload['html'].count(description),1)
            self.assertIn('&lt;Seller&gt;',payload['html'])
            self.assertNotIn('Salom',payload['html'])
            self.assertEqual(request.get_header('Idempotency-key'),'seller-review/notification-123')

    def test_resend_requires_verified_domain_sender_in_production(self):
        with patch.dict(os.environ,{'EMAIL_FROM':'SentryLoot <onboarding@resend.dev>'}):
            self.assertFalse(email_service.is_configured())
        with patch.dict(os.environ,{'EMAIL_FROM':''}):
            self.assertFalse(email_service.is_configured())


if __name__=='__main__':
    unittest.main()

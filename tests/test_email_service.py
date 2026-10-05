import json
import os
import unittest
from unittest.mock import patch

import email_service


class ResendEmailTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{
            'EMAIL_PROVIDER':'resend','RESEND_API_KEY':'unit-test-key',
            'EMAIL_FROM':'SentryLoot <onboarding@resend.dev>',
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

    def test_resend_not_configured_without_server_side_key(self):
        with patch.dict(os.environ,{'RESEND_API_KEY':'','EMAIL_API_KEY':''}):
            self.assertFalse(email_service.is_configured())


if __name__=='__main__':
    unittest.main()

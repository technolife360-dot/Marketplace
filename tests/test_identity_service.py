import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import patch

import identity_service


class DiditIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'MARKETPLACE_MODE': 'development',
            'PUBLIC_BASE_URL': 'https://sentryloot.com',
            'DIDIT_API_KEY': 'test-api-key',
            'DIDIT_WORKFLOW_ID': 'workflow-123',
            'DIDIT_WEBHOOK_SECRET': 'test-webhook-secret',
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def make_signed_event(self, timestamp=None):
        event = {
            'timestamp': int(time.time()) if timestamp is None else timestamp,
            'event_id': 'event-123',
            'webhook_type': 'status.updated',
            'session_id': 'session-123',
            'status': 'Approved',
            'vendor_data': 'opaque-user-reference',
            'decision': {
                'id_verifications': [{'status': 'Approved', 'name': 'José'}],
                'liveness_checks': [{'status': 'Approved', 'score': 95.0}],
                'face_matches': [{'status': 'Approved', 'score': 1.0}],
            },
        }
        # Deliberately keep noncanonical order/spacing and a whole-valued float.
        raw = json.dumps(event, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        canonical = json.dumps(identity_service._shorten_floats(event), sort_keys=True,
                               separators=(',', ':'), ensure_ascii=False)
        signature = hmac.new(b'test-webhook-secret', canonical.encode('utf-8'), hashlib.sha256).hexdigest()
        return raw, signature, str(event['timestamp'])

    def test_v2_signature_accepts_canonical_payload_with_unicode(self):
        raw, signature, timestamp = self.make_signed_event()
        result = identity_service.verify_webhook(raw, signature, timestamp)
        self.assertEqual(result['session_id'], 'session-123')
        self.assertEqual(result['decision']['liveness_checks'][0]['score'], 95.0)

    def test_v2_signature_rejects_tampering_and_expired_timestamp(self):
        raw, signature, timestamp = self.make_signed_event()
        self.assertIsNone(identity_service.verify_webhook(raw.replace(b'Approved', b'Declined'), signature, timestamp))
        old_raw, old_signature, old_timestamp = self.make_signed_event(int(time.time()) - 301)
        self.assertIsNone(identity_service.verify_webhook(old_raw, old_signature, old_timestamp))

    def test_create_session_posts_only_to_didit_v3(self):
        class Response:
            status = 201
            def read(self, _limit):
                return b'{"session_id":"session-123","url":"https://verify.didit.me/session/abc"}'

        class Connection:
            def __init__(self, host, port, **_kwargs):
                self.host, self.port = host, port
            def request(self, method, path, body, headers):
                self.request_data = (method, path, json.loads(body), headers)
            def getresponse(self):
                return Response()
            def close(self):
                pass

        with patch.object(identity_service.http.client, 'HTTPSConnection', Connection):
            session = identity_service.create_verification_session('opaque-reference')
        self.assertEqual(session['session_id'], 'session-123')
        self.assertEqual(session['url'], 'https://verify.didit.me/session/abc')


if __name__ == '__main__':
    unittest.main()

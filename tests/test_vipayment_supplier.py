import hashlib
import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch, MagicMock

import vipayment_supplier as vip


class VIPaymentConnection(unittest.TestCase):
    def test_missing_keys_do_not_make_network_requests(self):
        with patch.dict(vip.os.environ, {'VIPAYMENT_API_ID': '', 'VIPAYMENT_API_KEY': ''}), patch.object(vip, 'urlopen') as network:
            with self.assertRaises(vip.SupplierError):vip.account_status()
            network.assert_not_called()

    def call(self, payload, operation='profile'):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps(payload).encode()
        with patch.dict(vip.os.environ, {'VIPAYMENT_API_ID': '42', 'VIPAYMENT_API_KEY': 'synthetic-secret'}), patch.object(vip, 'urlopen', return_value=response) as network:
            result=vip.account_status() if operation=='profile' else vip.catalog_services()
        return result,network.call_args.args[0]

    def test_authenticated_profile_uses_post_and_hides_private_balance_and_keys(self):
        result,request=self.call({'result':True,'data':{'username':'test-merchant','balance':50000,'full_name':'Private name','level':'Basic'}})
        self.assertTrue(result['connected'])
        self.assertFalse(result['orders_enabled'])
        self.assertEqual(request.full_url,'https://vip-reseller.co.id/api/profile')
        self.assertEqual(request.method,'POST')
        self.assertNotIn('synthetic-secret',request.full_url)
        self.assertNotIn('balance',result)
        self.assertNotIn('Private name',json.dumps(result))
        from urllib.parse import parse_qs
        body=parse_qs(request.data.decode())
        self.assertEqual(body['sign'],[hashlib.md5(b'42synthetic-secret').hexdigest()])

    def test_catalog_request_cannot_create_order(self):
        result,request=self.call({'result':True,'data':[{'code':'ML14','game':'Mobile Legends','name':'14 Diamonds','price':{'basic':3310},'status':'available','server':'1'}]},'catalog')
        self.assertEqual(result[0]['code'],'ML14')
        self.assertIn(b'type=services',request.data)
        self.assertNotIn(b'type=order',request.data)
        self.assertNotIn('key',result[0])

    def test_invalid_account_or_false_success_is_rejected(self):
        for payload in ({'result':False,'data':{}},{'result':'true','data':{'username':'x'}},{'result':True,'data':{}}):
            with self.assertRaises(vip.SupplierError):self.call(payload)

    def test_cloudflare_is_reported_without_upstream_secrets(self):
        error=HTTPError('https://vip-reseller.co.id/api/profile',403,'Forbidden',{},io.BytesIO(b'synthetic-secret'))
        with patch.dict(vip.os.environ,{'VIPAYMENT_API_ID':'42','VIPAYMENT_API_KEY':'synthetic-secret'}),patch.object(vip,'urlopen',side_effect=error):
            with self.assertRaises(vip.SupplierError) as raised:vip.account_status()
        self.assertIn('403',str(raised.exception))
        self.assertNotIn('synthetic-secret',str(raised.exception))

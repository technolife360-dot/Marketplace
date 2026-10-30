import json
import unittest
from unittest.mock import patch, MagicMock

import app
import seagm_supplier as supplier
from tests import test_marketplace as fixtures


class SupplierVerification(unittest.TestCase):
    def test_success_without_account_identity_is_not_authenticated(self):
        with patch.dict(supplier.os.environ, {'SEAGM_UID': '12345', 'SEAGM_SECRET_KEY': 'synthetic-key'}), patch.object(supplier, 'request', return_value={'code': 200, 'data': {}}):
            with self.assertRaises(supplier.SupplierError):
                supplier.account_status()

    def test_wrong_account_identity_is_not_authenticated(self):
        with patch.dict(supplier.os.environ, {'SEAGM_UID': '12345', 'SEAGM_SECRET_KEY': 'synthetic-key'}), patch.object(supplier, 'request', return_value={'code': 200, 'data': {'id': 67890}}):
            with self.assertRaises(supplier.SupplierError):
                supplier.account_status()

    def test_verified_account_excludes_credentials(self):
        with patch.dict(supplier.os.environ, {'SEAGM_UID': '12345', 'SEAGM_SECRET_KEY': 'synthetic-key', 'SEAGM_API_ENV': 'sandbox'}), patch.object(supplier, 'request', return_value={'code': 200, 'data': {'id': 12345, 'currency': 'MYR'}}):
            result = supplier.account_status()
        self.assertTrue(result['connected'])
        self.assertEqual(result['environment'], 'sandbox')
        self.assertNotIn('synthetic-key', json.dumps(result))

    def test_missing_success_code_cannot_pass_as_valid_api_response(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data":{"id":12345}}'
        with patch.dict(supplier.os.environ, {'SEAGM_UID': '12345', 'SEAGM_SECRET_KEY': 'synthetic-key'}), patch.object(supplier, 'urlopen', return_value=response):
            with self.assertRaises(supplier.SupplierError):
                supplier.request('/v1/me')


class SupplierAdminCheck(unittest.TestCase):
    setUp = fixtures.MarketplaceFlows.setUp
    tearDown = fixtures.MarketplaceFlows.tearDown
    ctx = fixtures.MarketplaceFlows.ctx
    route = fixtures.MarketplaceFlows.route

    def test_no_credentials_returns_configuration_error_instead_of_success(self):
        with patch.dict(app.os.environ, {'SEAGM_UID': '', 'SEAGM_SECRET_KEY': ''}):
            with self.assertRaises(app.HttpError) as raised:
                self.route(self.admin, 'POST', '/api/admin/top-up/supplier/check')
        self.assertEqual(raised.exception.status, 503)

    def test_verified_read_only_check_keeps_purchases_closed(self):
        with patch.object(supplier, 'account_status', return_value={'configured': True, 'connected': True, 'environment': 'sandbox'}):
            result = self.route(self.admin, 'POST', '/api/admin/top-up/supplier/check')
        self.assertTrue(result['ok'])
        self.assertFalse(result['orders_enabled'])


if __name__ == '__main__':
    unittest.main()

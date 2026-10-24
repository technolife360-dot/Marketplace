import os
import unittest
from unittest.mock import MagicMock, patch

import storage_r2


R2_ENV = {
    'R2_ACCOUNT_ID': 'a' * 32,
    'R2_ACCESS_KEY_ID': 'test-access-key',
    'R2_SECRET_ACCESS_KEY': 'test-secret-key',
    'R2_LISTING_BUCKET': 'sentryloot-listing-images',
    'R2_EVIDENCE_BUCKET': 'sentryloot-account-evidence',
    'R2_PUBLIC_BASE_URL': 'https://assets.gamestorehub.com',
}


class R2StorageTests(unittest.TestCase):
    def test_public_photo_deletion_is_restricted_to_application_object_urls(self):
        key='visitor-images/'+'a'*20+'/'+'b'*40+'.webp'
        client=MagicMock()
        with patch.dict(os.environ,R2_ENV),patch.object(storage_r2,'_client',return_value=client):
            storage_r2.delete_listing('https://assets.gamestorehub.com/'+key)
            for url in ('https://other.example.com/'+key,'https://assets.gamestorehub.com/site-assets/logo.png'):
                with self.assertRaises(ValueError): storage_r2.delete_listing(url)
        client.delete_object.assert_called_once_with(Bucket='sentryloot-listing-images',Key=key)

    def test_evidence_requires_a_separate_nonpublic_bucket_configuration(self):
        for changes in (
            {'R2_EVIDENCE_BUCKET': 'sentryloot-listing-images'},
            {'R2_PUBLIC_BASE_URL': 'https://preview.r2.dev'},
            {'R2_PUBLIC_BASE_URL': 'https://assets.gamestorehub.com:bad'},
            {'R2_SECRET_ACCESS_KEY': ''},
        ):
            with self.subTest(changes=changes), patch.dict(os.environ, R2_ENV | changes):
                self.assertFalse(storage_r2.is_configured())

    def test_uploads_use_distinct_buckets_and_private_links_expire(self):
        key = 'a' * 24 + '/' + 'b' * 48 + '.webp'
        client = MagicMock()
        client.generate_presigned_url.return_value = 'https://example.invalid/signed'
        with patch.dict(os.environ, R2_ENV), patch.object(storage_r2, '_client', return_value=client):
            storage_r2.check_evidence_bucket()
            storage_r2.put_evidence(key, b'image')
            self.assertEqual(storage_r2.evidence_url(key), 'https://example.invalid/signed')
            storage_r2.delete_evidence(key)
            self.assertEqual(storage_r2.put_listing(key, b'image'),
                             'https://assets.gamestorehub.com/visitor-images/' + key)
        client.head_bucket.assert_called_once_with(Bucket='sentryloot-account-evidence')
        client.put_object.assert_any_call(Bucket='sentryloot-account-evidence', Key=key,
                                          Body=b'image', ContentType='image/webp',
                                          CacheControl='private, no-store')
        client.put_object.assert_any_call(Bucket='sentryloot-listing-images', Key='visitor-images/' + key,
                                          Body=b'image', ContentType='image/webp',
                                          CacheControl='public, max-age=31536000, immutable')
        client.generate_presigned_url.assert_called_once_with(
            'get_object', Params={'Bucket': 'sentryloot-account-evidence', 'Key': key}, ExpiresIn=300)
        client.delete_object.assert_called_once_with(Bucket='sentryloot-account-evidence', Key=key)

    def test_admin_and_visitor_images_are_kept_separate(self):
        key = 'a' * 20 + '/' + 'b' * 40 + '.webp'
        client = MagicMock()
        with patch.dict(os.environ, R2_ENV), patch.object(storage_r2, '_client', return_value=client):
            url = storage_r2.put_listing(key, b'admin-image', audience='admin')
            self.assertEqual(url, 'https://assets.gamestorehub.com/admin-images/' + key)
            self.assertTrue(storage_r2.is_listing_url(url))
            self.assertTrue(storage_r2.is_listing_url('https://assets.gamestorehub.com/visitor-images/' + key))
            self.assertTrue(storage_r2.is_listing_url('https://assets.gamestorehub.com/' + key))
            self.assertFalse(storage_r2.is_listing_url('https://assets.gamestorehub.com/site-assets/logo.png'))
            with self.assertRaises(ValueError):
                storage_r2.put_listing(key, b'image', audience='../private')
            with self.assertRaises(ValueError):
                storage_r2.evidence_url('admin-images/' + key)
        self.assertEqual(client.put_object.call_args.kwargs['Key'], 'admin-images/' + key)

    def test_rejects_unexpected_object_paths(self):
        with patch.dict(os.environ, R2_ENV), patch.object(storage_r2, '_client') as client:
            with self.assertRaises(ValueError):
                storage_r2.evidence_url('../private.txt')
            client.assert_not_called()

    def test_listing_urls_must_use_the_configured_public_domain_and_object_key(self):
        key = 'a' * 20 + '/' + 'b' * 40 + '.webp'
        with patch.dict(os.environ, R2_ENV):
            self.assertTrue(storage_r2.is_listing_url('https://assets.gamestorehub.com/' + key))
            self.assertFalse(storage_r2.is_listing_url('https://other.example.com/' + key))
            self.assertFalse(storage_r2.is_listing_url('https://assets.gamestorehub.com/' + key + '?x=1'))
            self.assertFalse(storage_r2.is_listing_url('https://assets.gamestorehub.com/../private.webp'))

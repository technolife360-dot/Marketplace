"""Album persistence, authorization and all-attachment safety checks through WSGI."""
import unittest
from unittest.mock import patch
import app
import community
import community_moderation as automatic
from tests import test_community as community_tests


class CommunityAlbums(unittest.TestCase):
    setUp = community_tests.CommunityWorkflows.setUp
    tearDown = community_tests.CommunityWorkflows.tearDown
    signed_client = community_tests.CommunityWorkflows.signed_client
    req = community_tests.CommunityWorkflows.req
    post = community_tests.CommunityWorkflows.post
    profile = community_tests.CommunityWorkflows.profile
    image = community_tests.CommunityWorkflows.image

    def upload_images(self, count=3, client=None):
        client = client or self.seller
        ids = []
        for _ in range(count):
            status, media, _ = self.req(client, 'POST', '/media', raw=self.image(), content_type='image/png')
            self.assertEqual(status, 201, media)
            ids.append(media['id'])
        return ids

    def test_album_order_survives_edit_and_every_image_obeys_post_visibility(self):
        with patch.object(app.storage_r2, 'is_configured', return_value=False):
            ids = self.upload_images()
            post = self.post(self.seller, kind='moment', media_ids=ids)
            self.assertEqual(post['media_id'], ids[0])
            self.assertEqual([m['id'] for m in post['media']], ids)
            for mid in ids:
                self.assertEqual(self.req(self.guest, 'GET', '/media/'+mid)[0], 200)
            # An unrelated edit must preserve the full album, including order.
            status, edited, _ = self.req(self.seller, 'PATCH', '/posts/'+post['id'], {'title':'Edited album title','permission':True})
            self.assertEqual(status, 200, edited)
            self.assertEqual([m['id'] for m in edited['media']], ids)
            self.req(self.seller, 'PATCH', '/posts/'+post['id'], {'audience':'private','permission':True})
            for mid in ids:
                self.assertEqual(self.req(self.guest, 'GET', '/media/'+mid)[0], 404)
                self.assertEqual(self.req(self.seller, 'GET', '/media/'+mid)[0], 200)

    def test_album_rejects_duplicates_foreign_media_and_mixed_video(self):
        with patch.object(app.storage_r2, 'is_configured', return_value=False):
            ids = self.upload_images(2)
            foreign = self.upload_images(1, self.admin)[0]
            for attachments in ([ids[0], ids[0]], [ids[0], foreign], 'bad', [ids[0], {}]):
                status, _, _ = self.req(self.seller, 'POST', '/posts', {'kind':'moment','title':'Invalid album','game_slug':'pubg-mobile','media_ids':attachments})
                self.assertEqual(status, 400, attachments)
            # Existing, normalized videos may be the sole attachment only.
            self.db.execute("UPDATE community_media SET content_type='video/mp4' WHERE id=?", (ids[1],))
            for attachments in (ids, ids[::-1]):
                status, _, _ = self.req(self.seller, 'POST', '/posts', {'kind':'moment','title':'Mixed album','game_slug':'pubg-mobile','media_ids':attachments})
                self.assertEqual(status, 400)
            post = self.post(self.seller, kind='moment', media_ids=[ids[1]], status='draft')
            self.assertEqual(post['media_type'], 'video/mp4')
            self.assertEqual(len(post['media']), 1)

    def test_all_images_are_scanned_and_flagged_secondary_image_hides_the_album(self):
        with patch.object(app.storage_r2, 'is_configured', return_value=False):
            ids = self.upload_images()
            with patch.object(automatic, 'assess', return_value=automatic.Result('rejected', ('nudity',))) as assess:
                post = self.post(self.seller, kind='moment', media_ids=ids)
            self.assertEqual(assess.call_args.args[2], ids)
            self.assertEqual(post['status'], 'hidden')
            for mid in ids:
                self.assertEqual(self.req(self.guest, 'GET', '/media/'+mid)[0], 404)

    def test_cleanup_retains_secondary_images_then_releases_removed_ones(self):
        with patch.object(app.storage_r2, 'is_configured', return_value=False):
            ids = self.upload_images()
            post = self.post(self.seller, kind='moment', media_ids=ids, status='draft')
            self.db.execute("UPDATE community_media SET created_at='2020-01-01 00:00:00'")
            self.assertEqual(community.cleanup_media(self.db, vars(app)), 0)
            status, changed, _ = self.req(self.seller, 'PATCH', '/posts/'+post['id'], {'media_ids':[ids[2],ids[0]]})
            self.assertEqual(status, 200, changed)
            self.assertEqual([m['id'] for m in changed['media']], [ids[2],ids[0]])
            self.assertEqual(community.cleanup_media(self.db, vars(app)), 1)
            self.assertEqual(self.req(self.seller, 'GET', '/media/'+ids[1])[0], 404)
            community.erase(self.db, self.seller_id, vars(app))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_post_media').fetchone()[0], 0)

    def test_r2_video_and_album_urls_stay_behind_the_api(self):
        with patch.object(app.storage_r2,'is_configured',return_value=True), patch.object(app.storage_r2,'put_evidence'), patch.object(app.storage_r2,'read_evidence',return_value=self.image()), patch.object(app.storage_r2,'evidence_url',return_value='https://private.example/lease') as sign:
            ids=self.upload_images(2)
            post=self.post(self.seller,kind='moment',media_ids=ids)
            self.assertEqual([m['url'] for m in post['media']], ['/api/community/media/'+mid for mid in ids])
            for mid in ids:
                status,_,headers=self.req(self.guest,'GET','/media/'+mid)
                self.assertEqual(status,302)
                self.assertEqual(headers['Cache-Control'],'private, no-store')
            self.assertEqual(sign.call_count,2)


if __name__ == '__main__':
    unittest.main()

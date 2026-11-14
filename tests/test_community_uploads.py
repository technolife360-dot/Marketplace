"""Large media uses bounded requests and private staged storage, never raw URLs."""
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import imageio_ffmpeg
import app
import community
import community_uploads as uploads
import community_moderation as automatic
from tests import test_community as fixtures


class CommunityUploads(unittest.TestCase):
    setUp=fixtures.CommunityWorkflows.setUp
    tearDown=fixtures.CommunityWorkflows.tearDown
    signed_client=fixtures.CommunityWorkflows.signed_client
    req=fixtures.CommunityWorkflows.req
    image=fixtures.CommunityWorkflows.image
    post=fixtures.CommunityWorkflows.post

    def reserve(self,raw,mime='image/png',client=None):
        status,ticket,_=self.req(client or self.seller,'POST','/uploads',{'size':len(raw),'content_type':mime})
        self.assertEqual(status,201,ticket)
        return ticket

    def upload(self,raw,mime='image/png'):
        ticket=self.reserve(raw,mime)
        self.assertFalse(ticket['direct'])
        for offset in range(0,len(raw),3*1024*1024):
            status,part,_=self.req(self.seller,'POST','/uploads/'+ticket['id']+'/chunk?offset='+str(offset),raw=raw[offset:offset+3*1024*1024],content_type='application/octet-stream')
            self.assertEqual(status,200,part)
        status,result,_=self.req(self.seller,'POST','/uploads/'+ticket['id']+'/complete',{})
        self.assertEqual(status,200,result)
        return ticket,result

    def test_image_larger_than_four_mb_uses_chunks_then_normalizes_and_finalizes_once(self):
        raw=io.BytesIO();Image.frombytes('RGB',(1500,1500),os.urandom(1500*1500*3)).save(raw,format='PNG');raw=raw.getvalue()
        self.assertGreater(len(raw),4*1024*1024)
        with patch.object(app.storage_r2,'is_configured',return_value=False):
            ticket,media=self.upload(raw)
            self.assertEqual(media['content_type'],'image/webp')
            status,repeated,_=self.req(self.seller,'POST','/uploads/'+ticket['id']+'/complete',{})
            self.assertEqual(status,200);self.assertEqual(repeated,media)
            row=self.db.execute('SELECT * FROM community_media WHERE id=?',(media['id'],)).fetchone()
            with Image.open(community.disk_path(vars(app),row['object_key'])) as image:
                self.assertEqual(image.format,'WEBP')
                self.assertLessEqual(max(image.size),1600)
            self.assertFalse(uploads.staging_path(vars(app),self.db.execute('SELECT object_key FROM community_uploads WHERE id=?',(ticket['id'],)).fetchone()['object_key']).exists())

    def test_staged_uploads_enforce_ownership_offsets_csrf_and_server_format_validation(self):
        with patch.object(app.storage_r2,'is_configured',return_value=False):
            ticket=self.reserve(b'not an image')
            endpoint='/uploads/'+ticket['id']
            self.assertEqual(self.req(self.admin,'POST',endpoint+'/complete',{})[0],404)
            self.assertEqual(self.req(self.seller,'POST',endpoint+'/complete',{})[0],409)
            self.assertEqual(self.req(self.seller,'POST',endpoint+'/chunk?offset=2',raw=b'123',content_type='application/octet-stream')[0],409)
            self.assertEqual(self.req(self.seller,'POST',endpoint+'/chunk?offset=0',raw=b'not an image',content_type='application/octet-stream')[0],200)
            self.assertEqual(self.req(self.seller,'POST',endpoint+'/complete',{})[0],400)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_media').fetchone()[0],0)
            self.assertEqual(self.req(self.guest,'POST','/uploads',{'size':10,'content_type':'image/png'})[0],401)
            self.assertEqual(self.req(self.seller,'POST','/uploads',{'size':10,'content_type':'text/html'})[0],415)
            self.assertEqual(self.req(self.seller,'POST','/uploads',{'size':True,'content_type':'image/png'})[0],400)

    def test_r2_ticket_uses_exact_size_and_does_not_publish_or_expose_raw_staging(self):
        body=self.image()
        with patch.object(app.storage_r2,'is_configured',return_value=True),patch.object(app.storage_r2,'evidence_upload_url',return_value='https://private.example/upload') as sign,patch.object(app.storage_r2,'download_evidence',side_effect=lambda key,path,size:path.write_bytes(body)),patch.object(app.storage_r2,'put_private_media') as put,patch.object(app.storage_r2,'delete_evidence') as delete:
            ticket=self.reserve(body)
            self.assertTrue(ticket['direct']);self.assertEqual(sign.call_args.args[1],len(body))
            self.assertEqual(self.req(self.seller,'GET','/media/'+ticket['id'])[0],404)
            status,media,_=self.req(self.seller,'POST','/uploads/'+ticket['id']+'/complete',{})
            self.assertEqual(status,200,media);put.assert_called_once();delete.assert_called_once()
            self.assertNotEqual(sign.call_args.args[0],put.call_args.args[0])
            self.assertEqual(media['url'],'/api/community/media/'+media['id'])

    def test_video_longer_than_thirty_seconds_is_not_truncated_and_every_segment_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'long.mp4'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=blue:s=160x120:r=5:d=34','-c:v','libx264','-pix_fmt','yuv420p','-y',str(source)],capture_output=True,check=True,timeout=10)
            with patch.object(app.storage_r2,'is_configured',return_value=False):
                _,media=self.upload(source.read_bytes(),'video/mp4')
                row=self.db.execute('SELECT duration FROM community_media_checks WHERE media_id=?',(media['id'],)).fetchone()
                self.assertGreater(row['duration'],30)
                payload={'title':'Long video test','body':'','permission':True}
                with patch.object(automatic,'classify',side_effect=[automatic.Result('approved'),automatic.Result('approved'),automatic.Result('rejected',('violence',))]) as classify:
                    results=[self.req(self.seller,'POST','/media/'+media['id']+'/check',payload) for _ in range(3)]
                self.assertTrue(all(result[0]==200 for result in results),results)
                self.assertFalse(results[0][1]['done']);self.assertFalse(results[1][1]['done'])
                self.assertEqual(results[2][1]['state'],'rejected');self.assertEqual(classify.call_count,3)
                post=self.post(self.seller,kind='moment',media_ids=[media['id']],title='Long video test',body='')
                self.assertEqual(post['status'],'hidden')
                self.assertEqual(self.req(self.guest,'GET','/media/'+media['id'])[0],404)
                # An edited caption must invalidate the cached decision.
                self.assertEqual(self.req(self.seller,'POST','/posts',{'kind':'moment','title':'Changed context','game_slug':'pubg-mobile','media_ids':[media['id']],'status':'published','permission':True})[0],503)

                # If the scanner fails during a new check, the UI can queue the video privately.
                with patch.object(automatic,'classify',side_effect=automatic.Unavailable(automatic.UNAVAILABLE)):
                    status, failure, _ = self.req(self.seller,'POST','/media/'+media['id']+'/check',{**payload,'title':'Changed context'})
                self.assertEqual(status,503)
                self.assertEqual(failure['fields']['code'],'community_safety_unavailable')
                status, queued, _ = self.req(self.seller,'POST','/posts',{
                    **payload,'kind':'moment','title':'Changed context','game_slug':'pubg-mobile',
                    'media_ids':[media['id']],'status':'published','queue_for_review':True,
                })
                self.assertEqual(status,201,queued)
                self.assertEqual((queued['status'],queued['review_status']),('draft','pending'))
                self.assertEqual(self.req(self.guest,'GET','/media/'+media['id'])[0],404)

    def test_r2_processing_refuses_disk_exhaustion_without_exposing_or_losing_staged_media(self):
        from types import SimpleNamespace
        with patch.object(app.storage_r2,'is_configured',return_value=True),patch.object(app.storage_r2,'evidence_upload_url',return_value='https://private.example/upload'),patch.object(app.storage_r2,'download_evidence') as download:
            ticket=self.reserve(self.image())
            with patch.object(uploads.shutil,'disk_usage',return_value=SimpleNamespace(free=0)):
                status,_,_=self.req(self.seller,'POST','/uploads/'+ticket['id']+'/complete',{})
            self.assertEqual(status,503);download.assert_not_called()
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_media').fetchone()[0],0)
            row=self.db.execute('SELECT state,claim_until FROM community_uploads WHERE id=?',(ticket['id'],)).fetchone()
            self.assertEqual((row['state'],row['claim_until']),('uploading',0))

    def test_expired_abandoned_upload_is_cleaned_without_touching_attached_media(self):
        with patch.object(app.storage_r2,'is_configured',return_value=False):
            ticket=self.reserve(self.image())
            self.req(self.seller,'POST','/uploads/'+ticket['id']+'/chunk?offset=0',raw=self.image(),content_type='application/octet-stream')
            row=self.db.execute('SELECT object_key FROM community_uploads WHERE id=?',(ticket['id'],)).fetchone()
            self.db.execute('UPDATE community_uploads SET expires_at=0')
            self.assertEqual(uploads.cleanup(self.db,vars(app)),1)
            self.assertFalse(uploads.staging_path(vars(app),row['object_key']).exists())

if __name__=='__main__':unittest.main()

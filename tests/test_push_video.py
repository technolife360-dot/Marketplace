import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import web_push
import video_evidence
from tests import test_marketplace as fixtures
from tests import test_trade_workflows as trade_fixtures

class PushAndVideo(unittest.TestCase):
    setUp=fixtures.MarketplaceFlows.setUp
    tearDown=fixtures.MarketplaceFlows.tearDown
    ctx=fixtures.MarketplaceFlows.ctx
    route=fixtures.MarketplaceFlows.route

    def subscription(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        public=ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)
        return {'endpoint':'https://fcm.googleapis.com/fcm/send/local-test-device','keys':{'auth':web_push.b64(b'0123456789abcdef'),'p256dh':web_push.b64(public)}}

    def test_push_consent_endpoint_validation_and_encrypted_account_storage(self):
        sub=self.subscription()
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/push/subscriptions',{'subscription':sub})
        for endpoint in ('http://127.0.0.1/private','https://localhost/secret','https://fcm.googleapis.com.attacker.invalid/fcm/send/test'):
            with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/push/subscriptions',{'consent':True,'subscription':{**sub,'endpoint':endpoint}})
        key=self.route(self.buyer,'POST','/api/push/setup',{})
        self.assertEqual(len(web_push.decode(key['public_key'])),65)
        self.route(self.buyer,'POST','/api/push/subscriptions',{'consent':True,'subscription':sub})
        raw=self.db.execute('SELECT settings_json FROM experience_preferences WHERE user_id=?',(self.buyer,)).fetchone()['settings_json']
        self.assertNotIn(sub['endpoint'],raw);self.assertNotIn(sub['keys']['auth'],raw)
        self.assertNotIn('push_devices',self.route(self.buyer,'GET','/api/experience/settings'))
        self.assertNotIn('push_devices',self.route(self.other,'GET','/api/experience/settings'))

    def test_push_dispatch_is_private_deduplicated_and_unsubscribe_is_owned(self):
        sub=self.subscription();self.route(self.buyer,'POST','/api/push/setup',{})
        self.route(self.buyer,'POST','/api/push/subscriptions',{'consent':True,'subscription':sub})
        app.notify(self.db,self.buyer,'message','Private chat title','Private chat contents','/conversation/private')
        with patch('pywebpush.webpush') as send:
            result=web_push.dispatch(self.db,vars(app),send=send)
            self.assertEqual(result['sent'],1)
            payload=send.call_args.kwargs['data']
            self.assertNotIn('Private chat',payload);self.assertNotIn('/conversation/',payload)
            self.assertEqual(web_push.dispatch(self.db,vars(app),send=send)['sent'],0)
        self.route(self.other,'DELETE','/api/push/subscriptions',{'endpoint':sub['endpoint']})
        app.notify(self.db,self.buyer,'message','Another title','Another body')
        with patch('pywebpush.webpush') as send:self.assertEqual(web_push.dispatch(self.db,vars(app),send=send)['sent'],1)
        self.route(self.buyer,'DELETE','/api/push/subscriptions',{'endpoint':sub['endpoint']})
        app.notify(self.db,self.buyer,'message','After unsubscribe','Not sent')
        with patch('pywebpush.webpush') as send:self.assertEqual(web_push.dispatch(self.db,vars(app),send=send)['sent'],0)

    def test_dispatch_token_is_scoped_and_never_uses_raw_cron_secret(self):
        with patch.dict(os.environ,{'PUSH_DISPATCH_TOKEN':'scoped-only-token-'*3,'CRON_SECRET':'original-cron-secret-'*3}):
            self.assertEqual(web_push.token(),'scoped-only-token-'*3)
            self.handler.headers={'Authorization':'Bearer '+os.environ['CRON_SECRET']}
            with self.assertRaises(app.HttpError):self.route(None,'POST','/api/cron/push-delivery',{})
            self.handler.headers={'Authorization':'Bearer '+web_push.token()}
            with patch.object(web_push,'dispatch',return_value={'sent':0,'failed':0}) as dispatch:
                self.assertEqual(self.route(None,'POST','/api/cron/push-delivery',{})['sent'],0)
                dispatch.assert_called_once()

    def test_video_normalizer_decodes_real_mp4_and_rejects_disguised_files(self):
        import imageio_ffmpeg
        for raw in (b'<html>not video</html>',b'\0'*50,b'0'* (video_evidence.MAX_BYTES+1)):
            with self.assertRaises(video_evidence.InvalidVideo):video_evidence.normalize(raw)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'input.mp4'
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=blue:s=320x240:d=1','-metadata','title=secret-camera-metadata','-c:v','libx264','-pix_fmt','yuv420p','-y',str(path)],capture_output=True,check=True,timeout=5)
            result=video_evidence.normalize(path.read_bytes())
            self.assertEqual(result[4:8],b'ftyp');self.assertNotIn(b'secret-camera-metadata',result)

    def test_video_evidence_is_only_visible_to_uploader_and_admin(self):
        oid,iid=trade_fixtures.TradeWorkflows.order(self,qty=1,typ='service')
        self.route(self.buyer,'POST','/api/orders/'+oid+'/dispute',{'details':'The delivered service is not the agreed result.'})
        self.handler.headers={'Content-Type':'video/mp4'}
        with patch.object(video_evidence,'normalize',return_value=b'normalized-video'),patch.object(app,'require_private_evidence_bucket'),patch.object(app.storage_r2,'put_video_evidence') as put:
            response=self.handler.route(self.db,self.ctx(self.buyer),'POST','/api/disputes/'+oid+'/videos',{}, {},b'video-upload')
            self.assertEqual(response[0],201);self.assertEqual(put.call_args.args[1],b'normalized-video')
        with patch.object(app.storage_r2,'evidence_url',return_value='https://private.invalid/signed'):
            own=self.route(self.buyer,'GET','/api/disputes/'+oid)['entries']
            self.assertEqual(own[-1]['media_type'],'video')
            seller=self.route(self.seller,'GET','/api/disputes/'+oid)['entries']
            self.assertNotIn('image_url',seller[-1]);self.assertTrue(seller[-1]['image_private'])
            with self.assertRaises(app.HttpError):self.route(self.other,'GET','/api/disputes/'+oid)

if __name__=='__main__':unittest.main()

"""Review, rights-request and signed-video security at the WSGI boundary."""
import base64
import json
import os
import unittest
from unittest.mock import patch
import app
import community_video as video
from tests import test_http_workflows as workflow
from tests import test_community as communityTests

class CommunitySafety(unittest.TestCase):
    setUp=workflow.HTTPWorkflows.setUp
    tearDown=workflow.HTTPWorkflows.tearDown
    signed_client=workflow.HTTPWorkflows.signed_client
    req=communityTests.CommunityWorkflows.req
    profile=communityTests.CommunityWorkflows.profile
    post=communityTests.CommunityWorkflows.post
    image=communityTests.CommunityWorkflows.image

    def pending(self,**changes):
        result=self.req(self.seller,'POST','/posts',{'kind':'achievement','title':'A real milestone','game_slug':'pubg-mobile','status':'published','permission':True,**changes})
        self.assertEqual(result[0],201,result[1]);return result[1]
    def inspect(self,pid):
        status,p,_=self.admin.request('GET','/api/admin/community/review/'+pid)
        self.assertEqual(status,200,p);return p
    def decide(self,pid,token,decision='approved'):
        return self.admin.request('POST','/api/admin/community/review/'+pid,{'decision':decision,'note':'Reviewed this submission carefully.','review_token':token})
    def case(self,client,**changes):
        headers=changes.pop('headers',None)
        return self.req(client,'POST','/cases',{'kind':'copyright','post_id':'unavailable-private-post','name':'Rights holder','email':'rights@example.test','reference':'Original work at https://example.test/original','body':'I own this work and request a review of its use.','attestation':True,**changes},headers=headers)
    def test_publication_is_reviewed_and_stale_reviews_cannot_approve_edits(self):
        p=self.pending();pid=p['id']
        self.assertEqual((p['status'],p['review_status']),('draft','pending'))
        self.assertEqual(self.req(self.guest,'GET','/posts')[1]['posts'],[])
        self.assertEqual(self.req(self.guest,'GET','/posts/'+pid)[0],404)
        self.assertEqual(self.seller.request('GET','/api/admin/community/queue')[0],403)
        first=self.inspect(pid)
        self.assertEqual(self.req(self.seller,'PATCH','/posts/'+pid,{'title':'Changed after review opened','status':'published','permission':True})[0],200)
        self.assertEqual(self.decide(pid,first['review_token'])[0],409)
        second=self.inspect(pid);self.assertNotEqual(first['review_token'],second['review_token'])
        self.assertEqual(self.decide(pid,second['review_token'])[0],200)
        self.assertEqual(self.decide(pid,second['review_token'])[0],409)
        self.assertEqual(self.req(self.guest,'GET','/posts/'+pid)[1]['title'],'Changed after review opened')
        self.req(self.seller,'PATCH','/posts/'+pid,{'body':'Another edit','status':'published','permission':True})
        self.assertEqual(self.req(self.guest,'GET','/posts/'+pid)[0],404)
    def test_pending_media_is_private_and_admin_review_requires_explicit_authorization(self):
        with patch.object(app.storage_r2,'is_configured',return_value=False):
            status,m,_=self.req(self.seller,'POST','/media',raw=self.image(),content_type='image/png')
            self.assertEqual(status,201,m);p=self.pending(kind='moment',media_id=m['id'])
            self.assertEqual(self.req(self.guest,'GET','/media/'+m['id'])[0],404)
            self.assertEqual(self.req(self.seller,'GET','/media/'+m['id']+'?review=1')[0],403)
            self.assertEqual(self.req(self.admin,'GET','/media/'+m['id'])[0],404)
            self.assertEqual(self.req(self.admin,'GET','/media/'+m['id']+'?review=1')[0],200)
            self.assertTrue(self.inspect(p['id'])['media_url'].endswith('?review=1'))
    def test_rights_cases_are_public_to_submit_but_private_to_read(self):
        self.assertEqual(self.case(self.guest,attestation=False)[0],400)
        self.assertEqual(self.case(self.guest,headers={'Origin':'https://evil.test','Host':'sentryloot.test'})[0],403)
        # Different rate subjects keep the anti-spam quota independent from the checks above.
        first=self.case(self.seller);self.assertEqual(first[0],201,first[1])
        second=self.case(self.seller);self.assertEqual(second[1]['id'],first[1]['id'])
        self.assertEqual(self.guest.request('GET','/api/admin/community/queue')[0],401)
        own=self.req(self.seller,'GET','/submissions')[1]['cases'];self.assertEqual(len(own),1)
        self.assertEqual(self.req(self.admin,'GET','/submissions')[1]['cases'],[])
        queued=self.admin.request('GET','/api/admin/community/queue')[1]['cases']
        self.assertEqual(queued[0]['email'],'rights@example.test')
        decision={'action':'resolve','decision':'No matching post was available for review.'}
        endpoint='/api/admin/community/cases/'+first[1]['id']
        self.assertEqual(self.admin.request('POST',endpoint,decision)[0],200)
        self.assertEqual(self.admin.request('POST',endpoint,decision)[0],409)
    def test_author_appeal_is_reviewed_again_and_hidden_post_can_be_deleted_by_owner(self):
        p=self.pending();pid=p['id'];token=self.inspect(pid)['review_token']
        self.assertEqual(self.decide(pid,token,'rejected')[0],200)
        self.assertEqual(self.case(self.admin,kind='appeal',post_id=pid)[0],400)
        case=self.case(self.seller,kind='appeal',post_id=pid);self.assertEqual(case[0],201)
        self.assertEqual(self.admin.request('POST','/api/admin/community/cases/'+case[1]['id'],{'action':'reconsider','decision':'Please review this post again.'})[0],200)
        self.assertEqual(self.req(self.guest,'GET','/posts/'+pid)[0],404)
        self.assertEqual(self.decide(pid,self.inspect(pid)['review_token'],'rejected')[0],200)
        self.assertEqual(self.req(self.admin,'DELETE','/posts/'+pid)[0],404)
        self.assertEqual(self.req(self.seller,'DELETE','/posts/'+pid)[0],200)
        self.assertIsNone(self.db.execute('SELECT id FROM community_posts WHERE id=?',(pid,)).fetchone())
    def test_country_is_opt_in_and_private_case_contacts_never_enter_profile(self):
        self.profile(self.seller)
        self.db.execute("UPDATE users SET country='MY' WHERE id=?",(self.seller_id,))
        profile=self.req(self.guest,'GET','/profiles/'+self.seller_id)[1];self.assertEqual(profile['country'],'')
        self.profile(self.seller,preferences={'show_country':True})
        profile=self.req(self.guest,'GET','/profiles/'+self.seller_id)[1];self.assertEqual(profile['country'],'MY');self.assertNotIn('email',profile)
    def test_stream_upload_owner_processing_and_signed_playback(self):
        remote='a'*32
        with patch.object(video,'configured',return_value=True),patch.object(video,'reserve',return_value=(remote,'https://upload.videodelivery.net/ticket')):
            status,m,_=self.req(self.seller,'POST','/video-upload',{'size':8000000});self.assertEqual(status,201,m)
        mid=m['id'];self.assertEqual(self.req(self.admin,'GET','/video-upload/'+mid)[0],404)
        with patch.object(video,'details',return_value={'readyToStream':True,'requireSignedURLs':False,'duration':20}):
            self.assertEqual(self.req(self.seller,'GET','/video-upload/'+mid)[1]['state'],'processing')
        attempted=self.req(self.seller,'POST','/posts',{'kind':'moment','title':'A real gameplay clip','media_id':mid,'game_slug':'pubg-mobile','status':'published','permission':True})
        self.assertEqual(attempted[0],409,attempted[1])
        with patch.object(video,'details',return_value={'readyToStream':True,'requireSignedURLs':True,'duration':20}):
            self.assertEqual(self.req(self.seller,'GET','/video-upload/'+mid)[1]['state'],'ready')
        p=self.pending(kind='moment',media_id=mid)
        self.assertEqual(self.req(self.guest,'GET','/media/'+mid)[0],404)
        self.assertEqual(self.decide(p['id'],self.inspect(p['id'])['review_token'])[0],200)
        with patch.object(video,'playback',return_value='https://iframe.videodelivery.net/signed.token.value'):
            result=self.req(self.guest,'GET','/media/'+mid);self.assertEqual(result[0],200,result[1]);self.assertEqual(result[1]['expires_in'],300)
        self.profile(self.seller,visibility='private')
        self.assertEqual(self.req(self.guest,'GET','/media/'+mid)[0],404)

class StreamSigning(unittest.TestCase):
    def test_local_token_signature_is_valid_short_lived_and_contains_no_credentials(self):
        from cryptography.hazmat.primitives.asymmetric import rsa,padding
        from cryptography.hazmat.primitives import serialization,hashes
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        pem=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
        env={'CF_STREAM_ACCOUNT_ID':'a'*32,'CF_STREAM_API_TOKEN':'server-only-token','CF_STREAM_SIGNING_KEY_ID':'key-id','CF_STREAM_SIGNING_KEY_PEM':base64.b64encode(pem).decode()}
        decode=lambda v:base64.urlsafe_b64decode(v+'='*(-len(v)%4))
        with patch.dict(os.environ,env),patch.object(video.time,'time',return_value=1000):url=video.playback('b'*32)
        header,payload,signature=url.rsplit('/',1)[1].split('.')
        key.public_key().verify(decode(signature),(header+'.'+payload).encode(),padding.PKCS1v15(),hashes.SHA256())
        self.assertEqual(json.loads(decode(payload)),{'sub':'b'*32,'kid':'key-id','exp':1300})
        self.assertNotIn('server-only-token',url)
    def test_tus_reservation_requires_official_upload_host_and_private_metadata(self):
        with patch.object(video,'request',return_value=({}, {'stream-media-id':'a'*32,'Location':'https://upload.videodelivery.net/ticket'})) as call:
            self.assertEqual(video.reserve(9000000,'owner')[0],'a'*32)
            headers=call.call_args.kwargs['headers'];self.assertIn('requiresignedurls',headers['Upload-Metadata']);self.assertEqual(headers['Upload-Length'],'9000000')
        for url in ('https://evil.test/ticket','https://upload.videodelivery.net:bad/ticket','http://upload.videodelivery.net/ticket'):
            with patch.object(video,'request',return_value=({}, {'stream-media-id':'a'*32,'Location':url})),self.assertRaises(video.Unavailable):video.reserve(9000000,'owner')

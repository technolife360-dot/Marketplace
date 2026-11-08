"""Real WSGI/SQLite tests for community isolation, persistence and moderation."""
import io
import unittest
from unittest.mock import patch
import app
import community_moderation as automatic
from tests import test_http_workflows as workflow

class CommunityWorkflows(unittest.TestCase):
    def setUp(self):
        workflow.HTTPWorkflows.setUp(self)
        for dependency,value in (('configured',True),('classify',automatic.Result('approved'))):
            patcher=patch.object(automatic,dependency,return_value=value)
            patcher.start();self.addCleanup(patcher.stop)
    tearDown=workflow.HTTPWorkflows.tearDown
    signed_client=workflow.HTTPWorkflows.signed_client

    def req(self,client,method,path,data=None,**kw):
        return client.request(method,'/api/community'+path,data,**kw)

    def profile(self,client,**data):
        status,p,_=self.req(client,'PATCH','/profile',data)
        self.assertEqual(status,200,p);return p

    def post(self,client,**data):
        body={'kind':'achievement','title':'My first milestone','body':'A real player achievement.','game_slug':'pubg-mobile','status':'published','permission':True,**data}
        status,p,_=self.req(client,'POST','/posts',body)
        self.assertEqual(status,201,p)
        if body['status']=='published' and p['review_status']=='pending':
            status,result,_=self.admin.request('POST','/api/admin/community/review/'+p['id'],{'decision':'approved','note':'Reviewed test content.','review_token':self.admin.request('GET','/api/admin/community/review/'+p['id'])[1]['review_token']})
            self.assertEqual(status,200,result)
            p=self.req(client,'GET','/posts/'+p['id'])[1]
        return p

    def test_guest_reads_real_empty_feed_and_cannot_write(self):
        status,p,_=self.req(self.guest,'GET','/posts');self.assertEqual(status,200);self.assertEqual(p['posts'],[])
        self.assertEqual(self.req(self.guest,'POST','/posts',{})[0],401)
        self.assertEqual(self.req(self.guest,'GET','/notifications')[0],401)
        status,body,headers=self.guest.request('GET','/community')
        self.assertEqual(status,200);self.assertIn(b'community.js',body);self.assertEqual(headers['X-Frame-Options'],'DENY')

    def test_profile_post_save_comment_and_notifications_survive_reload(self):
        self.profile(self.seller,handle='gamer-one',bio='Collection and moments')
        self.profile(self.admin,handle='gamer-two')
        p=self.post(self.seller);pid=p['id']
        self.assertEqual(self.req(self.admin,'POST','/profiles/'+self.seller_id+'/follow',{'enabled':True})[0],200)
        self.assertEqual(len(self.req(self.admin,'GET','/posts?mode=following')[1]['posts']),1)
        for action in ('like','save'):
            self.assertEqual(self.req(self.admin,'POST','/posts/'+pid+'/'+action,{'enabled':True,'folder':'Clutches'})[0],200)
        # Setting desired state is idempotent, including notification delivery.
        self.req(self.admin,'POST','/posts/'+pid+'/like',{'enabled':True})
        self.assertEqual(self.req(self.admin,'POST','/posts/'+pid+'/comments',{'body':'Great moment!'})[0],201)
        after=self.req(self.admin,'GET','/posts/'+pid)[1]
        self.assertEqual(after['reactions'],1);self.assertEqual(after['comments'],1);self.assertTrue(after['saved'])
        self.assertEqual(self.req(self.admin,'GET','/folders')[1]['folders'],['Clutches'])
        self.assertEqual(len(self.req(self.admin,'GET','/posts?mode=saved')[1]['posts']),1)
        events=self.req(self.seller,'GET','/notifications')[1]['notifications'];self.assertEqual(len(events),3)
        self.req(self.seller,'POST','/notifications/read',{})
        self.assertTrue(all(n['seen'] for n in self.req(self.seller,'GET','/notifications')[1]['notifications']))
        self.assertNotIn('email',after['author'])
        self.assertEqual(self.req(self.admin,'DELETE','/posts/'+pid)[0],403)
        self.assertEqual(self.req(self.admin,'PATCH','/posts/'+pid,{'title':'Stolen post'})[0],403)
        self.assertEqual(self.req(self.seller,'POST','/posts/'+pid+'/like',{'enabled':'true'})[0],400)

    def test_private_drafts_and_followers_posts_do_not_leak_via_search_saved_or_media(self):
        self.profile(self.seller,handle='privacy-owner');self.profile(self.admin,handle='other-player')
        draft=self.post(self.seller,status='draft');private=self.post(self.seller,audience='private');followers=self.post(self.seller,audience='followers')
        for p in (draft,private,followers):self.assertEqual(self.req(self.guest,'GET','/posts/'+p['id'])[0],404)
        self.assertEqual(self.req(self.admin,'GET','/posts?q=milestone')[1]['posts'],[])
        self.req(self.admin,'POST','/profiles/'+self.seller_id+'/follow',{'enabled':True})
        self.assertEqual(self.req(self.admin,'GET','/posts/'+followers['id'])[0],200)
        self.req(self.admin,'POST','/posts/'+followers['id']+'/save',{'enabled':True})
        self.profile(self.seller,visibility='private')
        self.assertEqual(self.req(self.admin,'GET','/posts?mode=saved')[1]['posts'],[])
        self.assertEqual(self.req(self.admin,'GET','/folders')[1]['folders'],[])
        self.assertEqual(self.req(self.admin,'GET','/profiles/'+self.seller_id)[0],404)
        self.assertEqual(len(self.req(self.seller,'GET','/posts?mode=drafts')[1]['posts']),1)
        self.assertEqual(self.req(self.admin,'GET','/posts?mode=drafts')[1]['posts'],[])

    def test_block_removes_connections_and_hides_both_directions(self):
        self.profile(self.seller,handle='first-player');self.profile(self.admin,handle='second-player')
        p=self.post(self.seller)
        self.req(self.admin,'POST','/profiles/'+self.seller_id+'/follow',{'enabled':True})
        self.req(self.seller,'POST','/profiles/'+self.admin_id+'/block',{'enabled':True})
        self.assertEqual(self.req(self.admin,'GET','/posts/'+p['id'])[0],404)
        self.assertEqual(self.req(self.admin,'POST','/posts/'+p['id']+'/comments',{'body':'blocked'})[0],404)
        self.assertEqual(self.req(self.admin,'GET','/profiles/'+self.seller_id)[0],404)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_follows').fetchone()[0],0)
        self.assertEqual(len(self.req(self.seller,'GET','/blocks')[1]['players']),1)
        self.req(self.seller,'POST','/profiles/'+self.admin_id+'/block',{'enabled':False})
        self.assertEqual(self.req(self.admin,'GET','/posts/'+p['id'])[0],200)

    def test_csrf_verified_account_permissions_and_input_validation(self):
        self.assertEqual(self.req(self.seller,'PATCH','/profile',{},csrf=False)[0],403)
        self.db.execute('UPDATE users SET email_verified=0 WHERE id=?',(self.seller_id,))
        self.assertEqual(self.req(self.seller,'PATCH','/profile',{})[0],403)
        self.db.execute('UPDATE users SET email_verified=1 WHERE id=?',(self.seller_id,))
        self.profile(self.seller,handle='valid-handle')
        self.assertEqual(self.req(self.admin,'PATCH','/profile',{'handle':'valid-handle'})[0],409)
        self.assertEqual(self.req(self.seller,'PATCH','/profile',{'handle':'../../no'})[0],400)
        self.assertEqual(self.req(self.seller,'PATCH','/profile',{'visibility':'invalid'})[0],400)
        self.assertEqual(self.req(self.seller,'POST','/posts',{'title':'Bad','game_slug':'pubg-mobile','status':'published'})[0],400)
        self.assertEqual(self.req(self.seller,'PATCH','/profile',{'preferences':{'games':['unknown-game']}})[0],400)

    def image(self):
        from PIL import Image
        out=io.BytesIO();Image.new('RGB',(64,48),(210,150,80)).save(out,'PNG');return out.getvalue()

    def test_home_and_community_share_canonical_avatar_and_name(self):
        avatar='https://images.example.com/shared-account.webp'
        with patch.object(app.storage_r2,'is_configured',return_value=True),patch.object(app.storage_r2,'put_listing',return_value=avatar):
            status,result,_=self.seller.request('POST','/api/profile/avatar',raw=self.image(),content_type='image/png')
            self.assertEqual(status,201,result)
        self.profile(self.seller,display_name='Shared Player',handle='shared-player')
        home=self.seller.request('GET','/api/me')[1]['user']
        community=self.req(self.seller,'GET','/meta')[1]
        for field in ('id','display_name','avatar_url','seller','email_verified'):
            self.assertEqual(home[field],community['user'][field])
        self.assertEqual(community['profile']['avatar_url'],avatar)
        status,result,_=self.seller.request('POST','/api/profile',{'display_name':'Updated at Home'})
        self.assertEqual(status,200,result)
        profile=self.req(self.seller,'GET','/profiles/'+self.seller_id)[1]
        self.assertEqual(profile['display_name'],'Updated at Home')
        self.assertEqual(profile['avatar_url'],avatar)
        other=self.req(self.admin,'GET','/meta')[1]['user']
        self.assertNotEqual(other['avatar_url'],avatar)

    def test_real_image_upload_private_access_range_and_ownership(self):
        with patch.object(app.storage_r2,'is_configured',return_value=False):
            status,m,_=self.req(self.seller,'POST','/media',raw=self.image(),content_type='image/png')
            self.assertEqual(status,201,m);mid=m['id']
            self.assertEqual(self.req(self.guest,'GET','/media/'+mid)[0],404)
            status,body,headers=self.req(self.seller,'GET','/media/'+mid)
            self.assertEqual(status,200);self.assertEqual(headers['Content-Type'],'image/webp');self.assertEqual(body[:4],b'RIFF')
            status,part,h=self.req(self.seller,'GET','/media/'+mid,headers={'Range':'bytes=0-7'})
            self.assertEqual(status,206);self.assertEqual(part,body[:8]);self.assertIn('bytes 0-7/',h['Content-Range'])
            self.assertEqual(self.req(self.admin,'POST','/posts',{'kind':'item','title':'Not my upload','game_slug':'pubg-mobile','media_id':mid,'status':'published','permission':True})[0],400)
            p=self.post(self.seller,kind='item',media_id=mid)
            self.assertEqual(self.req(self.guest,'GET','/media/'+mid)[0],200)
            self.req(self.seller,'PATCH','/posts/'+p['id'],{'audience':'private','permission':True})
            self.assertEqual(self.req(self.guest,'GET','/media/'+mid)[0],404)
            self.assertEqual(self.req(self.seller,'POST','/media',raw=b'<svg onload=alert(1)>',content_type='image/svg+xml')[0],415)

    def test_production_upload_requires_storage_and_suspension_hides_content(self):
        p=self.post(self.seller)
        with patch.object(app,'MODE','production'),patch.object(app.storage_r2,'is_configured',return_value=False):
            self.assertEqual(self.req(self.seller,'POST','/media',raw=self.image(),content_type='image/png')[0],503)
        self.db.execute('UPDATE users SET suspended=1 WHERE id=?',(self.seller_id,))
        self.assertEqual(self.req(self.guest,'GET','/posts/'+p['id'])[0],404)
        self.assertEqual(self.req(self.seller,'GET','/posts')[0],403)

    def test_report_moderation_and_comment_preferences(self):
        self.profile(self.seller,preferences={'comments':'nobody'})
        p=self.post(self.seller)
        self.assertEqual(self.req(self.admin,'POST','/posts/'+p['id']+'/comments',{'body':'No'})[0],403)
        self.assertEqual(self.req(self.admin,'POST','/posts/'+p['id']+'/report',{'reason':'spam'})[0],200)
        self.assertEqual(self.seller.request('GET','/api/admin/community/reports')[0],403)
        status,r,_=self.admin.request('GET','/api/admin/community/reports');self.assertEqual(status,200,r)
        report=r['reports'][0]
        for action,status in (('hide',404),('restore',200)):
            result=self.admin.request('POST','/api/admin/community/reports/'+report['id'],{'action':action})
            self.assertEqual(result[0],200,result[1]);self.assertEqual(self.req(self.guest,'GET','/posts/'+p['id'])[0],status)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM audit_logs WHERE action IN ('community.hide','community.restore')").fetchone()[0],2)

    def test_related_media_excludes_author_viewer_and_inaccessible_content(self):
        with patch.object(app.storage_r2,'is_configured',return_value=False):
            media={}
            for client in (self.seller,self.admin):
                status,m,_=self.req(client,'POST','/media',raw=self.image(),content_type='image/png')
                self.assertEqual(status,201,m);media[client]=m['id']
            source=self.post(self.seller)
            own=self.post(self.seller,kind='moment',media_id=media[self.seller])
            same=self.post(self.admin,kind='moment',media_id=media[self.admin])
            other=self.post(self.admin,kind='moment',media_id=media[self.admin],game_slug='valorant')
            self.post(self.admin,kind='moment',media_id=media[self.admin],audience='private')
            self.post(self.admin,kind='moment',media_id=media[self.admin],audience='followers')
            self.post(self.admin,kind='moment',media_id=media[self.admin],status='draft')
            no_media=self.post(self.admin)
            endpoint='/posts/'+source['id']+'/related'
            result=self.req(self.guest,'GET',endpoint)
            self.assertEqual(result[0],200,result[1])
            self.assertEqual([p['id'] for p in result[1]['posts']],[same['id'],other['id']])
            self.assertTrue(all(p['media_url'] and 'email' not in p['author'] for p in result[1]['posts']))
            self.assertEqual(self.req(self.admin,'GET',endpoint)[1]['posts'],[])
            self.profile(self.admin,visibility='private')
            self.assertEqual(self.req(self.guest,'GET',endpoint)[1]['posts'],[])
            self.profile(self.admin,visibility='public')
            self.req(self.seller,'POST','/profiles/'+self.admin_id+'/block',{'enabled':True})
            self.assertEqual(self.req(self.seller,'GET',endpoint)[1]['posts'],[])
            self.db.execute('UPDATE users SET suspended=1 WHERE id=?',(self.admin_id,))
            self.assertEqual(self.req(self.guest,'GET',endpoint)[1]['posts'],[])
            self.profile(self.seller,visibility='private')
            self.assertEqual(self.req(self.guest,'GET',endpoint)[0],404)

    def test_delete_erases_posts_saves_comments_and_layout_validates_ownership(self):
        p=self.post(self.seller)
        self.profile(self.seller,layout=[p['id']])
        self.assertEqual(self.req(self.admin,'PATCH','/profile',{'layout':[p['id']]})[0],400)
        self.req(self.admin,'POST','/posts/'+p['id']+'/save',{'enabled':True})
        self.req(self.admin,'POST','/posts/'+p['id']+'/comments',{'body':'Hello'})
        self.assertEqual(self.req(self.seller,'DELETE','/posts/'+p['id'])[0],200)
        self.assertEqual(self.req(self.admin,'GET','/posts?mode=saved')[1]['posts'],[])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_comments').fetchone()[0],0)

    def test_media_cleanup_preserves_drafts_and_account_erasure_removes_content(self):
        import community
        with patch.object(app.storage_r2,'is_configured',return_value=False):
            media=[]
            for _ in range(2):
                status,m,_=self.req(self.seller,'POST','/media',raw=self.image(),content_type='image/png')
                self.assertEqual(status,201,m);media.append(m['id'])
            self.post(self.seller,kind='item',media_id=media[0],status='draft')
            self.db.execute("UPDATE community_media SET created_at='2020-01-01 00:00:00'")
            self.assertEqual(community.cleanup_media(self.db,vars(app)),1)
            self.assertEqual(self.req(self.seller,'GET','/media/'+media[0])[0],200)
            self.assertEqual(self.req(self.seller,'GET','/media/'+media[1])[0],404)
            community.erase(self.db,self.seller_id,vars(app))
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_posts').fetchone()[0],0)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM community_media').fetchone()[0],0)
            self.assertEqual(self.req(self.guest,'GET','/profiles/'+self.seller_id)[0],404)

    def test_r2_upload_is_private_and_signing_requires_post_access(self):
        with patch.object(app.storage_r2,'is_configured',return_value=True),patch.object(app.storage_r2,'put_evidence') as put,patch.object(app.storage_r2,'read_evidence',return_value=self.image()),patch.object(app.storage_r2,'evidence_url',return_value='https://private.r2.cloudflarestorage.com/lease') as sign:
            status,m,_=self.req(self.seller,'POST','/media',raw=self.image(),content_type='image/png')
            self.assertEqual(status,201,m);put.assert_called_once();self.assertEqual(put.call_args.args[1][:4],b'RIFF')
            self.assertEqual(self.req(self.guest,'GET','/media/'+m['id'])[0],404);sign.assert_not_called()
            p=self.post(self.seller,kind='item',media_id=m['id'])
            status,_,headers=self.req(self.guest,'GET','/media/'+m['id'])
            self.assertEqual(status,302);self.assertEqual(headers['Cache-Control'],'private, no-store');sign.assert_called_once()
            self.req(self.seller,'PATCH','/posts/'+p['id'],{'audience':'private','permission':True})
            self.assertEqual(self.req(self.guest,'GET','/media/'+m['id'])[0],404);sign.assert_called_once()

    def test_private_folders_persist_without_saving_a_post(self):
        self.assertEqual(self.req(self.guest,'POST','/folders',{'name':'Private shelf'})[0],401)
        self.assertEqual(self.req(self.seller,'POST','/folders',{'name':'Private shelf'})[0],201)
        self.assertEqual(self.req(self.seller,'GET','/folders')[1]['folders'],['Private shelf'])
        self.assertEqual(self.req(self.admin,'GET','/folders')[1]['folders'],[])
        self.assertEqual(self.req(self.seller,'POST','/folders',{'name':''})[0],400)

    def test_gameplay_video_audio_is_preserved_without_changing_evidence_defaults(self):
        import subprocess,tempfile,imageio_ffmpeg,video_evidence
        from pathlib import Path
        executable=imageio_ffmpeg.get_ffmpeg_exe()
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'clip.mp4'
            subprocess.run([executable,'-hide_banner','-loglevel','error','-f','lavfi','-i','color=c=black:s=160x120:d=1',
                '-f','lavfi','-i','sine=frequency=440:duration=1','-c:v','libx264','-c:a','aac','-shortest','-y',str(source)],capture_output=True,check=True,timeout=8)
            for preserve in (False,True):
                target=Path(directory)/('sound.mp4' if preserve else 'silent.mp4')
                target.write_bytes(video_evidence.normalize(source.read_bytes(),preserve_audio=preserve))
                probe=subprocess.run([executable,'-hide_banner','-i',str(target)],capture_output=True,timeout=5)
                self.assertEqual(b'Audio:' in probe.stderr,preserve)

if __name__=='__main__':unittest.main()

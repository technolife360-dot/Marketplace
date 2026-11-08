"""PostgreSQL SQL/visibility checks with connection-local synthetic TEMP tables."""
import os
import unittest
import app
import community
import community_safety

@unittest.skipUnless(os.environ.get('SENTRYLOOT_TEST_POSTGRES_TEMP')=='1','Requires explicitly enabled PostgreSQL TEMP fixtures')
class CommunityPostgres(unittest.TestCase):
    def setUp(self):
        self.db=app.connect();self.db.execute('BEGIN');self.addCleanup(self.cleanup)
        self.db.execute("CREATE TEMP TABLE users(id TEXT PRIMARY KEY,display_name TEXT,country TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,suspended INTEGER DEFAULT 0) ON COMMIT DROP")
        self.db.execute('CREATE TEMP TABLE games(slug TEXT PRIMARY KEY,name TEXT) ON COMMIT DROP')
        self.db.execute('CREATE TEMP TABLE platform_config(key TEXT PRIMARY KEY,value TEXT) ON COMMIT DROP')
        self.db.execute('CREATE TEMP TABLE listings(id TEXT PRIMARY KEY) ON COMMIT DROP')
        for statement in community.SCHEMA:
            if statement.startswith('CREATE TABLE'):
                self.db.execute(statement.replace('CREATE TABLE IF NOT EXISTS','CREATE TEMP TABLE')+' ON COMMIT DROP')
        self.db.execute("INSERT INTO users(id,display_name,country) VALUES('qa-author','Author','UZ'),('qa-reader','Reader','MY')")
        self.db.execute("INSERT INTO games VALUES('qa-game','QA game')")
        self.db.execute("INSERT INTO community_profiles(user_id,handle) VALUES('qa-author','author'),('qa-reader','reader')")
        self.db.execute("INSERT INTO community_posts(id,user_id,kind,title,game_slug,audience,status) VALUES('qa-public','qa-author','achievement','First milestone','qa-game','public','published'),('qa-private','qa-author','achievement','Private milestone','qa-game','private','published'),('qa-followers','qa-author','achievement','Circle milestone','qa-game','followers','published')")
        self.core={'HttpError':app.HttpError,'require_user':lambda c:c['uid'],'is_admin':lambda db,uid:False}
        self.ctx={'uid':'qa-reader','user':None}
    def cleanup(self):
        try:self.db.execute('ROLLBACK')
        finally:self.db.close()
    def feed(self,query=None):
        return community.route(None,self.db,self.ctx,'GET','/api/community/posts',query or {},{},b'',self.core)['posts']
    def test_public_migration_keeps_community_tables_server_only(self):
        app.assert_private_postgres_tables(self.db,community.TABLES)

    def test_batched_feed_serializes_metrics_and_enforces_audience(self):
        self.assertEqual([p['id'] for p in self.feed()],['qa-public'])
        self.db.execute("INSERT INTO community_follows(user_id,target_id) VALUES('qa-reader','qa-author')")
        self.db.execute("INSERT INTO community_reactions VALUES('qa-reader','qa-public')")
        posts=self.feed();self.assertEqual(len(posts),2)
        public=next(p for p in posts if p['id']=='qa-public')
        self.assertEqual(public['reactions'],1);self.assertTrue(public['liked']);self.assertEqual(public['author']['followers'],1)
        self.db.execute("INSERT INTO community_blocks VALUES('qa-author','qa-reader')")
        self.assertEqual(self.feed(),[])
    def test_album_order_and_large_media_sizes_survive_postgres_serialization(self):
        self.db.execute("INSERT INTO community_media(id,user_id,object_key,content_type,byte_size) VALUES('qa-media-a','qa-author','qa-a','image/webp',3000000000),('qa-media-b','qa-author','qa-b','image/webp',20)")
        self.db.execute("UPDATE community_posts SET media_id='qa-media-a' WHERE id='qa-public'")
        self.db.execute("INSERT INTO community_post_media VALUES('qa-public','qa-media-a',0),('qa-public','qa-media-b',1)")
        post=self.feed()[0]
        self.assertEqual(post['media_ids'],['qa-media-a','qa-media-b'])
        self.assertEqual([m['url'] for m in post['media']],['/api/community/media/qa-media-a','/api/community/media/qa-media-b'])
        self.assertEqual(self.db.execute("SELECT byte_size FROM community_media WHERE id='qa-media-a'").fetchone()['byte_size'],3000000000)

    def test_players_search_and_saved_filter_use_portable_sql(self):
        players=community.route(None,self.db,self.ctx,'GET','/api/community/players',{'q':['Author']},{},b'',self.core)['players']
        self.assertEqual(players[0]['id'],'qa-author')
        self.db.execute("INSERT INTO community_saves(user_id,post_id,folder) VALUES('qa-reader','qa-public','Favorites')")
        self.assertEqual(len(self.feed({'mode':['saved']})),1)
        self.db.execute("UPDATE community_profiles SET visibility='private' WHERE user_id='qa-author'")
        self.assertEqual(self.feed({'mode':['saved']}),[])

    def test_guest_and_member_bootstrap_and_profile_counts_use_named_columns(self):
        guest={'uid':None,'user':None,'csrf':''}
        result=community.route(None,self.db,guest,'GET','/api/community/meta',{}, {},b'',self.core)
        self.assertEqual(result['unread'],0)
        self.assertEqual(result['games'],[{'slug':'qa-game','name':'QA game'}])
        self.assertIsNone(result['profile'])
        member={**self.ctx,'csrf':'test-csrf'}
        result=community.route(None,self.db,member,'GET','/api/community/meta',{}, {},b'',self.core)
        self.assertEqual(result['profile']['followers'],0)
        self.assertEqual(result['profile']['following_count'],0)
        self.assertEqual(result['csrf'],'test-csrf')
        profile=community.route(None,self.db,self.ctx,'GET','/api/community/profiles/qa-author',{}, {},b'',self.core)
        self.assertEqual(profile['followers'],0)

    def test_folder_names_use_named_postgres_columns(self):
        self.db.execute("INSERT INTO community_folders(user_id,name) VALUES('qa-reader','Clutches')")
        self.db.execute("INSERT INTO community_saves(user_id,post_id,folder) VALUES('qa-reader','qa-public','Highlights')")
        result=community.route(None,self.db,self.ctx,'GET','/api/community/folders',{}, {},b'',self.core)
        self.assertEqual(result['folders'],['Clutches','Highlights'])

    def test_hidden_posts_stay_private_but_the_author_can_correct_them(self):
        self.db.execute("UPDATE community_posts SET status='hidden' WHERE id='qa-public'")
        self.assertEqual(community.get_post(self.db,'qa-public','qa-author',self.core)['status'],'hidden')
        with self.assertRaises(app.HttpError):community.get_post(self.db,'qa-public','qa-reader',self.core)
        self.assertEqual(self.feed(),[])

    def test_automatic_decision_and_reason_are_saved_without_a_human_reviewer(self):
        community_safety.record_submission(self.db,'qa-public',None,'published',True,
                                           decision='rejected',note='Automatic safety decision')
        result=self.db.execute("SELECT review_status,review_note,reviewer_id FROM community_post_state WHERE post_id='qa-public'").fetchone()
        self.assertEqual(result['review_status'],'rejected')
        self.assertEqual(result['review_note'],'Automatic safety decision')
        self.assertIsNone(result['reviewer_id'])

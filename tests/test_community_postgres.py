"""PostgreSQL SQL/visibility checks with connection-local synthetic TEMP tables."""
import os
import unittest
import app
import community

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
        self.core={'HttpError':app.HttpError,'require_user':lambda c:c['uid']}
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
    def test_players_search_and_saved_filter_use_portable_sql(self):
        players=community.route(None,self.db,self.ctx,'GET','/api/community/players',{'q':['Author']},{},b'',self.core)['players']
        self.assertEqual(players[0]['id'],'qa-author')
        self.db.execute("INSERT INTO community_saves(user_id,post_id,folder) VALUES('qa-reader','qa-public','Favorites')")
        self.assertEqual(len(self.feed({'mode':['saved']})),1)
        self.db.execute("UPDATE community_profiles SET visibility='private' WHERE user_id='qa-author'")
        self.assertEqual(self.feed({'mode':['saved']}),[])

"""Listing-linked posts, human review, private rights cases and video lifecycle."""
import json
import hashlib
import math
from urllib.parse import urlsplit
import re
from datetime import datetime, timezone
import community_video as video

TABLES = ('community_post_state', 'community_cases', 'community_streams')
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS community_post_state (
        post_id TEXT PRIMARY KEY REFERENCES community_posts(id) ON DELETE CASCADE,
        listing_id TEXT REFERENCES listings(id) ON DELETE SET NULL,
        review_status TEXT NOT NULL DEFAULT 'approved' CHECK(review_status IN ('pending','approved','rejected','draft')),
        review_note TEXT NOT NULL DEFAULT '', rights_at TEXT, reviewer_id TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS community_cases (
        id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id) ON DELETE SET NULL,
        kind TEXT NOT NULL CHECK(kind IN ('copyright','privacy','appeal','comment')),
        post_id TEXT NOT NULL DEFAULT '', comment_id TEXT NOT NULL DEFAULT '',
        name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
        reference TEXT NOT NULL DEFAULT '', body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','resolved')),
        decision TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS community_streams (
        media_id TEXT PRIMARY KEY REFERENCES community_media(id) ON DELETE CASCADE,
        remote_id TEXT NOT NULL UNIQUE, state TEXT NOT NULL DEFAULT 'uploading',
        duration REAL NOT NULL DEFAULT 0, checked_at TEXT)""",
    'CREATE INDEX IF NOT EXISTS community_review_queue ON community_post_state(review_status,updated_at)',
    'CREATE INDEX IF NOT EXISTS community_case_queue ON community_cases(status,created_at)',
)


def listing(db, lid, core):
    row = db.execute('''SELECT l.id,l.seller_id,l.game_id,g.slug game_slug,l.title,l.price_minor,l.currency,
        l.platform,l.region,l.delivery_eta,l.stock,l.reserved,l.status,s.shop_name,
        s.selling_enabled,s.verification_status,u.suspended,l.product_type
        FROM listings l JOIN games g ON g.id=l.game_id JOIN users u ON u.id=l.seller_id
        JOIN seller_profiles s ON s.user_id=l.seller_id WHERE l.id=?''', (lid,)).fetchone()
    if not row or row['suspended'] or not row['selling_enabled'] or row['verification_status'] != 'verified':
        return None
    if not core['listing_allowed_for_production'](db, row['game_id'], row['product_type']):
        return None
    if core['MODE'] == 'production' and core['launch_readiness'].test_listing(db, lid):
        return None
    if row['status'] != 'published':
        return None
    return {k: row[k] for k in ('id','seller_id','game_slug','title','price_minor','currency','platform','region','delivery_eta','shop_name')} | {
        'available': row['stock'] > row['reserved']}


def enrich(db, posts, uid, core):
    if not posts:
        return posts
    ids = [p['id'] for p in posts]
    rows = db.execute('SELECT * FROM community_post_state WHERE post_id IN (' + ','.join('?' for _ in ids) + ')', ids).fetchall()
    states = {r['post_id']: r for r in rows}
    for p in posts:
        s = states.get(p['id'])
        p['listing_id'] = s['listing_id'] if s else None
        p['listing'] = listing(db, s['listing_id'], core) if s and s['listing_id'] else None
        p['promotion'] = bool(s and s['listing_id'])
        if p['user_id'] == uid:
            p['review_status'] = s['review_status'] if s else 'approved'
            p['review_note'] = s['review_note'] if s else ''
    return posts


def prepare(db, uid, source, core):
    import community as c
    lid = source.get('listing_id') or None
    if lid:
        if not isinstance(lid, str):
            c.fail(core,400,'Choose one of your active listings.')
        item = listing(db, lid, core)
        if not item or item['seller_id'] != uid or not item['available']:
            c.fail(core,400,'Choose one of your active listings.')
        if item['game_slug'] != source['game_slug']:
            c.fail(core,400,'The post and listing must belong to the same game.')
        if source['kind'] != 'moment':
            c.fail(core,400,'Use a moment to showcase a listing.')
    return lid


def review_token(db, pid):
    row=db.execute('SELECT p.*,s.rights_at,s.listing_id FROM community_posts p JOIN community_post_state s ON s.post_id=p.id WHERE p.id=?',(pid,)).fetchone()
    return hashlib.sha256(json.dumps(dict(row) if row else {},sort_keys=True,default=str).encode()).hexdigest()


def record_submission(db, pid, lid, requested, permission):
    db.execute('''INSERT INTO community_post_state(post_id,listing_id,review_status,rights_at)
        VALUES(?,?,?,?) ON CONFLICT(post_id) DO UPDATE SET listing_id=excluded.listing_id,
        review_status=excluded.review_status,review_note='',reviewer_id=NULL,rights_at=excluded.rights_at,
        updated_at=CURRENT_TIMESTAMP''', (pid,lid,'pending' if requested == 'published' else 'draft',
        datetime.now(timezone.utc).isoformat() if permission else None))


def remove_object(core, row):
    import community as c
    if row['object_key'].startswith('stream:'):
        video.delete(row['object_key'][7:])
    elif core['storage_r2'].is_configured():
        core['storage_r2'].delete_evidence(row['object_key'])
    else:
        c.disk_path(core,row['object_key']).unlink(missing_ok=True)


def route(handler,db,ctx,method,path,qs,data,core):
    import community as c
    uid=ctx['uid']
    if path=='/api/community/listings' and method=='GET':
        core['require_verified'](ctx)
        rows=db.execute("SELECT id FROM listings WHERE seller_id=? AND status='published' ORDER BY created_at DESC LIMIT 100",(uid,))
        return {'listings':[item for r in rows if (item:=listing(db,r['id'],core)) and item['available']]}
    if path=='/api/community/cases' and method=='POST':
        # Rights holders need not open a marketplace account to contact us.
        origin=handler.headers.get('Origin','')
        if origin and urlsplit(origin).netloc.lower()!=handler.headers.get('Host','').lower():c.fail(core,403,'Use the SentryLoot request form.')
        if not handler.headers.get('Content-Type','').lower().startswith('application/json'):c.fail(core,415,'Send the request as JSON.')
        core['check_rate'](db,'community-case',uid or handler.client_address[0],5,3600)
        kind=data.get('kind')
        if kind not in ('copyright','privacy','appeal','comment'):c.fail(core,400,'Choose a request type.')
        pid=c.text(core,data.get('post_id',''),100,1)
        post=db.execute('SELECT id,user_id,status FROM community_posts WHERE id=?',(pid,)).fetchone()
        name=c.text(core,data.get('name',''),100,2);email=c.text(core,data.get('email',''),254,3)
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):c.fail(core,400,'Enter a valid contact email.')
        body=c.text(core,data.get('body',''),4000,20);reference=c.text(core,data.get('reference',''),1000)
        if kind=='copyright' and (len(reference)<5 or data.get('attestation') is not True):
            c.fail(core,400,'Identify the original work and confirm your authority and the accuracy of your request.')
        comment=''
        if kind in ('appeal','comment'):
            core['require_verified'](ctx)
            if kind=='appeal':
                if not post or post['user_id']!=uid or post['status']!='hidden':c.fail(core,400,'Only the author can appeal a removed post.')
            else:
                c.get_post(db,pid,uid,core)
                comment=c.text(core,data.get('comment_id',''),100,1)
                if not db.execute('SELECT 1 FROM community_comments WHERE id=? AND post_id=?',(comment,pid)).fetchone():c.fail(core,404,'Comment unavailable.')
        # Identical requests are idempotent; response does not disclose whether a private post exists.
        old=db.execute("SELECT id FROM community_cases WHERE email=? AND post_id=? AND kind=? AND comment_id=? AND status='open'",(email,pid,kind,comment)).fetchone()
        cid=old['id'] if old else core['ident']()
        if not old:db.execute('INSERT INTO community_cases(id,user_id,kind,post_id,comment_id,name,email,reference,body) VALUES(?,?,?,?,?,?,?,?,?)',(cid,uid,kind,pid,comment,name,email,reference,body))
        return 201,{'id':cid,'status':'open'}
    if path=='/api/community/submissions' and method=='GET':
        core['require_verified'](ctx)
        rows=db.execute("SELECT p.*,s.review_status,s.review_note FROM community_posts p JOIN community_post_state s ON s.post_id=p.id WHERE p.user_id=? AND s.review_status IN ('pending','rejected') AND p.status<>'deleted' ORDER BY s.updated_at DESC LIMIT 100",(uid,)).fetchall()
        return {'posts':[{'id':r['id'],'title':r['title'],'review_status':r['review_status'],'review_note':r['review_note']} for r in rows],
            'cases':[dict(r) for r in db.execute('SELECT id,kind,post_id,status,decision,created_at FROM community_cases WHERE user_id=? ORDER BY created_at DESC LIMIT 100',(uid,))]}
    if path.startswith('/api/admin/community/'):
        core['require_admin'](ctx)
        if path=='/api/admin/community/queue' and method=='GET':
            return {'posts':[dict(r) for r in db.execute("SELECT p.id,p.title,p.body,p.game_slug,p.media_id,p.user_id,p.updated_at,s.review_status,s.review_note FROM community_posts p JOIN community_post_state s ON s.post_id=p.id WHERE s.review_status='pending' AND p.status='draft' ORDER BY s.updated_at LIMIT 100")],
                'cases':[dict(r) for r in db.execute("SELECT * FROM community_cases WHERE status='open' ORDER BY created_at LIMIT 100")]}
        m=re.fullmatch('/api/admin/community/review/([A-Za-z0-9_-]+)',path)
        if m:
            p=db.execute("SELECT * FROM community_posts WHERE id=? AND status<>'deleted'",(m[1],)).fetchone()
            if not p:c.fail(core,404,'Post unavailable.')
            if method=='GET':
                authors=c.author_views(db,[p['user_id']],uid)
                out=c.post_view(db,p,uid,core,authors=authors)
                for key in ('media_url','thumbnail_url'):
                    if out.get(key):out[key]+='?review=1'
                out['review_token']=review_token(db,p['id'])
                return enrich(db,[out],uid,core)[0]
            if method=='POST':
                decision=data.get('decision');note=c.text(core,data.get('note',''),1000,5)
                if decision not in ('approved','rejected'):c.fail(core,400,'Choose a review decision.')
                db.execute('BEGIN IMMEDIATE')
                try:
                    db.execute('UPDATE community_posts SET id=id WHERE id=?',(p['id'],))
                    if data.get('review_token')!=review_token(db,p['id']):c.fail(core,409,'The post changed. Open it again before reviewing.')
                    current=db.execute('SELECT p.status,s.review_status FROM community_posts p JOIN community_post_state s ON s.post_id=p.id WHERE p.id=?',(p['id'],)).fetchone()
                    if not current or current['review_status']!='pending' or current['status']!='draft':c.fail(core,409,'This submission is no longer pending.')
                    db.execute('UPDATE community_post_state SET review_status=?,review_note=?,reviewer_id=?,updated_at=CURRENT_TIMESTAMP WHERE post_id=?',(decision,note,uid,p['id']))
                    db.execute('UPDATE community_posts SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',('published' if decision=='approved' else 'hidden',p['id']))
                    core['audit'](db,uid,'community.review','post',p['id'],{'decision':decision,'note':note})
                    db.execute('COMMIT')
                except Exception:db.execute('ROLLBACK');raise
                return {'ok':True}
        m=re.fullmatch('/api/admin/community/cases/([A-Za-z0-9_-]+)',path)
        if m and method=='POST':
            row=db.execute('SELECT * FROM community_cases WHERE id=?',(m[1],)).fetchone()
            if not row:c.fail(core,404,'Request unavailable.')
            decision=c.text(core,data.get('decision',''),1000,5);action=data.get('action')
            if action not in ('resolve','hide','remove_comment','reconsider'):c.fail(core,400,'Choose an action.')
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('UPDATE community_cases SET id=id WHERE id=?',(row['id'],))
                current_case=db.execute('SELECT status FROM community_cases WHERE id=?',(row['id'],)).fetchone()
                if current_case['status']!='open':c.fail(core,409,'This request has already been resolved.')
                db.execute('UPDATE community_posts SET id=id WHERE id=?',(row['post_id'],))
                current_post=db.execute('SELECT status FROM community_posts WHERE id=?',(row['post_id'],)).fetchone()
                if action=='hide':
                    if not current_post or current_post['status']!='published':c.fail(core,409,'Only a published post can be removed.')
                    db.execute("UPDATE community_posts SET status='hidden',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='published'",(row['post_id'],))
                    db.execute("UPDATE community_post_state SET review_status='rejected',review_note=?,updated_at=CURRENT_TIMESTAMP WHERE post_id=?",(decision,row['post_id']))
                elif action=='remove_comment':
                    if row['kind']!='comment':c.fail(core,400,'This is not a comment report.')
                    db.execute('DELETE FROM community_comments WHERE id=? AND post_id=?',(row['comment_id'],row['post_id']))
                elif action=='reconsider':
                    if row['kind']!='appeal':c.fail(core,400,'This is not an appeal.')
                    if not current_post or current_post['status']!='hidden':c.fail(core,409,'Only a removed post can be reconsidered.')
                    db.execute("UPDATE community_posts SET status='draft' WHERE id=? AND status='hidden'",(row['post_id'],))
                    db.execute("UPDATE community_post_state SET review_status='pending',review_note=?,updated_at=CURRENT_TIMESTAMP WHERE post_id=?",(decision,row['post_id']))
                db.execute("UPDATE community_cases SET status='resolved',decision=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(decision,row['id']))
                core['audit'](db,uid,'community.case.'+action,'case',row['id'],{'decision':decision})
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
            return {'ok':True}
    if path=='/api/community/video-upload' and method=='POST':
        uid=c.ensure_profile(db,ctx,core)
        core['check_rate'](db,'community-video-reserve',uid,5,3600)
        size=data.get('size')
        if type(size) is not int or not 20<=size<=video.MAX_BYTES:c.fail(core,400,'Choose a video up to 200 MB and 3 minutes.')
        if not video.configured():c.fail(core,503,'Large video uploads are not available yet. Use a clip up to 4 MB and 30 seconds.')
        # Reserve before the external call; lock the user to serialize per-account quotas.
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('UPDATE users SET id=id WHERE id=?',(uid,))
            count=db.execute("SELECT COUNT(*) FROM community_media WHERE user_id=? AND content_type='video/stream'",(uid,)).fetchone()[0]
            if count>=50:c.fail(core,429,'Video storage limit reached. Remove unused videos first.')
            remote,url=video.reserve(size,uid);mid=core['ident']()
            db.execute('INSERT INTO community_media(id,user_id,object_key,content_type,byte_size) VALUES(?,?,?,?,?)',(mid,uid,'stream:'+remote,'video/stream',size))
            db.execute('INSERT INTO community_streams(media_id,remote_id) VALUES(?,?)',(mid,remote))
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            if 'remote' in locals():video.delete(remote)
            raise
        return 201,{'id':mid,'upload_url':url,'content_type':'video/stream'}
    m=re.fullmatch('/api/community/video-upload/([A-Za-z0-9_-]+)',path)
    if m and method=='GET':
        core['require_verified'](ctx)
        row=db.execute('SELECT s.* FROM community_streams s JOIN community_media m ON m.id=s.media_id WHERE s.media_id=? AND m.user_id=?',(m[1],uid)).fetchone()
        if not row:c.fail(core,404,'Video unavailable.')
        core['check_rate'](db,'community-video-poll',uid,120,3600)
        if row['state']!='ready':
            result=video.details(row['remote_id'])
            state='ready' if result.get('readyToStream') and result.get('requireSignedURLs') is True else 'processing'
            if result.get('status',{}).get('state')=='error':state='error'
            try:duration=float(result.get('duration') or 0)
            except (ValueError,TypeError):duration=0;state='error'
            if not math.isfinite(duration):duration=0;state='error'
            if duration>video.MAX_SECONDS or state=='ready' and duration<=0:state='error'
            db.execute('UPDATE community_streams SET state=?,duration=?,checked_at=CURRENT_TIMESTAMP WHERE media_id=?',(state,duration,m[1]))
        else:state='ready'
        return {'id':m[1],'state':state,'content_type':'video/stream','url':'/api/community/media/'+m[1]}
    return c.UNHANDLED

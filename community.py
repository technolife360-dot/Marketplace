"""Gamer showcases. All access goes through the authenticated application server."""
from __future__ import annotations
import json
import re
import secrets
import community_safety as safety
import community_video
import community_moderation as automatic
import community_uploads
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

UNHANDLED = object()
TABLES = ('community_profiles','community_media','community_posts','community_post_media','community_follows','community_saves',
          'community_reactions','community_comments','community_blocks','community_events','community_reports','community_squad','community_folders') + safety.TABLES
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS community_profiles (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        handle TEXT NOT NULL UNIQUE, bio TEXT NOT NULL DEFAULT '', cover_id TEXT,
        visibility TEXT NOT NULL DEFAULT 'public' CHECK(visibility IN ('public','followers','private')),
        preferences TEXT NOT NULL DEFAULT '{}', layout TEXT NOT NULL DEFAULT '[]')""",
    """CREATE TABLE IF NOT EXISTS community_media (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        object_key TEXT NOT NULL UNIQUE, content_type TEXT NOT NULL, byte_size BIGINT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS community_posts (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('moment','item','achievement')), title TEXT NOT NULL,
        body TEXT NOT NULL DEFAULT '', game_slug TEXT NOT NULL REFERENCES games(slug), media_id TEXT REFERENCES community_media(id),
        thumbnail_id TEXT REFERENCES community_media(id), linked_items TEXT NOT NULL DEFAULT '[]',
        audience TEXT NOT NULL DEFAULT 'public' CHECK(audience IN ('public','followers','private')),
        status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','hidden','deleted')),
        comments_enabled INTEGER NOT NULL DEFAULT 1, pinned INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS community_post_media (
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
        media_id TEXT NOT NULL REFERENCES community_media(id), position INTEGER NOT NULL CHECK(position>=0),
        PRIMARY KEY(post_id,media_id), UNIQUE(post_id,position))""",
    'CREATE INDEX IF NOT EXISTS community_post_media_object ON community_post_media(media_id)',
    """CREATE TABLE IF NOT EXISTS community_follows (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,target_id), CHECK(user_id<>target_id))""",
    """CREATE TABLE IF NOT EXISTS community_saves (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
        folder TEXT NOT NULL DEFAULT 'Favorites', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,post_id))""",
    """CREATE TABLE IF NOT EXISTS community_reactions (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE, PRIMARY KEY(user_id,post_id))""",
    """CREATE TABLE IF NOT EXISTS community_comments (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE,
        body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS community_blocks (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(user_id,target_id), CHECK(user_id<>target_id))""",
    """CREATE TABLE IF NOT EXISTS community_events (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        actor_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, post_id TEXT REFERENCES community_posts(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS community_reports (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        post_id TEXT NOT NULL REFERENCES community_posts(id) ON DELETE CASCADE, reason TEXT NOT NULL, body TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,post_id))""",
    """CREATE TABLE IF NOT EXISTS community_squad (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, PRIMARY KEY(user_id,target_id), CHECK(user_id<>target_id))""",
    """CREATE TABLE IF NOT EXISTS community_folders (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, name TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(user_id,name))""",
    'CREATE INDEX IF NOT EXISTS community_posts_feed ON community_posts(status,created_at DESC,id DESC)',
    'CREATE INDEX IF NOT EXISTS community_posts_owner ON community_posts(user_id,status,created_at DESC)',
    'CREATE INDEX IF NOT EXISTS community_follow_target ON community_follows(target_id,user_id)',
    'CREATE INDEX IF NOT EXISTS community_comments_post ON community_comments(post_id,created_at,id)',
    'CREATE INDEX IF NOT EXISTS community_events_user ON community_events(user_id,created_at DESC)',
    'CREATE INDEX IF NOT EXISTS community_media_owner ON community_media(user_id,created_at)',
)
SCHEMA += safety.SCHEMA + community_uploads.SCHEMA
TABLES += community_uploads.TABLES
DEFAULTS = {'show_country':False,'comments':'everyone','notify_follow':True,'notify_reaction':True,'notify_comment':True,'games':[]}


def migrate(db, postgres=False):
    for statement in SCHEMA: db.execute(statement)
    if postgres:
        db.execute('ALTER TABLE community_media ALTER COLUMN byte_size TYPE BIGINT')
        for table in TABLES:
            db.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            db.execute(f'REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated')


def unpack(value, fallback):
    try: return json.loads(value)
    except (TypeError, ValueError): return fallback


def fail(core, status, message): raise core['HttpError'](status,message)


def text(core, value, maximum, minimum=0):
    if not isinstance(value,str) or not minimum <= len(value.strip()) <= maximum:
        fail(core,400,f'Use between {minimum} and {maximum} characters.')
    return value.strip()


def blocked(db, a, b):
    return bool(a and db.execute('SELECT 1 FROM community_blocks WHERE (user_id=? AND target_id=?) OR (user_id=? AND target_id=?)',(a,b,b,a)).fetchone())


def profile_row(db, target):
    return db.execute("""SELECT u.id,u.display_name,u.country,u.created_at,COALESCE(av.value,'') avatar_url,
        p.handle,p.bio,p.cover_id,p.visibility,p.preferences,p.layout FROM community_profiles p JOIN users u ON u.id=p.user_id
        LEFT JOIN platform_config av ON av.key='public_avatar:'||u.id WHERE (u.id=? OR p.handle=?) AND u.suspended=0""",(target,target)).fetchone()


def following(db, uid, target):
    return bool(uid and db.execute('SELECT 1 FROM community_follows WHERE user_id=? AND target_id=?',(uid,target)).fetchone())


def visible_profile(db, row, uid):
    return bool(row and (row['id']==uid or (not blocked(db,uid,row['id']) and
                (row['visibility']=='public' or (row['visibility']=='followers' and following(db,uid,row['id']))))))


def ensure_profile(db, ctx, core):
    uid=core['require_verified'](ctx)
    if not profile_row(db,uid):
        db.execute('INSERT INTO community_profiles(user_id,handle) VALUES(?,?) ON CONFLICT(user_id) DO NOTHING',(uid,'player-'+secrets.token_hex(6)))
    return uid


def profile(db, target, uid, core, *, owner=False):
    row=profile_row(db,target)
    if not visible_profile(db,row,uid): fail(core,404,'This showcase is private or unavailable.')
    result={k:row[k] for k in ('id','display_name','country','created_at','avatar_url','handle','bio','visibility')}
    if row['id']!=uid and not unpack(row['preferences'],{}).get('show_country',False):result['country']=''
    result.update(following=following(db,uid,row['id']), owner=row['id']==uid,
        followers=db.execute('SELECT COUNT(*) AS total FROM community_follows WHERE target_id=?',(row['id'],)).fetchone()['total'],
        following_count=db.execute('SELECT COUNT(*) AS total FROM community_follows WHERE user_id=?',(row['id'],)).fetchone()['total'],
        cover_url='/api/community/media/'+row['cover_id'] if row['cover_id'] else '',
        layout=unpack(row['layout'],[]))
    if result['owner']: result['preferences']={**DEFAULTS,**unpack(row['preferences'],{})}
    return result


def acl(uid):
    # Repeated everywhere posts may surface, including search, saved, comments and media.
    return """EXISTS(SELECT 1 FROM community_profiles cp JOIN users cu ON cu.id=cp.user_id WHERE cp.user_id=p.user_id AND cu.suspended=0
        AND (p.user_id=? OR (p.status='published' AND cp.visibility<>'private'
        AND (cp.visibility='public' OR EXISTS(SELECT 1 FROM community_follows cf WHERE cf.user_id=? AND cf.target_id=p.user_id))
        AND (p.audience='public' OR (p.audience='followers' AND EXISTS(SELECT 1 FROM community_follows cf WHERE cf.user_id=? AND cf.target_id=p.user_id)))
        AND NOT EXISTS(SELECT 1 FROM community_blocks cb WHERE (cb.user_id=? AND cb.target_id=p.user_id) OR (cb.target_id=? AND cb.user_id=p.user_id)))))""", (uid or '',)*5


def get_post(db, pid, uid, core):
    rule,params=acl(uid)
    row=db.execute("SELECT p.* FROM community_posts p WHERE p.id=? AND p.status<>'deleted' AND (p.status<>'hidden' OR p.user_id=?) AND "+rule,(pid,uid or '',*params)).fetchone()
    if not row: fail(core,404,'This post is private or unavailable.')
    return row


def post_view(db,row,uid,core,authors=None,metrics=None,attachments=None):
    author=authors[row['user_id']] if authors is not None else profile(db,row['user_id'],uid,core)
    result=dict(row)
    for key in ('media_id','thumbnail_id'):
        result[key.replace('_id','_url')]='/api/community/media/'+row[key] if row[key] else ''
    if row['media_id']:
        media=db.execute('SELECT content_type FROM community_media WHERE id=?',(row['media_id'],)).fetchone()
        result['media_type']=media['content_type'] if media else ''
    if attachments is None:
        attachments=db.execute('SELECT m.id,m.content_type FROM community_post_media a JOIN community_media m ON m.id=a.media_id WHERE a.post_id=? ORDER BY a.position',(row['id'],)).fetchall()
    if not attachments and row['media_id']:
        attachments=[{'id':row['media_id'],'content_type':result.get('media_type','')}]
    result['media']=[{'id':m['id'],'url':'/api/community/media/'+m['id'],'content_type':m['content_type']} for m in attachments]
    result['media_ids']=[m['id'] for m in attachments]
    if metrics is None:
        metrics=dict(db.execute("""SELECT
            (SELECT COUNT(*) FROM community_reactions WHERE post_id=?) reactions,
            (SELECT COUNT(*) FROM community_comments c JOIN users u ON u.id=c.user_id WHERE c.post_id=? AND u.suspended=0) comments,
            EXISTS(SELECT 1 FROM community_reactions WHERE user_id=? AND post_id=?) liked,
            EXISTS(SELECT 1 FROM community_saves WHERE user_id=? AND post_id=?) saved""",(row['id'],row['id'],uid or '',row['id'],uid or '',row['id'])).fetchone())
    metrics['liked']=bool(metrics['liked']);metrics['saved']=bool(metrics['saved'])
    result.update(author=author,owner=row['user_id']==uid,**metrics,linked_items=unpack(row['linked_items'],[]))
    return safety.enrich(db,[result],uid,core)[0]


def author_views(db,ids,uid):
    if not ids:return {}
    rows=db.execute("""SELECT u.id,u.display_name,u.country,u.created_at,p.handle,p.bio,p.visibility,p.cover_id,p.preferences,
        COALESCE(av.value,'') avatar_url,
        (SELECT COUNT(*) FROM community_follows f WHERE f.target_id=u.id) followers,
        (SELECT COUNT(*) FROM community_follows f WHERE f.user_id=u.id) following_count,
        EXISTS(SELECT 1 FROM community_follows f WHERE f.user_id=? AND f.target_id=u.id) following
        FROM community_profiles p JOIN users u ON u.id=p.user_id LEFT JOIN platform_config av ON av.key='public_avatar:'||u.id
        WHERE u.id IN ("""+','.join('?' for _ in ids)+')',(uid or '',*ids)).fetchall()
    result={}
    for row in rows:
        p=dict(row);p['owner']=row['id']==uid;p['cover_url']='/api/community/media/'+p.pop('cover_id') if row['cover_id'] else '';p['layout']=[]
        prefs=unpack(p.pop('preferences','{}'),{})
        if row['id']!=uid and not prefs.get('show_country',False):p['country']=''
        result[row['id']]=p
    return result


def post_views(db,rows,uid,core):
    if not rows:return []
    authors=author_views(db,list({r['user_id'] for r in rows}),uid)
    ids=[r['id'] for r in rows];placeholders=','.join('?' for _ in ids)
    metrics={r['id']:dict(r) for r in db.execute("""SELECT p.id,
        (SELECT COUNT(*) FROM community_reactions r WHERE r.post_id=p.id) reactions,
        (SELECT COUNT(*) FROM community_comments c JOIN users u ON u.id=c.user_id WHERE c.post_id=p.id AND u.suspended=0) comments,
        EXISTS(SELECT 1 FROM community_reactions r WHERE r.user_id=? AND r.post_id=p.id) liked,
        EXISTS(SELECT 1 FROM community_saves s WHERE s.user_id=? AND s.post_id=p.id) saved,
        COALESCE(m.content_type,'') media_type FROM community_posts p LEFT JOIN community_media m ON m.id=p.media_id
        WHERE p.id IN ("""+placeholders+')',(uid or '',uid or '',*ids)).fetchall()}
    albums={}
    for m in db.execute('SELECT a.post_id,m.id,m.content_type FROM community_post_media a JOIN community_media m ON m.id=a.media_id WHERE a.post_id IN ('+placeholders+') ORDER BY a.post_id,a.position',ids).fetchall():
        albums.setdefault(m['post_id'],[]).append(m)
    out=[]
    for row in rows:
        m=metrics[row['id']];m.pop('id',None)
        # Avoid media lookups and per-author queries for a bounded feed page.
        value=dict(row);media=value['media_id'];value['media_id']=None
        attachments=albums.get(row['id'],[{'id':media,'content_type':m['media_type']}] if media else [])
        p=post_view(db,value,uid,core,authors,m,attachments);p['media_id']=media;p['media_url']='/api/community/media/'+media if media else ''
        out.append(p)
    return out


def discover_previews(db, posts, uid):
    ids = [post['id'] for post in posts if post['comments']]
    if not ids:
        return
    placeholders = ','.join('?' for _ in ids)
    rows = db.execute(f"""
        SELECT * FROM (
            SELECT c.id,c.post_id,c.user_id,c.body,c.created_at,u.display_name,cp.handle,
                COALESCE(av.value,'') avatar_url,
                ROW_NUMBER() OVER (PARTITION BY c.post_id ORDER BY c.created_at DESC,c.id DESC) reply_rank
            FROM community_comments c JOIN users u ON u.id=c.user_id
            JOIN community_profiles cp ON cp.user_id=u.id
            LEFT JOIN platform_config av ON av.key='public_avatar:'||u.id
            WHERE c.post_id IN ({placeholders}) AND u.suspended=0
                AND NOT EXISTS (SELECT 1 FROM community_blocks b
                    WHERE (b.user_id=? AND b.target_id=c.user_id)
                       OR (b.target_id=? AND b.user_id=c.user_id))
        ) ranked WHERE reply_rank=1
        """, (*ids, uid or '', uid or '')).fetchall()
    by_post = {row['post_id']: dict(row) for row in rows}
    for post in posts:
        post['reply_preview'] = by_post.get(post['id'])


def event(db,target,actor,kind,post_id=None):
    if target==actor or blocked(db,target,actor): return
    p=db.execute('SELECT preferences FROM community_profiles WHERE user_id=?',(target,)).fetchone()
    if not p or not unpack(p['preferences'],{}).get('notify_'+kind,True): return
    # De-duplicate retries and repeated toggles within one day.
    eid=__import__('hashlib').sha256((target+actor+kind+(post_id or '')+__import__('datetime').date.today().isoformat()).encode()).hexdigest()
    db.execute('INSERT INTO community_events(id,user_id,actor_id,post_id,kind) VALUES(?,?,?,?,?) ON CONFLICT(id) DO NOTHING',(eid,target,actor,post_id,kind))


@dataclass
class MediaResponse:
    body: bytes
    content_type: str


def disk_path(core,key):
    return Path(str(core['DB_PATH'])+'.community-media')/key.replace('/','_')


def erase(db,uid,core):
    community_uploads.cleanup(db,core,uid)
    for row in db.execute('SELECT object_key FROM community_media WHERE user_id=?',(uid,)).fetchall():
        safety.remove_object(core,row)
    db.execute('DELETE FROM community_cases WHERE user_id=?',(uid,))
    for table in ('community_saves','community_reactions','community_comments','community_reports','community_events','community_squad','community_follows','community_blocks','community_folders'):
        db.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
    for table in ('community_follows','community_blocks','community_squad'): db.execute(f'DELETE FROM {table} WHERE target_id=?',(uid,))
    db.execute('DELETE FROM community_events WHERE actor_id=?',(uid,))
    db.execute('DELETE FROM community_posts WHERE user_id=?',(uid,))
    db.execute('DELETE FROM community_profiles WHERE user_id=?',(uid,))
    db.execute('DELETE FROM community_media WHERE user_id=?',(uid,))


def cleanup_media(db,core):
    """Purge unreferenced uploads after seven days; referenced drafts/covers stay intact."""
    from datetime import datetime,timedelta,timezone
    community_uploads.cleanup(db,core)
    cutoff=(datetime.now(timezone.utc)-timedelta(days=7)).strftime('%Y-%m-%d 00:00:00')
    unused="NOT EXISTS(SELECT 1 FROM community_posts p WHERE p.media_id=m.id OR p.thumbnail_id=m.id) AND NOT EXISTS(SELECT 1 FROM community_post_media a WHERE a.media_id=m.id) AND NOT EXISTS(SELECT 1 FROM community_profiles p WHERE p.cover_id=m.id)"
    rows=db.execute('SELECT m.id FROM community_media m WHERE m.created_at<? AND '+unused+' ORDER BY m.created_at LIMIT 20',(cutoff,)).fetchall()
    deleted=0
    for item in rows:
        db.execute('BEGIN IMMEDIATE')
        try:
            row=db.execute('SELECT m.* FROM community_media m WHERE m.id=? AND '+unused+(' FOR UPDATE' if core['DATABASE_URL'] else ''),(item['id'],)).fetchone()
            if row:
                safety.remove_object(core,row)
                db.execute('DELETE FROM community_media WHERE id=?',(row['id'],));deleted+=1
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
    return deleted


def route(handler,db,ctx,method,path,qs,data,raw,core):
    admin_path=path.startswith('/api/admin/community')
    if not path.startswith('/api/community') and not admin_path: return UNHANDLED
    uid=ctx['uid']; part=path.removeprefix('/api/community')
    q=lambda name,default='': qs.get(name,[default])[0]
    if ctx.get('user') and ctx['user']['suspended']: core['require_user'](ctx)
    if method in ('POST','PATCH','DELETE') and path!='/api/community/cases':
        core['require_verified'](ctx)
        if not re.fullmatch(r'/api/community/(?:uploads/[A-Za-z0-9_-]+/chunk|media/[A-Za-z0-9_-]+/check)',path):
            core['check_rate'](db,'community-write',uid,120,3600)
    upload_result=community_uploads.route(handler,db,ctx,method,path,qs,data,raw,core)
    if upload_result is not UNHANDLED:return upload_result
    try:
        extra=safety.route(handler,db,ctx,method,path,qs,data,core)
    except community_video.Unavailable as exc:fail(core,503,str(exc))
    if extra is not UNHANDLED:return extra
    if admin_path:
        core['require_admin'](ctx)
        if path=='/api/admin/community/reports' and method=='GET':
            rows=db.execute("""SELECT r.*,p.title,p.user_id author_id FROM community_reports r JOIN community_posts p ON p.id=r.post_id
                ORDER BY r.created_at DESC LIMIT 100""").fetchall()
            return {'reports':[dict(r) for r in rows]}
        if method=='POST' and re.fullmatch('/api/admin/community/reports/[A-Za-z0-9_-]+',path):
            r=db.execute('SELECT * FROM community_reports WHERE id=?',(path.split('/')[-1],)).fetchone()
            if not r: fail(core,404,'Report not found.')
            action=data.get('action')
            if action not in ('dismiss','hide','restore'): fail(core,400,'Choose a moderation action.')
            db.execute('BEGIN IMMEDIATE')
            try:
                if action=='restore':
                    current=db.execute("SELECT status FROM community_posts WHERE id=?",(r['post_id'],)).fetchone()
                    if not current or current['status']!='hidden':fail(core,409,'Only a removed post can be restored.')
                    review=db.execute('SELECT review_status FROM community_post_state WHERE post_id=?',(r['post_id'],)).fetchone()
                    if review and review['review_status']!='approved':fail(core,409,'Review the appeal before restoring this post.')
                if action!='dismiss': db.execute('UPDATE community_posts SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',('hidden' if action=='hide' else 'published',r['post_id']))
                db.execute('UPDATE community_reports SET status=? WHERE post_id=?',(action,r['post_id']))
                core['audit'](db,uid,'community.'+action,'post',r['post_id'],{})
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK');raise
            return {'ok':True}
        fail(core,404,'Not found.')
    if part=='/meta' and method=='GET':
        me=profile(db,uid,uid,core) if uid and profile_row(db,uid) else None
        return {'user':ctx['user'],'profile':me,'csrf':ctx['csrf'],
                'unread':db.execute('SELECT COUNT(*) AS total FROM community_events WHERE user_id=? AND seen=0',(uid or '',)).fetchone()['total'],
                'games':[dict(r) for r in db.execute('SELECT slug,name FROM games ORDER BY name').fetchall()],
                'admin':bool(uid and core['is_admin'](db,uid)), 'r2_upload_origin':core['storage_r2'].upload_origin() if core.get('storage_r2') and core['storage_r2'].is_configured() else '', 'stream_enabled':community_video.configured(), 'stream_limit':community_video.MAX_BYTES, 'stream_seconds':community_video.MAX_SECONDS}
    if part=='/profile' and method in ('POST','PATCH'):
        uid=ensure_profile(db,ctx,core);current=profile_row(db,uid)
        handle=text(core,data.get('handle',current['handle']),24,3).lower()
        if handle in {'admin','administrator','support','sentryloot','sentryloot-support','moderator','system'}:fail(core,400,'This handle is reserved.')
        if db.execute('SELECT 1 FROM users WHERE id=? AND id<>?',(handle,uid)).fetchone():fail(core,400,'This handle is reserved.')
        if not re.fullmatch('[a-z0-9][a-z0-9_-]{2,23}',handle): fail(core,400,'Use 3–24 letters, numbers, underscores or hyphens for your handle.')
        bio=text(core,data.get('bio',current['bio']),500)
        visibility=data.get('visibility',current['visibility'])
        if visibility not in ('public','followers','private'):fail(core,400,'Invalid audience.')
        prefs={**DEFAULTS,**unpack(current['preferences'],{})}
        updates=data.get('preferences',{})
        if not isinstance(updates,dict):fail(core,400,'Invalid preferences.')
        for k in ('show_country','notify_follow','notify_reaction','notify_comment'):
            if k in updates:
                if type(updates[k]) is not bool: fail(core,400,'Invalid preference.')
                prefs[k]=updates[k]
        if 'comments' in updates:
            if updates['comments'] not in ('everyone','following','nobody'):fail(core,400,'Invalid comment preference.')
            prefs['comments']=updates['comments']
        if 'games' in updates:
            if not isinstance(updates['games'],list) or len(updates['games'])>20:fail(core,400,'Choose up to 20 games.')
            prefs['games']=[text(core,v,100,1) for v in updates['games']]
            for game in prefs['games']:
                if not db.execute('SELECT 1 FROM games WHERE slug=?',(game,)).fetchone(): fail(core,400,'Unknown game.')
        cover=data.get('cover_id',current['cover_id']) or None
        if cover and not db.execute("SELECT 1 FROM community_media WHERE id=? AND user_id=? AND content_type='image/webp'",(cover,uid)).fetchone():fail(core,400,'Choose one of your uploaded cover images.')
        if cover and cover != current['cover_id']:
            try: result=automatic.assess(db,uid,[cover],'Community profile cover',core)
            except automatic.Unavailable as exc:fail(core,503,str(exc))
            if result.status!='approved':fail(core,422,result.note)
        name=text(core,data.get('display_name',ctx['user']['display_name']),60,2)
        layout=data.get('layout',unpack(current['layout'],[]))
        if not isinstance(layout,list) or len(layout)>12 or any(not isinstance(i,str) for i in layout):fail(core,400,'Pin up to 12 published posts.')
        if 'layout' not in data:
            layout=[pid for pid in layout if db.execute("SELECT 1 FROM community_posts WHERE id=? AND user_id=? AND status='published'",(pid,uid)).fetchone()]
        if len(set(layout))!=len(layout):fail(core,400,'Duplicate pins are not allowed.')
        for pid in layout:
            if not db.execute("SELECT 1 FROM community_posts WHERE id=? AND user_id=? AND status='published'",(pid,uid)).fetchone():fail(core,400,'Choose your published posts for your showcase.')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('UPDATE community_profiles SET handle=?,bio=?,visibility=?,preferences=?,cover_id=?,layout=? WHERE user_id=?',(handle,bio,visibility,json.dumps(prefs),cover,json.dumps(layout),uid))
            db.execute('UPDATE users SET display_name=? WHERE id=?',(name,uid))
            db.execute('COMMIT')
        except Exception: db.execute('ROLLBACK');raise
        return profile(db,uid,uid,core)
    if part=='/media' and method=='POST':
        uid=ensure_profile(db,ctx,core)
        core['check_rate'](db,'community-upload',uid,20,3600)
        if len(raw)>4*1024*1024:fail(core,413,'Upload a file up to 4 MB.')
        mime=handler.headers.get('Content-Type','').split(';')[0]
        if mime=='video/mp4':
            import video_evidence
            try: body=video_evidence.normalize(raw,preserve_audio=True)
            except video_evidence.InvalidVideo as exc:fail(core,400,str(exc))
            except video_evidence.VideoUnavailable as exc:fail(core,503,str(exc))
        else:
            body=core['normalize_account_evidence'](raw,mime);mime='image/webp'
        mid=core['ident']();key=secrets.token_hex(12)+'/'+secrets.token_hex(24)+'.webp'
        storage=core['storage_r2']
        if storage.is_configured():
            try: (storage.put_video_evidence if mime=='video/mp4' else storage.put_evidence)(key,body)
            except Exception:fail(core,503,'Upload failed. Your post has not been published. Try again.')
        elif core['MODE']=='development':
            p=disk_path(core,key);p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(body)
        else:fail(core,503,'Media storage is unavailable. Try again later.')
        try: db.execute('INSERT INTO community_media(id,user_id,object_key,content_type,byte_size) VALUES(?,?,?,?,?)',(mid,uid,key,mime,len(body)))
        except Exception:
            if storage.is_configured():storage.delete_evidence(key)
            else:disk_path(core,key).unlink(missing_ok=True)
            raise
        return 201,{'id':mid,'url':'/api/community/media/'+mid,'content_type':mime}
    if re.fullmatch('/media/[A-Za-z0-9_-]+',part) and method=='GET':
        mid=part.split('/')[-1];media=db.execute('SELECT * FROM community_media WHERE id=?',(mid,)).fetchone()
        allowed=bool(media and media['user_id']==uid)
        if media and not allowed:
            rule,params=acl(uid)
            allowed=bool(db.execute("SELECT 1 FROM community_posts p WHERE (p.media_id=? OR p.thumbnail_id=? OR EXISTS(SELECT 1 FROM community_post_media a WHERE a.post_id=p.id AND a.media_id=?)) AND p.status='published' AND "+rule,(mid,mid,mid,*params)).fetchone())
            if not allowed:
                p=profile_row(db,media['user_id']);allowed=bool(p and p['cover_id']==mid and visible_profile(db,p,uid))
        if media and q('review')=='1':
            core['require_admin'](ctx);allowed=True
        if not allowed:fail(core,404,'Media is private or unavailable.')
        if media['content_type']=='video/stream':
            stream=db.execute("SELECT * FROM community_streams WHERE media_id=? AND state='ready'",(mid,)).fetchone()
            if not stream:fail(core,409,'Video is still processing.')
            try:url=community_video.playback(stream['remote_id'])
            except community_video.Unavailable as exc:fail(core,503,str(exc))
            return {'iframe':url,'expires_in':300}
        if core['storage_r2'].is_configured():return 302,{}, {'Location':core['storage_r2'].evidence_url(media['object_key']),'Cache-Control':'private, no-store'}
        p=disk_path(core,media['object_key'])
        if core['MODE']!='development' or not p.is_file():fail(core,404,'Media unavailable.')
        return MediaResponse(p.read_bytes(),media['content_type'])
    if re.fullmatch('/profiles/[A-Za-z0-9_-]+',part) and method=='GET':return profile(db,part.split('/')[-1],uid,core)
    if part=='/players' and method=='GET':
        query=text(core,q('q'),80);mode=q('mode');target=q('user',uid or '')
        if mode in ('followers','following','squad'):
            p=profile_row(db,target)
            if not visible_profile(db,p,uid):fail(core,404,'Showcase unavailable.')
            target=p['id']
            if mode=='squad' and uid!=target:fail(core,403,'Your squad list is private.')
        where=["u.suspended=0","(LOWER(cp.handle) LIKE ? OR LOWER(u.display_name) LIKE ?)"]
        args=['%'+query.lower()+'%']*2
        where.append("(u.id=? OR (cp.visibility='public' OR (cp.visibility='followers' AND EXISTS(SELECT 1 FROM community_follows f WHERE f.user_id=? AND f.target_id=u.id))))")
        args += [uid or '',uid or '']
        where.append("NOT EXISTS(SELECT 1 FROM community_blocks b WHERE (b.user_id=? AND b.target_id=u.id) OR (b.target_id=? AND b.user_id=u.id))")
        args += [uid or '',uid or '']
        if mode in ('following','followers','squad'):
            table='community_squad' if mode=='squad' else 'community_follows'
            where.append(f'EXISTS(SELECT 1 FROM {table} f WHERE '+('f.target_id=? AND f.user_id=u.id)' if mode=='followers' else 'f.user_id=? AND f.target_id=u.id)'))
            args.append(target)
        ids=[r['id'] for r in db.execute('SELECT u.id FROM users u JOIN community_profiles cp ON cp.user_id=u.id WHERE '+' AND '.join(where)+' ORDER BY cp.handle LIMIT 24',args)]
        authors=author_views(db,ids,uid)
        return {'players':[authors[i] for i in ids]}

    if re.fullmatch('/profiles/[A-Za-z0-9_-]+/(follow|block|squad)',part) and method=='POST':
        uid=ensure_profile(db,ctx,core);target=part.split('/')[2];action=part.split('/')[-1]
        p=profile_row(db,target)
        if not p or p['id']==uid:fail(core,400,'Choose another player.')
        target=p['id'];enabled=data.get('enabled')
        if type(enabled) is not bool:fail(core,400,'Choose enabled or disabled.')
        if action!='block' and not visible_profile(db,p,uid):fail(core,404,'Showcase unavailable.')
        table={'follow':'community_follows','block':'community_blocks','squad':'community_squad'}[action]
        db.execute('BEGIN IMMEDIATE')
        try:
            if enabled: db.execute(f'INSERT INTO {table}(user_id,target_id) VALUES(?,?) ON CONFLICT DO NOTHING',(uid,target))
            else:db.execute(f'DELETE FROM {table} WHERE user_id=? AND target_id=?',(uid,target))
            if action=='block' and enabled:
                db.execute('DELETE FROM community_follows WHERE (user_id=? AND target_id=?) OR (user_id=? AND target_id=?)',(uid,target,target,uid))
                db.execute('DELETE FROM community_squad WHERE (user_id=? AND target_id=?) OR (user_id=? AND target_id=?)',(uid,target,target,uid))
                db.execute('DELETE FROM community_events WHERE (user_id=? AND actor_id=?) OR (user_id=? AND actor_id=?)',(uid,target,target,uid))
            if action=='follow' and enabled:event(db,target,uid,'follow')
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'ok':True,'enabled':enabled}
    if part=='/blocks' and method=='GET':
        core['require_user'](ctx)
        return {'players':[{'id':r['id'],'handle':r['handle'],'display_name':r['display_name']} for r in db.execute('SELECT u.id,u.display_name,p.handle FROM community_blocks b JOIN users u ON u.id=b.target_id JOIN community_profiles p ON p.user_id=u.id WHERE b.user_id=?',(uid,))]}
    if part=='/posts' and method=='GET':
        rule,params=acl(uid);where=["p.status='published'",rule];args=list(params)
        mode=q('mode');target=q('user');kind=q('kind');query=text(core,q('q'),80);game=q('game')
        if target:
            p=profile(db,target,uid,core);where+=['p.user_id=?'];args+=[p['id']]
        if mode=='drafts':
            core['require_user'](ctx);where[0]="p.status='draft'";where+=['p.user_id=?'];args+=[uid]
        if mode=='following':
            core['require_user'](ctx);where+=['EXISTS(SELECT 1 FROM community_follows f WHERE f.user_id=? AND f.target_id=p.user_id)'];args+=[uid]
        if mode=='saved':
            core['require_user'](ctx);where+=['EXISTS(SELECT 1 FROM community_saves s WHERE s.user_id=? AND s.post_id=p.id'+(' AND s.folder=?' if q('folder') else '')+')'];args+=[uid]+([q('folder')] if q('folder') else [])
        if kind in ('moment','item','achievement'):where+=['p.kind=?'];args+=[kind]
        if query:where+=['(LOWER(p.title) LIKE ? OR LOWER(p.body) LIKE ?)'];args+=['%'+query.lower()+'%']*2
        if game:where+=['p.game_slug=?'];args+=[game]
        try:offset=min(2000,max(0,int(q('offset','0'))))
        except ValueError:fail(core,400,'Invalid page.')
        rows=db.execute('SELECT p.* FROM community_posts p WHERE '+' AND '.join(where)+' ORDER BY p.created_at DESC,p.id DESC LIMIT 25 OFFSET ?',(*args,offset)).fetchall()
        posts=post_views(db,rows[:24],uid,core)
        if q('view')=='discover':
            discover_previews(db,posts,uid)
        return {'posts':posts,'next':offset+24 if len(rows)>24 and offset+24<=2000 else None}
    if part=='/posts' and method=='POST' or re.fullmatch('/posts/[A-Za-z0-9_-]+',part) and method=='PATCH':
        uid=ensure_profile(db,ctx,core);old=None
        if method=='PATCH':
            old=get_post(db,part.split('/')[-1],uid,core)
            if old['user_id']!=uid:fail(core,403,'Only the author can edit this post.')
        previous=db.execute('SELECT listing_id FROM community_post_state WHERE post_id=?',(old['id'],)).fetchone() if old else None
        source={**(dict(old) if old else {}),'listing_id':previous['listing_id'] if previous else None,**data}
        title=text(core,source.get('title',''),80,3);body=text(core,source.get('body',''),2000)
        kind=source.get('kind','moment');audience=source.get('audience','public');status=source.get('status','draft');game=source.get('game_slug','')
        if kind not in ('moment','item','achievement') or audience not in ('public','followers','private') or status not in ('published','draft'):fail(core,400,'Invalid post options.')
        if old and old['kind']!=kind:fail(core,400,'The post type cannot be changed.')
        if not db.execute('SELECT 1 FROM games WHERE slug=?',(game,)).fetchone():fail(core,400,'Choose a game.')
        if status=='published' and data.get('permission') is not True:fail(core,400,'Confirm you have permission to share this content.')
        media=source.get('media_id') or None;thumb=source.get('thumbnail_id') or None
        if 'media_ids' in data:
            media_ids=data['media_ids']
        elif old and 'media_id' not in data:
            media_ids=[r['media_id'] for r in db.execute('SELECT media_id FROM community_post_media WHERE post_id=? ORDER BY position',(old['id'],)).fetchall()] or ([media] if media else [])
        else:
            media_ids=[media] if media else []
        if not isinstance(media_ids,list) or any(not isinstance(mid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',mid) for mid in media_ids) or len(set(media_ids))!=len(media_ids):
            fail(core,400,'Choose unique uploaded images or one video.')
        media=media_ids[0] if media_ids else None
        media_types=[]
        for mid in media_ids+([thumb] if thumb else []):
            if mid and not db.execute('SELECT 1 FROM community_media WHERE id=? AND user_id=?',(mid,uid)).fetchone():fail(core,400,'Only your own uploaded media can be used.')
        for mid in media_ids:
            media_types.append(db.execute('SELECT content_type FROM community_media WHERE id=?',(mid,)).fetchone()['content_type'])
        if len(media_ids)>1 and any(m.startswith('video/') for m in media_types):
            fail(core,400,'Choose multiple images or a single video, not both.')
        if thumb and db.execute('SELECT content_type FROM community_media WHERE id=?',(thumb,)).fetchone()['content_type']!='image/webp':fail(core,400,'Choose an image thumbnail.')
        if status=='published' and not media and (kind=='item' or (kind=='moment' and not body)):
            fail(core,400,'Upload an image or a gameplay clip before publishing.')
        linked=source.get('linked_items',[])
        if isinstance(linked,str):linked=unpack(linked,[])
        if not isinstance(linked,list) or len(linked)>8:fail(core,400,'Tag up to 8 collection items.')
        for item in linked:
            if not isinstance(item,str) or not db.execute("SELECT 1 FROM community_posts WHERE id=? AND user_id=? AND kind='item' AND status='published'",(item,uid)).fetchone():fail(core,400,'Choose your published collection items.')
        comments=source.get('comments_enabled',True);pinned=source.get('pinned',False)
        if type(comments) not in (bool,int) or comments not in (0,1) or type(pinned) not in (bool,int) or pinned not in (0,1):fail(core,400,'Invalid post settings.')
        source.update(game_slug=game,kind=kind)
        lid=safety.prepare(db,uid,source,core)
        if media:
            stream=db.execute('SELECT state FROM community_streams WHERE media_id=?',(media,)).fetchone()
            if stream and status=='published' and stream['state']!='ready':fail(core,409,'Wait until video processing has finished.')
        requested=status
        result=None
        review_note=''
        if requested=='published':
            core['check_rate'](db,'community-safety-check',uid,20,3600)
            try: result=automatic.assess(db,uid,media_ids+([thumb] if thumb else []),json.dumps({'title':title,'body':body},ensure_ascii=False),core)
            except automatic.Unavailable as exc:
                # Queue new submissions privately. A failed edit keeps the existing version.
                incomplete_video = isinstance(exc, automatic.IncompleteVideoCheck)
                if old or str(exc)!=automatic.UNAVAILABLE or (incomplete_video and data.get('queue_for_review') is not True):
                    fail(core,503,str(exc))
                result=automatic.Result('pending')
                review_note=automatic.AWAITING_REVIEW
        status='published' if result and result.status=='approved' else 'hidden' if result and result.status=='rejected' else 'draft'
        pid=old['id'] if old else core['ident']()
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('''INSERT INTO community_posts(id,user_id,kind,title,body,game_slug,media_id,thumbnail_id,linked_items,audience,status,comments_enabled,pinned,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,body=excluded.body,game_slug=excluded.game_slug,
                media_id=excluded.media_id,thumbnail_id=excluded.thumbnail_id,linked_items=excluded.linked_items,audience=excluded.audience,status=excluded.status,
                comments_enabled=excluded.comments_enabled,pinned=excluded.pinned,updated_at=CURRENT_TIMESTAMP''',
                (pid,uid,kind,title,body,game,media,thumb,json.dumps(linked),audience,status,int(comments),int(pinned),
                 datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')))
            db.execute('DELETE FROM community_post_media WHERE post_id=?',(pid,))
            for position,mid in enumerate(media_ids):
                db.execute('INSERT INTO community_post_media(post_id,media_id,position) VALUES(?,?,?)',(pid,mid,position))
            safety.record_submission(db,pid,lid,requested,data.get('permission') is True,
                                     decision=result.status if result else None,note=review_note or (result.note if result else ''))
            if result:
                core['audit'](db,uid,'community.automatic_check','post',pid,
                              {'policy':automatic.POLICY_VERSION,'decision':result.status,'categories':list(result.categories)})
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return (200 if old else 201),post_view(db,get_post(db,pid,uid,core),uid,core)
    match=re.fullmatch('/posts/([A-Za-z0-9_-]+)(?:/(comments|like|save|report|related))?',part)
    if match:
        pid,action=match.groups()
        if not action and method=='DELETE':
            own=db.execute('SELECT user_id FROM community_posts WHERE id=?',(pid,)).fetchone()
            if own and own['user_id']==uid:
                db.execute('DELETE FROM community_posts WHERE id=?',(pid,));return {'ok':True}
        post=get_post(db,pid,uid,core)
        if action=='related' and method=='GET':
            rule,params=acl(uid)
            rows=db.execute("SELECT p.* FROM community_posts p WHERE p.status='published' AND p.id<>? AND p.user_id<>? AND p.user_id<>? AND p.media_id IS NOT NULL AND "+rule+
                " ORDER BY CASE WHEN p.game_slug=? THEN 0 ELSE 1 END,p.created_at DESC,p.id DESC LIMIT 12",(pid,post['user_id'],uid or '',*params,post['game_slug'])).fetchall()
            return {'posts':post_views(db,rows,uid,core)}
        if not action and method=='GET':return post_view(db,post,uid,core)
        if not action and method=='DELETE':
            if post['user_id']!=uid:fail(core,403,'Only the author can delete this post.')
            db.execute('DELETE FROM community_posts WHERE id=?',(pid,));return {'ok':True}
        if action=='comments' and method=='GET':
            rows=db.execute('SELECT c.*,u.display_name,cp.handle,COALESCE(av.value,\'\') avatar_url FROM community_comments c JOIN users u ON u.id=c.user_id JOIN community_profiles cp ON cp.user_id=u.id LEFT JOIN platform_config av ON av.key=\'public_avatar:\'||u.id WHERE c.post_id=? AND u.suspended=0 ORDER BY c.created_at DESC,c.id DESC LIMIT 100',(pid,)).fetchall()
            return {'comments':[dict(r) for r in rows if not blocked(db,uid,r['user_id'])]}
        if action=='comments' and method=='POST':
            ensure_profile(db,ctx,core)
            prefs=unpack(profile_row(db,post['user_id'])['preferences'],{})
            allowed=post['comments_enabled'] and (uid==post['user_id'] or prefs.get('comments','everyone')=='everyone' or (prefs.get('comments')=='following' and following(db,post['user_id'],uid)))
            if not allowed:fail(core,403,'Comments are closed for this post.')
            body=text(core,data.get('body',''),1000,1);cid=core['ident']()
            db.execute('INSERT INTO community_comments(id,user_id,post_id,body) VALUES(?,?,?,?)',(cid,uid,pid,body));event(db,post['user_id'],uid,'comment',pid)
            return 201,{'id':cid}
        if action in ('like','save') and method=='POST':
            ensure_profile(db,ctx,core);enabled=data.get('enabled')
            if type(enabled) is not bool:fail(core,400,'Choose enabled or disabled.')
            table='community_reactions' if action=='like' else 'community_saves'
            if enabled:
                if action=='save':db.execute('INSERT INTO community_saves(user_id,post_id,folder) VALUES(?,?,?) ON CONFLICT(user_id,post_id) DO UPDATE SET folder=excluded.folder',(uid,pid,text(core,data.get('folder','Favorites'),40,1)))
                else:db.execute('INSERT INTO community_reactions(user_id,post_id) VALUES(?,?) ON CONFLICT DO NOTHING',(uid,pid));event(db,post['user_id'],uid,'reaction',pid)
            else:db.execute(f'DELETE FROM {table} WHERE user_id=? AND post_id=?',(uid,pid))
            return {'ok':True,'enabled':enabled}
        if action=='report' and method=='POST':
            if post['status']!='published':fail(core,400,'Only published posts can be reported.')
            reason=data.get('reason')
            if reason not in ('copyright','harassment','spam','unsafe','other'):fail(core,400,'Choose a reason.')
            db.execute('INSERT INTO community_reports(id,user_id,post_id,reason,body) VALUES(?,?,?,?,?) ON CONFLICT(user_id,post_id) DO NOTHING',(core['ident'](),uid,pid,reason,text(core,data.get('body',''),1000)))
            return {'ok':True}
    if re.fullmatch('/comments/[A-Za-z0-9_-]+',part) and method=='DELETE':
        cid=part.split('/')[-1];c=db.execute('SELECT c.*,p.user_id author FROM community_comments c JOIN community_posts p ON p.id=c.post_id WHERE c.id=?',(cid,)).fetchone()
        if not c:fail(core,404,'Comment unavailable.')
        if uid not in (c['user_id'],c['author']):fail(core,403,'You cannot remove this comment.')
        db.execute('DELETE FROM community_comments WHERE id=?',(cid,));return {'ok':True}
    if part=='/folders' and method=='POST':
        name=text(core,data.get('name',''),40,1)
        db.execute('INSERT INTO community_folders(user_id,name) VALUES(?,?) ON CONFLICT DO NOTHING',(uid,name))
        return 201,{'name':name}
    if part=='/folders' and method=='GET':
        core['require_user'](ctx)
        rule,params=acl(uid)
        return {'folders':sorted(set([r['name'] for r in db.execute('SELECT name FROM community_folders WHERE user_id=?',(uid,))]+[r['folder'] for r in db.execute('SELECT DISTINCT s.folder FROM community_saves s JOIN community_posts p ON p.id=s.post_id WHERE s.user_id=? AND p.status=\'published\' AND '+rule+' ORDER BY s.folder',(uid,*params))]))}
    if part=='/notifications' and method=='GET':
        core['require_user'](ctx)
        rows=db.execute('SELECT e.*,u.display_name,p.handle,COALESCE(av.value,\'\') avatar_url FROM community_events e JOIN users u ON u.id=e.actor_id JOIN community_profiles p ON p.user_id=u.id LEFT JOIN platform_config av ON av.key=\'public_avatar:\'||u.id WHERE e.user_id=? AND u.suspended=0 ORDER BY e.created_at DESC,e.id DESC LIMIT 100',(uid,)).fetchall()
        out=[]
        for r in rows:
            if blocked(db,uid,r['actor_id']):continue
            if r['post_id']:
                try:get_post(db,r['post_id'],uid,core)
                except core['HttpError']:continue
            out.append(dict(r))
        return {'notifications':out}
    if part=='/notifications/read' and method=='POST':
        event_id=data.get('id')
        if event_id is None:
            db.execute('UPDATE community_events SET seen=1 WHERE user_id=? AND seen=0',(uid,))
        else:
            if not isinstance(event_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',event_id):
                fail(core,400,'Invalid ID.')
            db.execute('UPDATE community_events SET seen=1 WHERE user_id=? AND id=? AND seen=0',(uid,event_id))
        return {'ok':True}
    fail(core,404,'Not found.')

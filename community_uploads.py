"""Private R2 uploads, with disk-backed validation independent of HTTP body size.

Development alone uses ordered HTTP chunks. Production sends the file straight
from the browser to an expiring R2 PUT lease; only JSON goes through Vercel.
"""
import json
import math
import re
import secrets
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

# R2's single-PUT service boundary, not a marketing/account upload allowance.
R2_PUT_MAX = 5 * 1024**3
SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS community_uploads (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        object_key TEXT NOT NULL UNIQUE, content_type TEXT NOT NULL, byte_size BIGINT NOT NULL,
        received BIGINT NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'uploading',
        media_id TEXT REFERENCES community_media(id) ON DELETE SET NULL,
        expires_at BIGINT NOT NULL, claim TEXT NOT NULL DEFAULT '', claim_until BIGINT NOT NULL DEFAULT 0)''',
    '''CREATE TABLE IF NOT EXISTS community_media_checks (
        media_id TEXT PRIMARY KEY REFERENCES community_media(id) ON DELETE CASCADE,
        duration REAL NOT NULL, cursor_seconds REAL NOT NULL DEFAULT 0,
        caption_hash TEXT NOT NULL DEFAULT '', policy TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL DEFAULT 'unchecked', categories TEXT NOT NULL DEFAULT '[]', uncertain INTEGER NOT NULL DEFAULT 0,
        claim TEXT NOT NULL DEFAULT '', claim_until BIGINT NOT NULL DEFAULT 0)''',
    'CREATE INDEX IF NOT EXISTS community_upload_expiry ON community_uploads(expires_at)',
)
TABLES = ('community_uploads','community_media_checks')
MIMES = ('image/jpeg','image/png','image/webp','video/mp4')


def staging_path(core, key):
    return Path(str(core['DB_PATH'])+'.community-staging')/key.replace('/','_')


def normalize(source, target, mime, core):
    """Decode raster images; remux MP4 streams and strip private metadata.

    No 4 MB or 30-second cutoff. Disk/memory/CPU bounds and format checks remain.
    The old dispute-evidence normalizer is deliberately left untouched.
    """
    if mime.startswith('image/'):
        import warnings
        from PIL import Image, ImageOps
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(source) as image:
                    if image.format != {'image/jpeg':'JPEG','image/png':'PNG','image/webp':'WEBP'}[mime] or getattr(image,'is_animated',False):
                        raise ValueError('Invalid image')
                    if image.width*image.height>20_000_000:
                        raise ValueError('Image dimensions exceed the safe decoding budget')
                    image.load()
                    image=ImageOps.exif_transpose(image).convert('RGB')
                    image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
                    image.save(target,format='WEBP',quality=82,method=5)
            return 'image/webp',0
        except Exception:
            raise core['HttpError'](400,'The image could not be decoded. Choose a valid JPG, PNG or WebP.') from None
    try:
        import imageio_ffmpeg
        ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
        with source.open('rb') as stream:
            header=stream.read(12)
        if len(header)<12 or header[4:8]!=b'ftyp':
            raise ValueError('Invalid MP4')
        base=[ffmpeg,'-nostdin','-hide_banner','-protocol_whitelist','file,pipe','-max_alloc','33554432','-threads','1','-f','mov','-enable_drefs','0','-use_absolute_path','0','-i',str(source)]
        with tempfile.TemporaryFile() as log:
            subprocess.run(base,stdout=subprocess.DEVNULL,stderr=log,timeout=6,check=False)
            log.seek(0);probe=log.read(65536).decode('utf-8','replace')
        duration=re.search(r'Duration: (\d+):(\d+):(\d+(?:\.\d+)?)',probe)
        dimensions=re.search(r'Video: [^\n]*?\b(\d{2,5})x(\d{2,5})\b',probe)
        if not duration or not dimensions or math.prod(map(int,dimensions.groups()))>20_000_000:
            raise ValueError('Invalid video dimensions or duration')
        seconds=int(duration[1])*3600+int(duration[2])*60+float(duration[3])
        if not math.isfinite(seconds) or seconds<=0:raise ValueError('Invalid duration')
        # Copy streams rather than truncating/re-encoding an entire long video.
        # Restrict all input protocols/references and explicitly remove metadata.
        result=subprocess.run(base+['-loglevel','error','-map','0:v:0','-map','0:a:0?','-c','copy','-map_metadata','-1','-map_metadata:s','-1','-map_chapters','-1','-movflags','+faststart','-f','mp4','-y',str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=90,check=False)
        if result.returncode or not target.is_file() or target.stat().st_size<20:raise ValueError('Invalid MP4')
        return 'video/mp4',seconds
    except (ValueError,OSError,subprocess.TimeoutExpired):
        raise core['HttpError'](400,'The video could not be processed. Try another MP4.') from None
    except ImportError:
        raise core['HttpError'](503,'The video processor is not available.') from None


def route(handler,db,ctx,method,path,qs,data,raw,core):
    import community as c
    check=re.fullmatch(r'/api/community/media/([A-Za-z0-9_-]+)/check',path)
    if check and method=='POST':return check_video(db,ctx,check[1],data,core)
    match=re.fullmatch(r'/api/community/uploads(?:/([A-Za-z0-9_-]+)/(chunk|complete))?',path)
    if not match:return c.UNHANDLED
    uid=c.ensure_profile(db,ctx,core);storage=core['storage_r2'];remote=storage.is_configured()
    if not remote and core['MODE']!='development':c.fail(core,503,'Media storage is unavailable. Try again later.')
    upload_id,action=match.groups()
    if method=='POST' and not upload_id:
        size=data.get('size');mime=data.get('content_type')
        if type(size) is not int or not 0<size<=R2_PUT_MAX:c.fail(core,400,'The file exceeds the storage provider’s single-upload capacity.')
        if mime not in MIMES:c.fail(core,415,'Choose JPG, PNG, WebP or MP4 media.')
        core['check_rate'](db,'community-upload',uid,20,3600)
        upload_id=core['ident']();key=secrets.token_hex(12)+'/'+secrets.token_hex(24)+'.webp'
        url=storage.evidence_upload_url(key,size) if remote else ''
        db.execute('INSERT INTO community_uploads(id,user_id,object_key,content_type,byte_size,expires_at) VALUES(?,?,?,?,?,?)',(upload_id,uid,key,mime,size,int(time.time())+3600))
        return 201,{'id':upload_id,'upload_url':url,'direct':remote}
    row=db.execute('SELECT * FROM community_uploads WHERE id=? AND user_id=?',(upload_id,uid)).fetchone()
    if not row:c.fail(core,404,'Upload unavailable.')
    if row['state']=='complete' and action=='complete':
        media=db.execute('SELECT * FROM community_media WHERE id=?',(row['media_id'],)).fetchone()
        if media:return {'id':media['id'],'url':'/api/community/media/'+media['id'],'content_type':media['content_type']}
    if row['expires_at']<time.time():c.fail(core,410,'Upload expired. Choose the file again.')
    if method=='POST' and action=='chunk':
        if remote:c.fail(core,400,'Use the signed upload destination.')
        try:offset=int(qs.get('offset',[''])[0])
        except (ValueError,TypeError):c.fail(core,400,'Invalid upload offset.')
        if not raw or len(raw)>4*1024*1024 or offset<0 or offset+len(raw)>row['byte_size']:c.fail(core,400,'Invalid upload chunk.')
        if shutil.disk_usage(tempfile.gettempdir()).free<len(raw)+64*1024*1024:c.fail(core,503,'Media processing capacity is temporarily unavailable. Try again later.')
        source=staging_path(core,row['object_key']);source.parent.mkdir(parents=True,exist_ok=True)
        db.execute('BEGIN IMMEDIATE')
        try:
            current=db.execute('SELECT received,state FROM community_uploads WHERE id=?',(upload_id,)).fetchone()
            if current['state']!='uploading' or current['received']!=offset:c.fail(core,409,'Invalid upload offset.')
            with source.open('r+b' if source.exists() else 'w+b') as stream:
                stream.seek(offset);stream.truncate();stream.write(raw)
            db.execute('UPDATE community_uploads SET received=? WHERE id=?',(offset+len(raw),upload_id));db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'offset':offset+len(raw)}
    if method!='POST' or action!='complete':c.fail(core,405,'Method not allowed.')
    claim=secrets.token_hex(16);now=int(time.time())
    claimed=db.execute("UPDATE community_uploads SET claim=?,claim_until=?,state='processing' WHERE id=? AND state<>'complete' AND claim_until<?",(claim,now+180,upload_id,now)).rowcount
    if not claimed:c.fail(core,409,'The file is being processed. Try again shortly.')
    key=secrets.token_hex(12)+'/'+secrets.token_hex(24)+'.webp';stored=False
    try:
        with tempfile.TemporaryDirectory(prefix='sl-upload-') as directory:
            source=Path(directory)/'source';target=Path(directory)/'normalized'
            if remote:
                required=row['byte_size']+(row['byte_size'] if row['content_type']=='video/mp4' else 8*1024*1024)+64*1024*1024
                if shutil.disk_usage(directory).free<required:c.fail(core,503,'Media processing capacity is temporarily unavailable. Try again later.')
                storage.download_evidence(row['object_key'],source,row['byte_size'])
            else:
                source=staging_path(core,row['object_key'])
                if row['received']!=row['byte_size'] or not source.is_file() or source.stat().st_size!=row['byte_size']:c.fail(core,409,'The upload is incomplete.')
            mime,duration=normalize(source,target,row['content_type'],core)
            size=target.stat().st_size
            if remote:
                with target.open('rb') as stream:storage.put_private_media(key,stream,mime)
            else:
                destination=c.disk_path(core,key);destination.parent.mkdir(parents=True,exist_ok=True)
                target.replace(destination)
            stored=True;mid=core['ident']()
            db.execute('BEGIN IMMEDIATE')
            try:
                if not db.execute('SELECT 1 FROM community_uploads WHERE id=? AND claim=?',(upload_id,claim)).fetchone():c.fail(core,409,'Upload processing changed. Try again.')
                db.execute('INSERT INTO community_media(id,user_id,object_key,content_type,byte_size) VALUES(?,?,?,?,?)',(mid,uid,key,mime,size))
                if mime=='video/mp4':db.execute('INSERT INTO community_media_checks(media_id,duration) VALUES(?,?)',(mid,duration))
                db.execute("UPDATE community_uploads SET state='complete',media_id=?,claim='',claim_until=0 WHERE id=?",(mid,upload_id));db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        try:
            if remote:storage.delete_evidence(row['object_key'])
            else:staging_path(core,row['object_key']).unlink(missing_ok=True)
        except Exception:pass # Retention retries cleanup; final media is already committed.
        return {'id':mid,'url':'/api/community/media/'+mid,'content_type':mime}
    except Exception as exc:
        if stored:
            try:
                if remote:storage.delete_evidence(key)
                else:c.disk_path(core,key).unlink(missing_ok=True)
            except Exception:pass
        db.execute("UPDATE community_uploads SET state='uploading',claim='',claim_until=0 WHERE id=? AND claim=?",(upload_id,claim))
        if isinstance(exc,core['HttpError']):raise
        c.fail(core,503,'Upload failed. Your post has not been published. Try again.')


def segment_frames(source, start):
    """Decode a bounded chronological segment. Source comes only from our storage."""
    import imageio_ffmpeg
    import community_moderation as automatic
    with tempfile.TemporaryDirectory(prefix='sl-check-') as directory:
        root=Path(directory)
        remote=isinstance(source,str) and source.startswith('https://')
        args=[imageio_ffmpeg.get_ffmpeg_exe(),'-nostdin','-hide_banner','-loglevel','error',
              '-protocol_whitelist','https,tls,tcp,crypto' if remote else 'file,pipe',
              '-max_alloc','33554432','-threads','1','-ss',str(start),'-f','mov',
              '-enable_drefs','0','-use_absolute_path','0','-i',str(source),
              '-an','-t','16','-vf','fps=1,scale=512:512:force_original_aspect_ratio=decrease',
              '-frames:v','16','-q:v','3',str(root/'frame-%02d.jpg')]
        result=subprocess.run(args,capture_output=True,timeout=12,check=False)
        frames=sorted(root.glob('frame-*.jpg'))
        if not frames and result.returncode==0:
            # A sub-second tail still needs one decoded frame.
            args=args[:args.index('-an')]+['-an','-vf','scale=512:512:force_original_aspect_ratio=decrease','-frames:v','1','-y',str(root/'fallback.jpg')]
            result=subprocess.run(args,capture_output=True,timeout=8,check=False)
            frames=[root/'fallback.jpg'] if (root/'fallback.jpg').is_file() else []
        if result.returncode or not frames:raise automatic.Unavailable(automatic.UNAVAILABLE)
        return [automatic.image_frame(p.read_bytes()) for p in frames]


def check_video(db,ctx,mid,data,core):
    import hashlib
    import community as c
    import community_moderation as automatic
    uid=c.ensure_profile(db,ctx,core)
    if data.get('permission') is not True:c.fail(core,400,'Confirm you have permission to share this content.')
    caption=json.dumps({'title':c.text(core,data.get('title',''),80,3),'body':c.text(core,data.get('body',''),2000)},ensure_ascii=False)
    digest=hashlib.sha256(caption.encode()).hexdigest()
    row=db.execute("SELECT m.object_key FROM community_media m WHERE m.id=? AND m.user_id=? AND m.content_type='video/mp4'",(mid,uid)).fetchone()
    if not row:c.fail(core,404,'Media is private or unavailable.')
    check=db.execute('SELECT * FROM community_media_checks WHERE media_id=?',(mid,)).fetchone()
    if not check:return {'done':True,'state':'legacy'}
    if not automatic.configured():
        raise core['HttpError'](503,automatic.UNAVAILABLE,{'code':'community_safety_unavailable'})
    now=int(time.time());claim=secrets.token_hex(16)
    if check['caption_hash']!=digest or check['policy']!=automatic.POLICY_VERSION:
        core['check_rate'](db,'community-safety-start',uid,20,3600)
    db.execute("UPDATE community_media_checks SET cursor_seconds=0,state='unchecked',categories='[]',uncertain=0,caption_hash=?,policy=?,claim='',claim_until=0 WHERE media_id=? AND (caption_hash<>? OR policy<>?)",(digest,automatic.POLICY_VERSION,mid,digest,automatic.POLICY_VERSION))
    check=db.execute('SELECT * FROM community_media_checks WHERE media_id=?',(mid,)).fetchone()
    if check['state'] in ('approved','rejected','pending'):return {'done':True,'state':check['state'],'progress':100}
    claimed=db.execute('UPDATE community_media_checks SET claim=?,claim_until=? WHERE media_id=? AND claim_until<?',(claim,now+60,mid,now)).rowcount
    if not claimed:c.fail(core,409,'The file is being processed. Try again shortly.')
    try:
        storage=core['storage_r2']
        source=storage.evidence_url(row['object_key']) if storage.is_configured() else c.disk_path(core,row['object_key'])
        result=automatic.classify(caption,segment_frames(source,check['cursor_seconds']))
        cursor=min(check['duration'],check['cursor_seconds']+16)
        uncertain=int(check['uncertain'] or result.status=='pending')
        state='rejected' if result.status=='rejected' else ('pending' if uncertain else 'approved') if cursor>=check['duration'] else 'checking'
        changed=db.execute("UPDATE community_media_checks SET cursor_seconds=?,state=?,categories=?,uncertain=?,claim='',claim_until=0 WHERE media_id=? AND claim=? AND caption_hash=? AND policy=?",(cursor,state,json.dumps(result.categories),uncertain,mid,claim,digest,automatic.POLICY_VERSION)).rowcount
        if not changed:c.fail(core,409,'The post changed. Open it again before reviewing.')
        return {'done':state in ('approved','rejected','pending'),'state':state,'progress':round(cursor/check['duration']*100)}
    except Exception as exc:
        db.execute("UPDATE community_media_checks SET claim='',claim_until=0 WHERE media_id=? AND claim=?",(mid,claim))
        if isinstance(exc,core['HttpError']):raise
        raise core['HttpError'](503,automatic.UNAVAILABLE,{'code':'community_safety_unavailable'}) from None


def cleanup(db,core,uid=None):
    """Remove expired staged originals, including uploads abandoned before finalize."""
    where='user_id=?' if uid else 'expires_at<? AND claim_until<?'
    values=(uid,) if uid else (int(time.time()),int(time.time()))
    rows=db.execute('SELECT id,object_key FROM community_uploads WHERE '+where+' ORDER BY expires_at LIMIT '+('10000' if uid else '20'),values).fetchall()
    removed=0
    for row in rows:
        try:
            if core['storage_r2'].is_configured():core['storage_r2'].delete_evidence(row['object_key'])
            else:staging_path(core,row['object_key']).unlink(missing_ok=True)
            db.execute('DELETE FROM community_uploads WHERE id=?',(row['id'],));removed+=1
        except Exception:
            if uid:raise
    return removed

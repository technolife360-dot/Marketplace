"""Account security and auditable marketplace operations; no payment adapters."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UNHANDLED=object()
TABLES=('account_security','security_recovery_codes','pending_email_changes','seller_availability','user_blocks','support_tickets','support_entries','dispute_entries','dispute_attachments','order_deadline_notices')
SCHEMA=(
 """CREATE TABLE IF NOT EXISTS account_security(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,secret_cipher TEXT NOT NULL DEFAULT '',pending_cipher TEXT NOT NULL DEFAULT '',pending_expires TEXT,enabled INTEGER NOT NULL DEFAULT 0,last_step BIGINT NOT NULL DEFAULT -1)""",
 """CREATE TABLE IF NOT EXISTS security_recovery_codes(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,code_hash TEXT NOT NULL,used_at TEXT,PRIMARY KEY(user_id,code_hash))""",
 """CREATE TABLE IF NOT EXISTS pending_email_changes(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,new_email TEXT NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
 """CREATE TABLE IF NOT EXISTS seller_availability(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,timezone TEXT NOT NULL DEFAULT 'UTC',hours_json TEXT NOT NULL DEFAULT '[]',vacation INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
 """CREATE TABLE IF NOT EXISTS user_blocks(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,blocked_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,blocked_id),CHECK(user_id<>blocked_id))""",
 """CREATE TABLE IF NOT EXISTS support_tickets(id TEXT PRIMARY KEY,requester_id TEXT NOT NULL REFERENCES users(id),order_id TEXT REFERENCES orders(id),subject TEXT NOT NULL,category TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
 """CREATE TABLE IF NOT EXISTS support_entries(id TEXT PRIMARY KEY,ticket_id TEXT NOT NULL REFERENCES support_tickets(id) ON DELETE CASCADE,sender_id TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
 """CREATE TABLE IF NOT EXISTS dispute_entries(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),sender_id TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
 """CREATE TABLE IF NOT EXISTS dispute_attachments(entry_id TEXT PRIMARY KEY REFERENCES dispute_entries(id) ON DELETE CASCADE,owner_id TEXT NOT NULL REFERENCES users(id),object_path TEXT NOT NULL UNIQUE)""",
 """CREATE TABLE IF NOT EXISTS order_deadline_notices(order_item_id TEXT NOT NULL REFERENCES order_items(id),kind TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(order_item_id,kind))""",
 'CREATE INDEX IF NOT EXISTS idx_support_owner ON support_tickets(requester_id,updated_at)',
 'CREATE INDEX IF NOT EXISTS idx_support_entries ON support_entries(ticket_id,created_at)',
 'CREATE INDEX IF NOT EXISTS idx_dispute_entries ON dispute_entries(order_id,created_at)',
 'CREATE INDEX IF NOT EXISTS idx_blocks_reverse ON user_blocks(blocked_id,user_id)',
)
COLUMNS={
 'sessions':{'created_at':"TEXT NOT NULL DEFAULT ''",'last_seen_at':"TEXT NOT NULL DEFAULT ''",'user_agent':"TEXT NOT NULL DEFAULT ''",'network_label':"TEXT NOT NULL DEFAULT ''",'mfa_verified':'INTEGER NOT NULL DEFAULT 0'},
 'order_items':{'snapshot_json':"TEXT NOT NULL DEFAULT '{}'",'delivery_due_at':'TEXT'},
 'reports':{'response_due_at':'TEXT'},
}

def utc(value):
    parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)

def iso(value):return value.astimezone(timezone.utc).isoformat(timespec='seconds')

def migrate(db,postgres=False):
    for statement in SCHEMA:db.execute(statement)
    for table,fields in COLUMNS.items():
        known=set() if postgres else {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
        for field,definition in fields.items():
            if postgres:db.execute(f'ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS {field} {definition}')
            elif field not in known:db.execute(f'ALTER TABLE {table} ADD COLUMN {field} {definition}')
    db.execute("UPDATE sessions SET created_at=CURRENT_TIMESTAMP,last_seen_at=CURRENT_TIMESTAMP WHERE created_at=''")
    if postgres:
        for table in TABLES:
            db.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            db.execute(f'REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated')
    # Existing orders are explicitly marked as legacy snapshots; never silently
    # replace an already captured promise with a newly edited listing.
    for row in db.execute("SELECT id,listing_id FROM order_items WHERE snapshot_json='{}'").fetchall():snapshot_item(db,row['id'],row['listing_id'],legacy=True)

def totp(secret,step,digits=6,digest=hashlib.sha1):
    key=base64.b32decode(secret+'='*((8-len(secret)%8)%8))
    value=hmac.new(key,struct.pack('>Q',step),digest).digest();offset=value[-1]&15
    return str((struct.unpack('>I',value[offset:offset+4])[0]&0x7fffffff)%(10**digits)).zfill(digits)

def enabled(db,uid):
    r=db.execute('SELECT enabled FROM account_security WHERE user_id=?',(uid,)).fetchone()
    return bool(r and r['enabled'])

def encrypt(value,uid,core):
    try:return core['delivery_crypto'].encrypt_payload(value,'account-security:'+uid)
    except core['delivery_crypto'].DeliveryCryptoError as exc:raise core['HttpError'](503,'Xavfsizlik kalitini saqlash xizmati tayyor emas.') from exc

def decrypt(value,uid,core):
    try:return core['delivery_crypto'].decrypt_payload(value,'account-security:'+uid)
    except core['delivery_crypto'].DeliveryCryptoError as exc:raise core['HttpError'](503,'Xavfsizlik kalitini ochib bo‘lmadi.') from exc

def consume_otp(db,uid,code,core):
    if not isinstance(code,str) or len(code)>50:return False
    row=db.execute('SELECT * FROM account_security WHERE user_id=? AND enabled=1',(uid,)).fetchone()
    if not row:return False
    code=code.strip().replace(' ','')
    if re.fullmatch(r'[0-9]{6}',code):
        secret=decrypt(row['secret_cipher'],uid,core);step=int(time.time())//30
        for candidate in (step,step-1,step+1):
            if candidate>row['last_step'] and hmac.compare_digest(totp(secret,candidate),code):
                return db.execute('UPDATE account_security SET last_step=? WHERE user_id=? AND last_step<? AND enabled=1',(candidate,uid,candidate)).rowcount==1
    code_hash=hashlib.sha256(code.upper().encode()).hexdigest()
    return db.execute('UPDATE security_recovery_codes SET used_at=CURRENT_TIMESTAMP WHERE user_id=? AND code_hash=? AND used_at IS NULL',(uid,code_hash)).rowcount==1

def reauthenticate(db,uid,data,core):
    core['check_rate'](db,'security_reauth',uid,8,300)
    row=db.execute('SELECT password_hash FROM users WHERE id=?',(uid,)).fetchone()
    if not isinstance(data.get('password'),str) or not core['password_ok'](data['password'],row['password_hash']):raise core['HttpError'](403,'Amaldagi sayt parolini kiriting. Google/Facebook ishlatsangiz, avval parolni tiklash orqali sayt parolini yarating.')
    if enabled(db,uid) and not consume_otp(db,uid,data.get('otp'),core):raise core['HttpError'](403,'Authenticator yoki ishlatilmagan tiklash kodi kerak.')

def security_notice(db,uid,title,core,address=None):
    core['notify'](db,uid,'security',title,'Bu amalni siz bajarmagan bo‘lsangiz, yordam xizmatiga murojaat qiling.','/account')
    row=db.execute('SELECT email,display_name FROM users WHERE id=?',(uid,)).fetchone()
    if row and core['email_service'].is_configured():
        try:core['email_service'].send_security_update(address or row['email'],row['display_name'],title)
        except Exception:core['audit'](db,uid,'security_email_failed','user',uid)

def blocked(db,a,b):return bool(db.execute('SELECT 1 FROM user_blocks WHERE (user_id=? AND blocked_id=?) OR (user_id=? AND blocked_id=?)',(a,b,b,a)).fetchone())

def chat_allowed(db,conv,uid,core):
    other=conv['seller_id'] if uid==conv['buyer_id'] else conv['buyer_id']
    if not blocked(db,uid,other):return
    active="('paid','awaiting_delivery','delivered','under_review','disputed')"
    if conv['order_id']:
        if db.execute(f'SELECT 1 FROM orders WHERE id=? AND status IN {active}',(conv['order_id'],)).fetchone():return
    elif conv['listing_id']:
        if db.execute(f'SELECT 1 FROM orders o JOIN order_items i ON i.order_id=o.id WHERE o.buyer_id=? AND i.seller_id=? AND i.listing_id=? AND o.status IN {active}',(conv['buyer_id'],conv['seller_id'],conv['listing_id'])).fetchone():return
    raise core['HttpError'](403,'Bu foydalanuvchi bilan yangi suhbat yoki savdo bloklangan. Faol buyurtma bo‘yicha yozishmalar saqlanadi.')

def availability(db,sid):
    row=db.execute('SELECT * FROM seller_availability WHERE user_id=?',(sid,)).fetchone()
    return {'timezone':row['timezone'],'hours':json.loads(row['hours_json']),'vacation':bool(row['vacation'])} if row else {'timezone':'UTC','hours':[],'vacation':False}

def next_open(settings,moment):
    hours=settings.get('hours',[])
    if not hours:return moment
    zone=ZoneInfo(settings.get('timezone','UTC'));local=moment.astimezone(zone);options=[]
    for delta in range(8):
        day=local.date()+timedelta(days=delta)
        for window in hours:
            if day.weekday()!=window['day']:continue
            start=datetime.combine(day,datetime.strptime(window['start'],'%H:%M').time(),zone)
            end=datetime.combine(day,datetime.strptime(window['end'],'%H:%M').time(),zone)
            if start<=local<end:return moment
            if start>local:options.append(start.astimezone(timezone.utc))
    return min(options) if options else moment

def snapshot_item(db,iid,lid,legacy=False,source=None):
    row=source if source is not None else db.execute('SELECT * FROM listings WHERE id=?',(lid,)).fetchone()
    if not row:return
    attrs=json.loads(row['attributes_json'] or '{}')
    data={k:row[k] for k in ('title','description','game_id','product_type','platform','region','delivery_method','delivery_eta','delivery_minutes','requirements','price_minor','currency','image_url')}
    data['attributes']={k:v for k,v in attrs.items() if not k.startswith('_')};data['availability']=availability(db,row['seller_id']);data['legacy']=legacy
    db.execute("UPDATE order_items SET snapshot_json=? WHERE id=? AND snapshot_json='{}'",(json.dumps(data,ensure_ascii=False),iid))

def deadline_setup(db,oid):
    paid=db.execute("SELECT MIN(created_at) at FROM order_events WHERE order_id=? AND to_status IN ('paid','awaiting_delivery')",(oid,)).fetchone()['at']
    if not paid:return
    for row in db.execute('SELECT id,snapshot_json FROM order_items WHERE order_id=? AND delivery_due_at IS NULL',(oid,)).fetchall():
        data=json.loads(row['snapshot_json'] or '{}');minutes=data.get('delivery_minutes')
        if minutes and minutes>0 and not data.get('legacy'):
            due=next_open(data.get('availability',{}),utc(paid))+timedelta(minutes=minutes)
            db.execute('UPDATE order_items SET delivery_due_at=? WHERE id=? AND delivery_due_at IS NULL',(iso(due),row['id']))

def deadline_run(db,core,moment=None):
    moment=moment or datetime.now(timezone.utc);count=0
    for order in db.execute("SELECT id,reference,buyer_id FROM orders WHERE status IN ('paid','awaiting_delivery') ORDER BY created_at LIMIT 1000").fetchall():
        deadline_setup(db,order['id'])
        for item in db.execute('SELECT i.* FROM order_items i LEFT JOIN deliveries d ON d.order_item_id=i.id WHERE i.order_id=? AND d.id IS NULL AND i.delivery_due_at IS NOT NULL',(order['id'],)).fetchall():
            due=utc(item['delivery_due_at']);remaining=(due-moment).total_seconds()
            duration=json.loads(item['snapshot_json'] or '{}').get('delivery_minutes') or 60
            kind='late' if remaining<0 else 'reminder' if remaining<=min(1800,max(60,duration*12)) else None
            if not kind:continue
            db.execute('BEGIN IMMEDIATE')
            try:
                changed=db.execute('INSERT INTO order_deadline_notices(order_item_id,kind) VALUES(?,?) ON CONFLICT(order_item_id,kind) DO NOTHING',(item['id'],kind))
                if changed.rowcount!=1:
                    db.execute('COMMIT');continue
                title='Yetkazish muddati o‘tdi' if kind=='late' else 'Yetkazish muddati yaqinlashmoqda'
                for target in {item['seller_id'],order['buyer_id']}:core['notify'](db,target,'delivery_deadline',title,order['reference']+' · '+item['title'],'/order/'+order['id'])
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
            count+=1
    core['audit'](db,None,'cron_order_deadlines_ok','system','deadlines',{'notices':count})
    return {'ok':True,'notices':count}

def order_member(db,oid,uid,core):
    row=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
    if not row or not (uid==row['buyer_id'] or core['is_admin'](db,uid) or db.execute('SELECT 1 FROM order_items WHERE order_id=? AND seller_id=?',(oid,uid)).fetchone()):raise core['HttpError'](404,'Buyurtma topilmadi.')
    return row

def quality(item):
    problems=[]
    if len(item['title'].split())<3:problems.append('Sarlavhada mahsulot nomi va asosiy xususiyatini yozing.')
    if len(item['description'].strip())<60:problems.append('Tavsifni kamida 60 belgi bilan aniq yozing.')
    attrs=json.loads(item['attributes_json'] or '{}')
    if item['product_type']=='item' and not attrs.get('item_name'):problems.append('Buyumning aniq nomini kiriting.')
    if not item['platform'] or not item['region']:problems.append('Platforma va hududni tanlang.')
    if not item['requirements'].strip():problems.append('Nima yetkazilishi va xaridorga kerakli shartlarni kiriting.')
    if not item['image_url']:problems.append('Mahsulotning haqiqiy rasmini qo‘shing.')
    return problems

def route(handler,db,ctx,method,path,qs,data,raw,core):
    uid=ctx['uid'];error=core['HttpError'];text=core['clean_text'];ident=core['ident'];verified=core['require_verified'];require=core['require_user'];now=datetime.now(timezone.utc)
    if path=='/api/security/unlock' and method=='POST':
        require(ctx);core['check_rate'](db,'mfa_unlock',uid,8,300)
        if not consume_otp(db,uid,data.get('otp'),core):raise error(403,'Xavfsizlik kodi noto‘g‘ri yoki oldin ishlatilgan.')
        token=core['decode_session'](handler.cookie());db.execute('UPDATE sessions SET mfa_verified=1 WHERE token_hash=? AND user_id=?',(core['hash_token'](token),uid))
        return {'ok':True}
    if path=='/api/security' and method=='GET':
        require(ctx);token=core['decode_session'](handler.cookie()) if hasattr(handler,'headers') else None
        current=core['hash_token'](token) if token else ''
        sessions=[{**dict(r),'current':r['id']==current} for r in db.execute('SELECT token_hash id,created_at,last_seen_at,user_agent,network_label FROM sessions WHERE user_id=? AND expires_at>? ORDER BY last_seen_at DESC',(uid,core['now_iso']()))]
        linked=[r['provider'] for r in db.execute('SELECT provider FROM oauth_identities WHERE user_id=?',(uid,))]
        return {'mfa_enabled':enabled(db,uid),'recovery_codes_remaining':db.execute('SELECT COUNT(*) n FROM security_recovery_codes WHERE user_id=? AND used_at IS NULL',(uid,)).fetchone()['n'],'sessions':sessions,'linked_providers':linked}
    match=re.fullmatch(r'/api/security/sessions/([a-f0-9]{64}|others)',path)
    if match and method=='DELETE':
        require(ctx);target=match.group(1)
        current=core['decode_session'](handler.cookie());current=core['hash_token'](current) if current else ''
        if target=='others':db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(uid,current))
        else:db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash=?',(uid,target))
        return {'ok':True,'signed_out':target==current}
    if path=='/api/security/mfa/setup' and method=='POST':
        verified(ctx);reauthenticate(db,uid,data,core)
        if enabled(db,uid):raise error(409,'2FA allaqachon yoqilgan.')
        secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=');cipher=encrypt(secret,uid,core)
        db.execute('INSERT INTO account_security(user_id,pending_cipher,pending_expires) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET pending_cipher=excluded.pending_cipher,pending_expires=excluded.pending_expires',(uid,cipher,iso(now+timedelta(minutes=10))))
        from urllib.parse import quote
        return {'secret':secret,'uri':'otpauth://totp/'+quote('SentryLoot:'+ctx['user']['email'],safe='')+'?secret='+secret+'&issuer=SentryLoot&digits=6&period=30'}
    if path=='/api/security/mfa/enable' and method=='POST':
        verified(ctx);core['check_rate'](db,'mfa_enroll',uid,8,300)
        row=db.execute('SELECT * FROM account_security WHERE user_id=?',(uid,)).fetchone()
        code=data.get('otp');step=int(time.time())//30;valid_step=None
        if row and not row['enabled'] and row['pending_cipher'] and row['pending_expires'] and utc(row['pending_expires'])>now and isinstance(code,str) and re.fullmatch(r'[0-9]{6}',code.strip()):
            secret=decrypt(row['pending_cipher'],uid,core)
            valid_step=next((n for n in (step,step-1,step+1) if hmac.compare_digest(totp(secret,n),code.strip())),None)
        if valid_step is None:raise error(400,'Tasdiqlash kodi noto‘g‘ri yoki sozlash muddati tugagan.')
        db.execute('BEGIN IMMEDIATE')
        try:
            changed=db.execute("UPDATE account_security SET secret_cipher=pending_cipher,pending_cipher='',pending_expires=NULL,enabled=1,last_step=? WHERE user_id=? AND enabled=0 AND pending_cipher=?",(valid_step,uid,row['pending_cipher']))
            if changed.rowcount!=1:raise error(409,'Sozlama allaqachon yangilangan.')
            codes=[secrets.token_hex(6).upper() for _ in range(10)]
            for code in codes:db.execute('INSERT INTO security_recovery_codes(user_id,code_hash) VALUES(?,?)',(uid,hashlib.sha256(code.encode()).hexdigest()))
            current=core['decode_session'](handler.cookie());current=core['hash_token'](current) if current else ''
            db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(uid,current));db.execute('UPDATE sessions SET mfa_verified=1 WHERE user_id=?',(uid,))
            core['audit'](db,uid,'mfa_enabled','user',uid);db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        security_notice(db,uid,'Ikki bosqichli kirish yoqildi',core)
        return {'enabled':True,'recovery_codes':codes}
    if path=='/api/security/mfa/disable' and method=='POST':
        verified(ctx);reauthenticate(db,uid,data,core)
        db.execute("UPDATE account_security SET enabled=0,secret_cipher='',pending_cipher='',pending_expires=NULL,last_step=-1 WHERE user_id=?",(uid,));db.execute('DELETE FROM security_recovery_codes WHERE user_id=?',(uid,))
        current=core['decode_session'](handler.cookie());db.execute('DELETE FROM sessions WHERE user_id=? AND token_hash<>?',(uid,core['hash_token'](current) if current else ''))
        core['audit'](db,uid,'mfa_disabled','user',uid);security_notice(db,uid,'Ikki bosqichli kirish o‘chirildi',core);return {'enabled':False}
    if path=='/api/security/password' and method=='POST':
        verified(ctx);reauthenticate(db,uid,data,core);password=data.get('new_password')
        if not isinstance(password,str) or not 10<=len(password)<=256:raise error(400,'Yangi parol 10–256 belgidan iborat bo‘lsin.')
        hashed=core['password_hash'](password)
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(hashed,uid));db.execute('DELETE FROM sessions WHERE user_id=?',(uid,));core['audit'](db,uid,'password_changed','user',uid)
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        security_notice(db,uid,'Hisob paroli yangilandi',core)
        return {'ok':True,'signed_out':True}
    if path=='/api/security/email' and method=='POST':
        verified(ctx);reauthenticate(db,uid,data,core);address=text(data.get('email'),'Email',3,254).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',address):raise error(400,'Email manzili noto‘g‘ri.')
        if db.execute('SELECT 1 FROM users WHERE email=?',(address,)).fetchone():raise error(409,'Bu email band.')
        if core['MODE']!='development' and not core['email_service'].is_configured():raise error(503,'Tasdiqlash xatini yuborish xizmati tayyor emas.')
        token=core['create_token']();db.execute('DELETE FROM pending_email_changes WHERE user_id=?',(uid,));db.execute('INSERT INTO pending_email_changes(token_hash,user_id,new_email,expires_at) VALUES(?,?,?,?)',(core['hash_token'](token),uid,address,iso(now+timedelta(minutes=30))))
        if core['email_service'].is_configured():
            try:core['email_service'].send_action_email(address,ctx['user']['display_name'],'email_change',token)
            except Exception as exc:raise error(503,'Tasdiqlash xati yuborilmadi. Qayta urinib ko‘ring.') from exc
        result={'ok':True,'message':'Yangi emailga tasdiqlash havolasi yuborildi. Amaldagi email hozircha o‘zgarmadi.'}
        if core['MODE']=='development' and not core['email_service'].is_configured():result['confirmation_token']=token
        return result
    if path=='/api/security/email/confirm' and method=='POST':
        verified(ctx);core['check_rate'](db,'email_change_confirm',uid,8,300);token=text(data.get('token'),'Token',20,200)
        db.execute('BEGIN IMMEDIATE')
        try:
            row=db.execute('SELECT * FROM pending_email_changes WHERE token_hash=? AND user_id=? AND expires_at>?',(core['hash_token'](token),uid,core['now_iso']())).fetchone()
            if not row:raise error(400,'Tasdiqlash havolasi yaroqsiz yoki muddati tugagan.')
            changed=db.execute('DELETE FROM pending_email_changes WHERE token_hash=?',(row['token_hash'],))
            if changed.rowcount!=1:raise error(409,'Havola ishlatilgan.')
            db.execute('UPDATE users SET email=? WHERE id=?',(row['new_email'],uid));core['notify'](db,uid,'security','Email yangilandi','Hisob email manzilingiz yangilandi.','/account');core['audit'](db,uid,'email_changed','user',uid);db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        security_notice(db,uid,'Hisob email manzili yangilandi',core,address=ctx['user']['email'])
        return {'ok':True,'user':core['user_view'](db,uid)}
    if path=='/api/seller/availability' and method in ('GET','POST'):
        verified(ctx)
        if not ctx['user']['seller']:raise error(403,'Sotuvchi profili kerak.')
        if method=='GET':return availability(db,uid)
        zone=text(data.get('timezone'),'Vaqt mintaqasi',1,80)
        try:ZoneInfo(zone)
        except (ZoneInfoNotFoundError,ValueError):raise error(400,'Vaqt mintaqasi noto‘g‘ri.')
        hours=data.get('hours',[]);vacation=data.get('vacation',False)
        if not isinstance(vacation,bool) or not isinstance(hours,list) or len(hours)>14:raise error(400,'Ish jadvali noto‘g‘ri.')
        cleaned=[]
        for window in hours:
            if not isinstance(window,dict) or type(window.get('day')) is not int or not 0<=window['day']<=6:raise error(400,'Hafta kuni noto‘g‘ri.')
            start,end=window.get('start',''),window.get('end','')
            if not isinstance(start,str) or not isinstance(end,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',start) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',end) or start>=end:raise error(400,'Ish soati 00:00–23:59 orasida, boshlanish tugashdan oldin bo‘lsin.')
            if any(w['day']==window['day'] and start<w['end'] and end>w['start'] for w in cleaned):raise error(400,'Ish soatlari bir-birini takrorlamasin.')
            cleaned.append({'day':window['day'],'start':start,'end':end})
        db.execute('INSERT INTO seller_availability(user_id,timezone,hours_json,vacation) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET timezone=excluded.timezone,hours_json=excluded.hours_json,vacation=excluded.vacation,updated_at=CURRENT_TIMESTAMP',(uid,zone,json.dumps(cleaned),int(vacation)))
        return availability(db,uid)
    if path=='/api/blocks' and method=='GET':
        require(ctx);return [dict(r) for r in db.execute('SELECT b.blocked_id id,u.display_name name,b.created_at FROM user_blocks b JOIN users u ON u.id=b.blocked_id WHERE b.user_id=? ORDER BY b.created_at DESC',(uid,))]
    match=re.fullmatch(r'/api/blocks/([^/]+)',path)
    if match and method in ('POST','DELETE'):
        require(ctx);other=match.group(1)
        if other==uid or not db.execute('SELECT 1 FROM users WHERE id=?',(other,)).fetchone():raise error(400,'Foydalanuvchini bloklab bo‘lmaydi.')
        if method=='POST':db.execute('INSERT OR IGNORE INTO user_blocks(user_id,blocked_id) VALUES(?,?)',(uid,other))
        else:db.execute('DELETE FROM user_blocks WHERE user_id=? AND blocked_id=?',(uid,other))
        return {'blocked':method=='POST'}
    if method=='POST' and path=='/api/conversations':
        if data.get('listing_id'):
            if not isinstance(data['listing_id'],str):raise error(400,'E’lon ID noto‘g‘ri.')
            row=db.execute('SELECT seller_id FROM listings WHERE id=?',(data['listing_id'],)).fetchone()
            if row and uid and blocked(db,uid,row['seller_id']):raise error(403,'Bu foydalanuvchi bilan yangi suhbat bloklangan.')
        if data.get('seller_id') and not isinstance(data['seller_id'],str):raise error(400,'Sotuvchi ID noto‘g‘ri.')
        if data.get('seller_id') and uid and blocked(db,uid,data['seller_id']) and not data.get('order_id'):raise error(403,'Bu foydalanuvchi bilan yangi suhbat bloklangan.')
    match=re.fullmatch(r'/api/conversations/([^/]+)/(?:messages|photos)',path)
    if match and method=='POST' and uid:
        row=db.execute('SELECT * FROM conversations WHERE id=?',(match.group(1),)).fetchone()
        if row and uid in (row['buyer_id'],row['seller_id']):chat_allowed(db,row,uid,core)
    if path=='/api/seller/listings/bulk-update' and method=='POST':
        verified(ctx);core['seller_ok'](db,uid);core['check_rate'](db,'bulk_update',uid,12,3600)
        ids=data.get('ids');fields=data.get('fields')
        if not isinstance(ids,list) or not 1<=len(ids)<=100 or any(not isinstance(i,str) for i in ids) or not isinstance(fields,dict) or not fields or set(fields)-{'price_minor','stock','delivery_eta','platform','region'}:raise error(400,'E’lonlar va tahrir maydonlarini tekshiring.')
        ids=list(dict.fromkeys(ids));slots=','.join('?' for _ in ids);db.execute('BEGIN IMMEDIATE')
        try:
            rows=db.execute(f'SELECT id FROM listings WHERE seller_id=? AND id IN ({slots})',(uid,*ids)).fetchall()
            if len(rows)!=len(ids):raise error(404,'E’lon topilmadi.')
            for lid in ids:handler.route(db,ctx,'PATCH','/api/listings/'+lid,{},fields)
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'updated':len(ids),'message':'O‘zgargan faol e’lonlar qayta moderatsiyaga yuborildi.'}
    if path=='/api/catalog/readiness' and method=='GET':
        core['require_admin'](ctx)
        rows=db.execute("SELECT l.*,g.name game_name FROM listings l JOIN games g ON g.id=l.game_id WHERE l.status IN ('draft','pending_review','published','approved_private') ORDER BY l.updated_at DESC LIMIT 200").fetchall()
        return {'items':[{'id':r['id'],'title':r['title'],'game_name':r['game_name'],'status':r['status'],'issues':quality(r)} for r in rows],'games':[dict(r) for r in db.execute("SELECT g.name,g.slug,COUNT(l.id) listings FROM games g LEFT JOIN listings l ON l.game_id=g.id AND l.status='published' GROUP BY g.id,g.name,g.slug ORDER BY COUNT(l.id),g.name")]}
    if path=='/api/support/tickets' and method in ('GET','POST'):
        require(ctx);admin=core['is_admin'](db,uid)
        if method=='GET':
            admin_queue=admin and qs.get('queue',[''])[0]=='1'
            return [dict(r) for r in db.execute('SELECT t.id,t.subject,t.category,t.status,t.order_id,t.created_at,t.updated_at FROM support_tickets t'+('' if admin_queue else ' WHERE t.requester_id=?')+' ORDER BY t.updated_at DESC,t.id DESC LIMIT 100',() if admin_queue else (uid,))]
        verified(ctx);core['check_rate'](db,'support_create',uid,10,3600)
        subject=text(data.get('subject'),'Mavzu',5,120);body=text(data.get('body'),'Murojaat',10,5000);category=data.get('category','general')
        if category not in ('general','delivery','account','listing','dispute'):raise error(400,'Mavzuni tanlang.')
        oid=data.get('order_id') or None
        if oid:oid=text(oid,'Buyurtma ID',1,100)
        if oid:order_member(db,oid,uid,core)
        tid=ident();db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('INSERT INTO support_tickets(id,requester_id,order_id,subject,category) VALUES(?,?,?,?,?)',(tid,uid,oid,subject,category));db.execute('INSERT INTO support_entries(id,ticket_id,sender_id,body) VALUES(?,?,?,?)',(ident(),tid,uid,body))
            for row in db.execute('SELECT user_id FROM admin_accounts LIMIT 30'):core['notify'](db,row['user_id'],'support','Yangi yordam murojaati',subject,'/support-ticket/'+tid)
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return 201,{'id':tid}
    match=re.fullmatch(r'/api/support/tickets/([^/]+)',path)
    if match and method in ('GET','POST'):
        require(ctx);tid=match.group(1);ticket=db.execute('SELECT * FROM support_tickets WHERE id=?',(tid,)).fetchone();admin=core['is_admin'](db,uid)
        if not ticket or not (uid==ticket['requester_id'] or admin):raise error(404,'Murojaat topilmadi.')
        if method=='GET':return {'ticket':dict(ticket),'can_manage':admin,'entries':[{**dict(r),'is_support':r['sender_id']!=ticket['requester_id']} for r in db.execute('SELECT id,sender_id,body,created_at FROM support_entries WHERE ticket_id=? ORDER BY created_at,id',(tid,))]}
        verified(ctx);core['check_rate'](db,'support_reply',uid,30,3600);body=text(data.get('body'),'Javob',2,5000);state=data.get('status','waiting_customer' if admin else 'open')
        if state not in ('open','waiting_customer','resolved') or not admin and state not in ('open','resolved'):raise error(400,'Holat noto‘g‘ri.')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('INSERT INTO support_entries(id,ticket_id,sender_id,body) VALUES(?,?,?,?)',(ident(),tid,uid,body));db.execute('UPDATE support_tickets SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(state,tid))
            targets=[ticket['requester_id']] if admin else [r['user_id'] for r in db.execute('SELECT user_id FROM admin_accounts LIMIT 30')]
            for target in targets:core['notify'](db,target,'support','Yordam murojaati yangilandi',ticket['subject'],'/support-ticket/'+tid)
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'ok':True}
    match=re.fullmatch(r'/api/disputes/([^/]+)(/photos)?',path)
    if match and method in ('GET','POST'):
        require(ctx);oid=match.group(1);order=order_member(db,oid,uid,core)
        report=db.execute("SELECT id,details,status,resolution,created_at,response_due_at FROM reports WHERE order_id=? AND reason='order_dispute' ORDER BY created_at DESC LIMIT 1",(oid,)).fetchone()
        if method=='GET':
            entries=[dict(r) for r in db.execute('SELECT e.id,e.sender_id,e.body,e.created_at,u.display_name sender_name FROM dispute_entries e JOIN users u ON u.id=e.sender_id WHERE e.order_id=? ORDER BY e.created_at,e.id',(oid,))]
            attachments={r['entry_id']:dict(r) for r in db.execute('SELECT a.entry_id,a.owner_id,a.object_path FROM dispute_attachments a JOIN dispute_entries e ON e.id=a.entry_id WHERE e.order_id=?',(oid,))}
            admin=core['is_admin'](db,uid)
            for entry in entries:
                if entry['id'] in attachments:
                    attachment=attachments[entry['id']]
                    if attachment['owner_id']!=uid and not admin:
                        entry['image_private']=True;continue
                    try:entry['image_url']=core['storage_r2'].evidence_url(attachment['object_path'])
                    except Exception:entry['image_unavailable']=True
            return {'order':{'id':oid,'reference':order['reference'],'status':order['status']},'report':dict(report) if report else None,'entries':entries,'can_reply':order['status']=='disputed','can_manage':core['is_admin'](db,uid)}
        verified(ctx);core['check_rate'](db,'dispute_reply',uid,30,3600)
        if not report or order['status']!='disputed':raise error(409,'Nizo hali ochilmagan yoki allaqachon yopilgan.')
        eid=ident();key=None
        if match.group(2):
            core['require_private_evidence_bucket']();image=core['normalize_account_evidence'](raw,handler.headers.get('Content-Type',''));key=secrets.token_hex(12)+'/'+secrets.token_hex(24)+'.webp'
            try:core['storage_r2'].put_evidence(key,image)
            except Exception as exc:raise error(503,'Dalil rasmi saqlanmadi.') from exc
            body='Dalil rasmi · moderator uchun'
        else:body=text(data.get('body'),'Izoh',2,5000)
        db.execute('BEGIN IMMEDIATE')
        try:
            locked=db.execute("UPDATE orders SET updated_at=updated_at WHERE id=? AND status='disputed'",(oid,))
            if locked.rowcount!=1:raise error(409,'Nizo allaqachon yopilgan.')
            db.execute('INSERT INTO dispute_entries(id,order_id,sender_id,body) VALUES(?,?,?,?)',(eid,oid,uid,body))
            if key:db.execute('INSERT INTO dispute_attachments(entry_id,owner_id,object_path) VALUES(?,?,?)',(eid,uid,key))
            targets={order['buyer_id']}|{r['seller_id'] for r in db.execute('SELECT seller_id FROM order_items WHERE order_id=?',(oid,))}|{r['user_id'] for r in db.execute('SELECT user_id FROM admin_accounts LIMIT 30')}
            for target in targets-{uid}:core['notify'](db,target,'dispute','Nizo yangilandi',order['reference'],'/dispute/'+oid)
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            if key:core['storage_r2'].delete_evidence(key)
            raise
        return 201,{'id':eid}
    if path=='/api/cron/order-deadlines' and method=='GET':
        secret=core['os'].environ.get('CRON_SECRET','');auth=handler.headers.get('Authorization','')
        if not secret or not hmac.compare_digest(auth,'Bearer '+secret):raise error(401,'Cron avtorizatsiyasi noto‘g‘ri.')
        return deadline_run(db,core)
    return UNHANDLED

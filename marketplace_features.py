"""Marketplace discovery, public stores and participant-only conversations.

Core services are injected by the request handler so this module never opens a
second database connection or bypasses the existing authorization/sales gates.
"""
import json
import re
import secrets
from datetime import datetime, timezone
from difflib import get_close_matches

UNHANDLED = object()
TABLES = ('seller_follows', 'review_replies', 'message_attachments', 'listing_alert_state')
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS seller_follows (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        seller_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id,seller_id), CHECK(user_id<>seller_id))""",
    """CREATE TABLE IF NOT EXISTS review_replies (
        review_id TEXT PRIMARY KEY REFERENCES reviews(id) ON DELETE CASCADE,
        seller_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS message_attachments (
        message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
        conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        owner_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        object_path TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS listing_alert_state (
        listing_id TEXT PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,
        price_minor BIGINT NOT NULL, available INTEGER NOT NULL,
        published_once INTEGER NOT NULL DEFAULT 0)""",
    'CREATE INDEX IF NOT EXISTS idx_follows_seller ON seller_follows(seller_id)',
    'CREATE INDEX IF NOT EXISTS idx_messages_recent ON messages(conversation_id,created_at,id)',
    'CREATE UNIQUE INDEX IF NOT EXISTS idx_order_conversation ON conversations(order_id,buyer_id,seller_id) WHERE order_id IS NOT NULL',
)

def migrate(db, postgres=False):
    if postgres: db.execute('ALTER TABLE public.listings ADD COLUMN IF NOT EXISTS delivery_minutes INTEGER')
    elif 'delivery_minutes' not in {r['name'] for r in db.execute('PRAGMA table_info(listings)')}: db.execute('ALTER TABLE listings ADD COLUMN delivery_minutes INTEGER')
    for row in db.execute('SELECT id,delivery_eta FROM listings WHERE delivery_minutes IS NULL').fetchall():
        minutes=delivery_minutes(row['delivery_eta'])
        if minutes is not None: db.execute('UPDATE listings SET delivery_minutes=? WHERE id=?',(minutes,row['id']))
    for statement in SCHEMA:
        db.execute(statement)
    if postgres:
        for table in TABLES:
            db.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            db.execute(f'REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated')
    db.execute("INSERT INTO listing_alert_state(listing_id,price_minor,available,published_once) SELECT id,price_minor,stock-reserved,CASE WHEN status='published' THEN 1 ELSE 0 END FROM listings ON CONFLICT(listing_id) DO NOTHING" if postgres else "INSERT OR IGNORE INTO listing_alert_state(listing_id,price_minor,available,published_once) SELECT id,price_minor,stock-reserved,CASE WHEN status='published' THEN 1 ELSE 0 END FROM listings")


def delivery_minutes(value):
    text=(value or '').lower()
    if any(word in text for word in ('instant', 'darhol', 'мгнов')): return 1
    matches=re.findall(r'(\d+(?:\.\d+)?)\s*(minutes?|mins?|minut|daq|мин|hours?|hrs?|soat|час|days?|kun|дн)',text)
    values=[]
    for number,unit in matches:
        scale=1440 if unit.startswith(('day','kun','дн')) else 60 if unit.startswith(('hour','hr','soat','час')) else 1
        values.append(float(number)*scale)
    return int(max(values)) if values else None


def alert_publication(db, lid, core):
    row=db.execute('SELECT * FROM listings WHERE id=?',(lid,)).fetchone()
    if not row or row['status']!='published': return
    prior=db.execute('SELECT * FROM listing_alert_state WHERE listing_id=?',(lid,)).fetchone()
    available=max(0,row['stock']-row['reserved'])
    if prior and prior['published_once']:
        if row['price_minor']!=prior['price_minor'] or (available>0 and prior['available']<=0):
            title='Saqlangan e’lon yangilandi'
            body=f'{row["title"]}: '+(f"narx o‘zgardi: {prior['price_minor']} → {row['price_minor']} {row['currency']}." if row['price_minor']!=prior['price_minor'] else 'yana mavjud.')
            for follower in db.execute('SELECT user_id FROM favorites WHERE listing_id=?',(lid,)):
                core['notify'](db,follower['user_id'],'favorite',title,body,'/listing/'+lid)
    else:
        for follower in db.execute('SELECT user_id FROM seller_follows WHERE seller_id=?',(row['seller_id'],)):
            core['notify'](db,follower['user_id'],'seller_listing','Kuzatilayotgan do‘konda yangi e’lon',row['title'],'/listing/'+lid)
    db.execute('INSERT INTO listing_alert_state(listing_id,price_minor,available,published_once) VALUES(?,?,?,1) ON CONFLICT(listing_id) DO UPDATE SET price_minor=excluded.price_minor,available=excluded.available,published_once=1',(lid,row['price_minor'],available))


def profile(db, sid, uid, core):
    row=db.execute("SELECT s.user_id id,s.shop_name,s.bio,s.created_at,s.verification_status,CASE WHEN s.identity_provider='didit' AND s.identity_status='verified' THEN 1 ELSE 0 END identity_verified FROM seller_profiles s JOIN users u ON u.id=s.user_id WHERE s.user_id=? AND u.suspended=0",(sid,)).fetchone()
    if not row: raise core['HttpError'](404,'Do‘kon topilmadi.')
    out=dict(row)
    stats=db.execute('SELECT COUNT(*) review_count,AVG(rating) rating,COALESCE(SUM(CASE WHEN rating>=4 THEN 1 ELSE 0 END),0) positive FROM reviews WHERE seller_id=?',(sid,)).fetchone()
    out.update(dict(stats));out['rating']=float(out['rating']) if out['rating'] is not None else None
    out['positive_percent']=round(out.pop('positive')*100/out['review_count']) if out['review_count'] else None
    out['completed_sales']=int(db.execute("SELECT COALESCE(SUM(i.quantity),0) n FROM order_items i JOIN orders o ON o.id=i.order_id WHERE i.seller_id=? AND o.status='completed'",(sid,)).fetchone()['n'])
    out['sales_history']=[{'game_name':r['game_name'],'quantity':int(r['quantity']),'last_sale_at':r['last_sale_at']} for r in db.execute("SELECT g.name game_name,SUM(oi.quantity) quantity,MAX(o.updated_at) last_sale_at FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN listings l ON l.id=oi.listing_id JOIN games g ON g.id=l.game_id WHERE oi.seller_id=? AND o.status='completed' GROUP BY g.id,g.name ORDER BY SUM(oi.quantity) DESC LIMIT 12",(sid,))]
    out['following']=bool(uid and db.execute('SELECT 1 FROM seller_follows WHERE user_id=? AND seller_id=?',(uid,sid)).fetchone())
    out['is_owner']=uid==sid
    out['online']=False
    if core['user_presence_available'](db):
        seen=db.execute('SELECT last_seen_at FROM users WHERE id=?',(sid,)).fetchone()['last_seen_at']
        try: out['online']=(datetime.now(timezone.utc)-datetime.fromisoformat(seen.replace('Z','+00:00')).replace(tzinfo=timezone.utc)).total_seconds()<180
        except (TypeError,ValueError,AttributeError): pass
    samples=[]
    for row in db.execute('''SELECT c.id,MIN(b.created_at) sent_at FROM conversations c JOIN messages b ON b.conversation_id=c.id AND b.sender_id=c.buyer_id WHERE c.seller_id=? GROUP BY c.id ORDER BY MIN(b.created_at) DESC LIMIT 100''',(sid,)):
        reply=db.execute('SELECT MIN(created_at) sent_at FROM messages WHERE conversation_id=? AND sender_id=? AND created_at>=?',(row['id'],sid,row['sent_at'])).fetchone()['sent_at']
        if reply:
            try: samples.append(max(0,(datetime.fromisoformat(reply.replace('Z','+00:00')).replace(tzinfo=timezone.utc)-datetime.fromisoformat(row['sent_at'].replace('Z','+00:00')).replace(tzinfo=timezone.utc)).total_seconds()))
            except (TypeError,ValueError): pass
    out['avg_reply_seconds']=round(sum(samples)/len(samples)) if samples else None
    return out


def route(handler,db,ctx,method,path,qs,data,raw,core):
    uid=ctx['uid']; error=core['HttpError']; require_user=core['require_user']; require_verified=core['require_verified']; text=core['clean_text']; ident=core['ident']
    param=lambda key,default='': qs.get(key,[default])[0]
    if path=='/api/search/suggestions' and method=='GET':
        query=param('q').strip().lower()[:100]
        if len(query)<2: return {'games':[],'items':[]}
        games=[dict(r) for r in db.execute('SELECT slug,name FROM games ORDER BY name')]
        normalized=re.sub(r'[^a-z0-9]','',query)
        aliases={'csgo':'counter-strike-2','cs2':'counter-strike-2','counterstrike':'counter-strike-2','counterstrike2':'counter-strike-2','pubg':'pubg-mobile','mlbb':'mobile-legends','dota':'dota-2'}
        selected=[g for g in games if query in g['name'].lower() or query in g['slug'] or g['slug']==aliases.get(normalized)]
        if not selected:
            names={g['name'].lower():g for g in games};selected=[names[n] for n in get_close_matches(query,list(names),n=4,cutoff=.45)]
        rows=db.execute("SELECT l.id,l.title,l.price_minor,l.currency,l.game_id,l.product_type FROM listings l WHERE l.status='published' AND l.stock>l.reserved AND lower(l.title) LIKE ? ORDER BY l.created_at DESC LIMIT 6",('%'+query+'%',))
        items=[dict(r) for r in rows if core['listing_allowed_for_production'](db,r['game_id'],r['product_type'])]
        return {'games':selected[:5],'items':items}
    match=re.fullmatch(r'/api/stores/([^/]+)(/reviews|/follow)?',path)
    if match:
        sid,sub=match.groups()
        store=profile(db,sid,uid,core)
        if sub=='/follow' and method in ('POST','DELETE'):
            require_user(ctx)
            if sid==uid: raise error(400,'O‘z do‘koningizni kuzata olmaysiz.')
            if method=='POST':db.execute('INSERT OR IGNORE INTO seller_follows(user_id,seller_id) VALUES(?,?)',(uid,sid))
            else:db.execute('DELETE FROM seller_follows WHERE user_id=? AND seller_id=?',(uid,sid))
            return {'following':method=='POST'}
        if method=='GET' and sub=='/reviews':
            where=['r.seller_id=?'];args=[sid]
            if param('sentiment')=='positive':where.append('r.rating>=4')
            if param('sentiment')=='negative':where.append('r.rating<=3')
            if param('game'):where.append('g.slug=?');args.append(param('game'))
            try: page=max(1,min(10000,int(param('page','1'))))
            except ValueError: raise error(400,'Sahifa noto‘g‘ri.')
            joins='FROM reviews r JOIN users u ON u.id=r.reviewer_id JOIN order_items oi ON oi.id=r.order_item_id JOIN listings l ON l.id=oi.listing_id JOIN games g ON g.id=l.game_id LEFT JOIN review_replies rr ON rr.review_id=r.id'
            count=db.execute(f"SELECT COUNT(*) n {joins} WHERE {' AND '.join(where)}",tuple(args)).fetchone()['n']
            order={'oldest':'r.created_at ASC,r.id ASC','rating_desc':'r.rating DESC,r.created_at DESC','rating_asc':'r.rating ASC,r.created_at DESC'}.get(param('sort'),'r.created_at DESC,r.id DESC')
            rows=[dict(r) for r in db.execute(f"SELECT r.id,r.rating,r.body,r.created_at,u.display_name reviewer_name,g.name game_name,g.slug game_slug,rr.body reply,rr.updated_at replied_at {joins} WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 12 OFFSET ?",(*args,(page-1)*12))]
            games=[dict(r) for r in db.execute('SELECT DISTINCT g.slug,g.name FROM reviews r JOIN order_items oi ON oi.id=r.order_item_id JOIN listings l ON l.id=oi.listing_id JOIN games g ON g.id=l.game_id WHERE r.seller_id=? ORDER BY g.name',(sid,))]
            return {'items':rows,'games':games,'total_count':count,'page':page,'has_more':page*12<count,'can_reply':uid==sid}
        if method=='GET' and sub is None:return store
    if path=='/api/following' and method=='GET':
        require_user(ctx)
        return [profile(db,r['seller_id'],uid,core) for r in db.execute('SELECT seller_id FROM seller_follows WHERE user_id=? ORDER BY created_at DESC',(uid,))]
    match=re.fullmatch(r'/api/reviews/([^/]+)/reply',path)
    if match and method=='POST':
        require_verified(ctx);core['check_rate'](db,'review_reply',uid,30,3600)
        review=db.execute('SELECT seller_id,reviewer_id FROM reviews WHERE id=?',(match.group(1),)).fetchone()
        if not review or review['seller_id']!=uid:raise error(404,'Sharh topilmadi.')
        body=text(data.get('body'),'Javob',2,1500)
        db.execute('INSERT INTO review_replies(review_id,seller_id,body) VALUES(?,?,?) ON CONFLICT(review_id) DO UPDATE SET body=excluded.body,updated_at=CURRENT_TIMESTAMP',(match.group(1),uid,body))
        return {'ok':True}
    if path=='/api/seller/listings/bulk-pause' and method=='POST':
        require_verified(ctx);core['seller_ok'](db,uid);ids=data.get('ids')
        if not isinstance(ids,list) or not ids or len(ids)>100 or any(not isinstance(i,str) for i in ids):raise error(400,'1–100 ta e’lonni tanlang.')
        ids=list(dict.fromkeys(ids));placeholders=','.join('?' for _ in ids)
        db.execute('BEGIN IMMEDIATE')
        try:
            rows=db.execute(f'SELECT id,status FROM listings WHERE seller_id=? AND id IN ({placeholders})',(uid,*ids)).fetchall()
            if len(rows)!=len(ids) or any(r['status'] not in ('published','paused') for r in rows):raise error(409,'Faqat o‘zingizning faol e’lonlaringizni tanlang.')
            db.execute(f"UPDATE listings SET status='paused',updated_at=CURRENT_TIMESTAMP WHERE seller_id=? AND id IN ({placeholders})",(uid,*ids));db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'updated':len(ids)}
    match=re.fullmatch(r'/api/listings/([^/]+)/duplicate',path)
    if match and method=='POST':
        require_verified(ctx);core['seller_ok'](db,uid);core['check_rate'](db,'duplicate_listing',uid,15,3600)
        row=db.execute('SELECT * FROM listings WHERE id=? AND seller_id=?',(match.group(1),uid)).fetchone()
        if not row:raise error(404,'E’lon topilmadi.')
        lid=ident();fields=['seller_id','game_id','category_id','title','description','product_type','price_minor','currency','platform','region','attributes_json','delivery_method','delivery_eta','requirements','stock','image_url','seller_account_terms_version','seller_account_terms_at']
        values=[row[f] for f in fields];values[fields.index('title')]=(row['title']+' — copy')[:120];values[fields.index('stock')]=max(1,row['stock'])
        attrs=json.loads(row['attributes_json'] or '{}');attrs={k:v for k,v in attrs.items() if not k.startswith('_')};attrs['_risk_flags']=['possible_duplicate_listing'];values[fields.index('attributes_json')]=json.dumps(attrs)
        db.execute(f"INSERT INTO listings(id,{','.join(fields)},status) VALUES({','.join('?' for _ in range(len(fields)+1))},'draft')",(lid,*values))
        db.execute('UPDATE listings SET delivery_minutes=? WHERE id=?',(delivery_minutes(row['delivery_eta']),lid))
        return 201,{'id':lid,'status':'draft'}
    if path=='/api/conversations' and method=='POST' and data.get('order_id'):
        require_verified(ctx);oid=text(data.get('order_id'),'Buyurtma',1,100)
        order=db.execute('SELECT buyer_id FROM orders WHERE id=?',(oid,)).fetchone()
        if not order:raise error(404,'Buyurtma topilmadi.')
        sid=data.get('seller_id') if uid==order['buyer_id'] else uid
        if not db.execute('SELECT 1 FROM order_items WHERE order_id=? AND seller_id=?',(oid,sid)).fetchone():raise error(404,'Buyurtma topilmadi.')
        cid=ident();db.execute('INSERT OR IGNORE INTO conversations(id,buyer_id,seller_id,order_id) VALUES(?,?,?,?)',(cid,order['buyer_id'],sid,oid))
        return {'id':db.execute('SELECT id FROM conversations WHERE order_id=? AND buyer_id=? AND seller_id=?',(oid,order['buyer_id'],sid)).fetchone()['id']}
    match=re.fullmatch(r'/api/conversations/([^/]+)(/photos)?',path)
    if match and (method=='GET' or method=='POST' and match.group(2)):
        require_user(ctx);cid=match.group(1)
        conv=db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone()
        if not conv or uid not in (conv['buyer_id'],conv['seller_id']):raise error(404,'Suhbat topilmadi.')
        if method=='POST':
            require_verified(ctx);core['check_rate'](db,'chat_photo',uid,20,3600)
            normalized=core['normalize_account_evidence'](raw,handler.headers.get('Content-Type',''))
            core['require_private_evidence_bucket']()
            key=secrets.token_hex(12)+'/'+secrets.token_hex(24)+'.webp'
            try:core['storage_r2'].put_evidence(key,normalized)
            except Exception as exc:raise error(503,'Rasmni saqlab bo‘lmadi. Qayta urinib ko‘ring.') from exc
            mid=ident()
            try:
                db.execute('BEGIN IMMEDIATE')
                db.execute("INSERT INTO messages(id,conversation_id,sender_id,body) VALUES(?,?,?,'📷 Photo')",(mid,cid,uid))
                db.execute('INSERT INTO message_attachments(message_id,conversation_id,owner_id,object_path) VALUES(?,?,?,?)',(mid,cid,uid,key))
                core['notify'](db,conv['seller_id'] if uid==conv['buyer_id'] else conv['buyer_id'],'message','Yangi rasm','Suhbatda yangi rasm bor.','/conversation/'+cid)
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK');core['storage_r2'].delete_evidence(key);raise
            return 201,{'id':mid}
        db.execute('UPDATE messages SET read_at=CURRENT_TIMESTAMP WHERE conversation_id=? AND sender_id<>? AND read_at IS NULL',(cid,uid))
        sequence='id' if core['DATABASE_URL'] else 'rowid'
        messages=[dict(r) for r in db.execute(f'SELECT * FROM (SELECT id,sender_id,body,created_at,read_at,{sequence} sequence FROM messages WHERE conversation_id=? ORDER BY created_at DESC,{sequence} DESC LIMIT 200) recent ORDER BY created_at,sequence',(cid,))]
        for message in messages: message.pop('sequence',None)
        attachments={r['message_id']:r['object_path'] for r in db.execute('SELECT message_id,object_path FROM message_attachments WHERE conversation_id=?',(cid,))}
        for message in messages:
            if message['id'] in attachments:
                try:message['image_url']=core['storage_r2'].evidence_url(attachments[message['id']])
                except Exception:message['image_unavailable']=True
        out={'conversation':dict(conv),'messages':messages}
        if conv['listing_id']:
            listing=db.execute('SELECT id,title,image_url,price_minor,currency FROM listings WHERE id=?',(conv['listing_id'],)).fetchone()
            if listing:out['listing']=dict(listing)
        if conv['order_id']:
            order=db.execute('SELECT id,reference,status FROM orders WHERE id=?',(conv['order_id'],)).fetchone()
            if order:out['order']=dict(order)
        return out
    return UNHANDLED

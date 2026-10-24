"""Catalogue, seller productivity and account preferences; uses request connection only."""
import csv
import hashlib
import hmac
import io
import json
import re
import secrets
import unicodedata
import zipfile
from datetime import datetime,timedelta,timezone
from difflib import get_close_matches,SequenceMatcher
from urllib.parse import urlencode
from xml.etree import ElementTree as ET
import marketplace_operations as ops

UNHANDLED=object()
TABLES=('experience_preferences','account_collections','conversation_preferences','seller_quick_replies','listing_insights','listing_view_keys','seller_stock_alerts','seller_code_inventory','listing_imports','notification_outbox','price_watches','message_retry_keys')
SCHEMA=(
 "CREATE TABLE IF NOT EXISTS experience_preferences(user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,settings_json TEXT NOT NULL DEFAULT '{}')",
 "CREATE TABLE IF NOT EXISTS account_collections(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,kind TEXT NOT NULL,listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(user_id,kind,listing_id))",
 "CREATE TABLE IF NOT EXISTS conversation_preferences(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,muted INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,conversation_id))",
 "CREATE TABLE IF NOT EXISTS seller_quick_replies(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,title TEXT NOT NULL,body TEXT NOT NULL)",
 "CREATE TABLE IF NOT EXISTS listing_insights(listing_id TEXT NOT NULL REFERENCES listings(id),day TEXT NOT NULL,kind TEXT NOT NULL,total INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(listing_id,day,kind))",
 "CREATE TABLE IF NOT EXISTS listing_view_keys(listing_id TEXT NOT NULL REFERENCES listings(id),day TEXT NOT NULL,visitor_key TEXT NOT NULL,PRIMARY KEY(listing_id,day,visitor_key))",
 "CREATE TABLE IF NOT EXISTS seller_stock_alerts(listing_id TEXT PRIMARY KEY REFERENCES listings(id) ON DELETE CASCADE,threshold INTEGER NOT NULL DEFAULT 2,alerted INTEGER NOT NULL DEFAULT 0)",
 "CREATE TABLE IF NOT EXISTS seller_code_inventory(id TEXT PRIMARY KEY,listing_id TEXT NOT NULL REFERENCES listings(id),seller_id TEXT NOT NULL REFERENCES users(id),cipher TEXT NOT NULL,fingerprint TEXT NOT NULL,order_item_id TEXT REFERENCES order_items(id),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,allocated_at TEXT,UNIQUE(listing_id,fingerprint))",
 "CREATE TABLE IF NOT EXISTS listing_imports(id TEXT PRIMARY KEY,seller_id TEXT NOT NULL REFERENCES users(id),rows_json TEXT NOT NULL,errors_json TEXT NOT NULL,expires_at TEXT NOT NULL,committed INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
 "CREATE TABLE IF NOT EXISTS notification_outbox(notification_id TEXT PRIMARY KEY REFERENCES notifications(id) ON DELETE CASCADE,user_id TEXT NOT NULL REFERENCES users(id),status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
 "CREATE TABLE IF NOT EXISTS price_watches(user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,target_minor BIGINT NOT NULL,last_triggered_minor BIGINT,PRIMARY KEY(user_id,listing_id))",
 "CREATE TABLE IF NOT EXISTS message_retry_keys(conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,sender_id TEXT NOT NULL REFERENCES users(id),request_key TEXT NOT NULL,message_id TEXT NOT NULL REFERENCES messages(id),PRIMARY KEY(conversation_id,sender_id,request_key))",
 'CREATE INDEX IF NOT EXISTS idx_inventory_ready ON seller_code_inventory(listing_id,order_item_id)',
 'CREATE INDEX IF NOT EXISTS idx_outbox_pending ON notification_outbox(status,created_at)',
)
COLUMNS={'listings':{'min_quantity':'INTEGER NOT NULL DEFAULT 1','unit_label':"TEXT NOT NULL DEFAULT 'item'",'automatic_delivery':'INTEGER NOT NULL DEFAULT 0','corrections_json':"TEXT NOT NULL DEFAULT '{}'"}}
GAME_ALIASES={
 'counter-strike-2':['cs2','csgo','counter strike','контр страйк','кс2','ксго','kontr strayk'],
 'pubg-mobile':['pubg','pubg mobile','пабг','pubg mobil','пубг'],
 'mobile-legends':['mlbb','mobile legends','мобайл легенд','mobil legend'],
 'free-fire':['freefire','фри фаер','fri fayr'],'honor-of-kings':['hok','honor of kings','хонор оф кингс'],
 'roblox':['роблокс','robloks'],'valorant':['валорант','valorant'],'genshin-impact':['genshin','геншин','genshin impact'],
 'dota-2':['dota','dota2','дота','дота 2'],
}
FIELD_TYPES={
 'account':['rank','account_level','server','region','platform'],
 'item':['item_type','condition','item_variant','rarity','region','platform'],
 'currency':['server','region','platform','unit'], 'service':['server','rank','region','platform'],
 'code':['redemption_region','code_kind','region','platform'], 'digital':['product_format','access_method','region','platform'],
}
GAME_FIELDS={
 'counter-strike-2':{'account':['premier_rating','prime_status'],'item':['float_value','pattern']},
 'valorant':{'account':['competitive_rank','account_level','platform_binding']},
 'pubg-mobile':{'account':['tier','account_level','server_id']},
 'mobile-legends':{'account':['current_rank','account_level','server_id']},
 'free-fire':{'account':['rank','account_level','server_id']},
 'honor-of-kings':{'account':['current_rank','account_level','server_id']},
 'roblox':{'account':['account_level','inventory_summary']},
 'genshin-impact':{'account':['account_level','server_id','inventory_summary']},
 'dota-2':{'account':['mmr','behavior_score','rank_medal']},
}
LABELS={'account_level':'Level','redemption_region':'Activation region','float_value':'Float','unit':'Unit','item_variant':'Variant','condition':'Condition','item_type':'Item type','server':'Server','platform':'Platform','region':'Region','rank':'Rank'}
TOPICS=[
 {'id':'delivery','title':['Yetkazish qanday ishlaydi?','Как работает доставка?','How does delivery work?'],'body':['Buyurtma ichida sotuvchi natija yoki himoyalangan ma’lumot yuboradi. Qisman yetkazishda son ko‘rinadi.','Продавец передаёт результат или защищённые данные внутри заказа. Частичная доставка показывает количество.','The seller sends the result or protected delivery details in your order. Partial deliveries show the quantity.'],'href':'/help/orders'},
 {'id':'compatibility','title':['Hudud va platforma mosligi','Совместимость региона и платформы','Region and platform compatibility'],'body':['Kodning faollashtirish hududi, platformasi va talablari xariddan oldin tekshiriladi.','До покупки проверьте регион активации, платформу и требования кода.','Check the activation region, platform and requirements before ordering.'],'href':'/help/orders'},
 {'id':'cancel','title':['Buyurtmani bekor qilish','Отмена заказа','Cancel an order'],'body':['Buyurtmada bekor qilish sababini tanlang. Kelishuv bo‘lmasa moderator ko‘radi.','Выберите причину отмены в заказе. При разногласии подключится модератор.','Choose a cancellation reason in the order. A moderator reviews disagreements.'],'href':'/help/refunds'},
 {'id':'dispute','title':['Nizo va yangi dalillar','Споры и новые доказательства','Disputes and new evidence'],'body':['Nizo sahifasida izoh va dalillarni saqlang. Qaror bo‘yicha 7 kun ichida yangi dalil bilan apellyatsiya yuboriladi.','Сохраните комментарии и доказательства в споре. Апелляция с новыми данными доступна 7 дней.','Keep comments and evidence on the case page. Appeal a decision with new evidence within 7 days.'],'href':'/help/refunds'},
 {'id':'safety','title':['Hisob va kod xavfsizligi','Безопасность аккаунта и кодов','Account and code safety'],'body':['Parol, OTP va tiklash kodlarini chat yoki ochiq rasmlarda yubormang. Himoyalangan buyurtma yetkazishidan foydalaning.','Не отправляйте пароли, OTP и коды восстановления в чате или на фото. Используйте защищённую доставку.','Do not send passwords, OTPs or recovery codes in chat or photos. Use protected order delivery.'],'href':'/help/chat'},
 {'id':'notifications','title':['Bildirishnoma va saqlangan qidiruvlar','Уведомления и сохранённые поиски','Notifications and saved searches'],'body':['Profil sozlamalarida kanallarni tanlang. Qidiruv va kerakli narxni saqlab kuzating.','Выберите каналы в профиле. Сохраните поиск и желаемую цену.','Choose channels in your profile. Save a search or target price to follow listings.'],'href':'/#notification-settings'},
]

def migrate(db,postgres=False):
    if postgres:
        # Production migrations are applied before rollout. Avoid repeating dozens
        # of DDL round trips on every serverless cold start; the caller still audits RLS.
        names=(*TABLES,*COLUMNS)
        marks=','.join('?' for _ in names)
        columns={}
        for row in db.execute(f"SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name IN ({marks})",names):columns.setdefault(row['table_name'],set()).add(row['column_name'])
        if all(table in columns for table in TABLES) and all(set(fields)<=columns.get(table,set()) for table,fields in COLUMNS.items()):return
    for sql in SCHEMA:db.execute(sql)
    for table,fields in COLUMNS.items():
        known=set() if postgres else {r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
        for field,definition in fields.items():
            if postgres:db.execute(f'ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS {field} {definition}')
            elif field not in known:db.execute(f'ALTER TABLE {table} ADD COLUMN {field} {definition}')
    if postgres:
        for table in TABLES:
            db.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            db.execute(f'REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated')

def normalize(value):return re.sub(r'[^\w]+',' ',unicodedata.normalize('NFKC',str(value)).casefold()).strip()
def game_query(value):
    value=normalize(value)
    choices={normalize(alias):slug for slug,aliases in GAME_ALIASES.items() for alias in [slug,*aliases]}
    if value in choices:return choices[value]
    close=get_close_matches(value,list(choices),n=1,cutoff=.82)
    return choices[close[0]] if close else None

def schema(game,typ):
    fields=list(dict.fromkeys(FIELD_TYPES.get(typ,['region','platform'])+GAME_FIELDS.get(game,{}).get(typ,[])))
    return [{'key':k,'label':LABELS.get(k,k.replace('_',' ').capitalize()),'numeric':k in ('float_value','account_level','mmr','behavior_score','premier_rating','pattern')} for k in fields]

def validate_game(attrs,game,typ,core):
    for key in ('account_level','mmr','behavior_score','premier_rating','pattern'):
        value=attrs.get(key)
        if value and (not str(value).isdigit() or not 0<=int(value)<=10000000):raise core['HttpError'](400,key+': 0–10000000 oralig‘ida butun son kiriting.')
    if game!='counter-strike-2' and attrs.get('float_value'):raise core['HttpError'](400,'Float qiymati faqat CS2 buyumlariga mos.')
    return attrs

def settings(db,uid):
    row=db.execute('SELECT settings_json FROM experience_preferences WHERE user_id=?',(uid,)).fetchone()
    saved=json.loads(row['settings_json']) if row else {}
    return {**{'order':True,'message':True,'favorite':True,'seller_listing':True,'saved_search':True,'email':False,'browser':False},**saved}

def notification_allowed(db,uid,kind):
    group='order' if kind in ('delivery','order_complete','order','order_case','dispute','delivery_deadline') else kind
    if group not in ('message','favorite','seller_listing','saved_search','order'):return True
    if kind=='message':
        return settings(db,uid).get(group,True)
    return settings(db,uid).get(group,True)

def insight(db,lid,kind):
    if kind not in ('view','favorite','chat','cart','order'):return
    day=datetime.now(timezone.utc).date().isoformat()
    db.execute('INSERT INTO listing_insights(listing_id,day,kind,total) VALUES(?,?,?,1) ON CONFLICT(listing_id,day,kind) DO UPDATE SET total=listing_insights.total+1',(lid,day,kind))

def stock_check(db,lid,core,projected=None):
    row=db.execute('SELECT a.*,l.stock,l.reserved,l.seller_id,l.title FROM seller_stock_alerts a JOIN listings l ON l.id=a.listing_id WHERE a.listing_id=?',(lid,)).fetchone()
    if not row:return
    left=max(0,row['stock']-row['reserved']) if projected is None else max(0,projected)
    if left>row['threshold']:db.execute('UPDATE seller_stock_alerts SET alerted=0 WHERE listing_id=?',(lid,));return
    if db.execute('UPDATE seller_stock_alerts SET alerted=1 WHERE listing_id=? AND alerted=0',(lid,)).rowcount:
        core['notify'](db,row['seller_id'],'low_stock','Mahsulot qoldig‘i kamaydi',row['title']+' · '+str(left),' /seller'.strip())

def price_alerts(db,lid,core):
    row=db.execute("SELECT title,price_minor,currency FROM listings WHERE id=? AND status='published'",(lid,)).fetchone()
    if not row:return
    for watch in db.execute('SELECT * FROM price_watches WHERE listing_id=? AND target_minor>=? AND (last_triggered_minor IS NULL OR last_triggered_minor>?)',(lid,row['price_minor'],row['price_minor'])).fetchall():
        core['notify'](db,watch['user_id'],'favorite','Kuzatilgan narxga tushdi',row['title']+' · '+str(row['price_minor'])+' '+row['currency'],'/listing/'+lid)
        db.execute('UPDATE price_watches SET last_triggered_minor=? WHERE user_id=? AND listing_id=?',(row['price_minor'],watch['user_id'],lid))
    stock_check(db,lid,core)

def quality(db,sid,days=30):
    cutoff=(datetime.now(timezone.utc)-timedelta(days=days)).isoformat(timespec='seconds')
    rows=db.execute('SELECT i.*,o.status,o.created_at order_created FROM order_items i JOIN orders o ON o.id=i.order_id WHERE i.seller_id=?',(sid,)).fetchall()
    eligible=[r for r in rows if ops.utc(r['order_created'])>=ops.utc(cutoff) and r['status']!='pending_payment']
    delivered=[r for r in eligible if r['delivered_quantity']>=r['quantity']];on_time=0;timed=0
    for r in delivered:
        if not r['delivery_due_at']:continue
        stamp=db.execute('SELECT submitted_at FROM deliveries WHERE order_item_id=?',(r['id'],)).fetchone()
        if stamp:timed+=1;on_time+=int(ops.utc(stamp['submitted_at'])<=ops.utc(r['delivery_due_at']))
    orders={r['order_id'] for r in eligible};cancelled={r['order_id'] for r in eligible if r['status'] in ('cancelled','refunded')};disputes={r['order_id'] for r in eligible if db.execute("SELECT 1 FROM reports WHERE order_id=? AND reason='order_dispute'",(r['order_id'],)).fetchone()}
    reviews=[dict(r) for r in db.execute('SELECT l.product_type,COUNT(*) count,AVG(r.rating) rating FROM visible_reviews r JOIN order_items i ON i.id=r.order_item_id JOIN listings l ON l.id=i.listing_id WHERE r.seller_id=? GROUP BY l.product_type',(sid,))]
    for r in reviews:r['rating']=float(r['rating']) if r['rating'] is not None else None
    return {'days':days,'orders':len(orders),'delivered':len(delivered),'on_time_percent':round(on_time*100/timed) if timed else None,'timed_deliveries':timed,'cancellations':len(cancelled),'disputes':len(disputes),'cancellation_percent':round(len(cancelled)*100/len(orders),1) if orders else None,'dispute_percent':round(len(disputes)*100/len(orders),1) if orders else None,'ratings_by_type':reviews}

def signature(row):
    attrs=row.get('attributes') or json.loads(row.get('attributes_json') or '{}')
    keys={'item':['item_name','item_variant','condition','pattern'],'currency':['amount','unit'],'code':['code_kind','redemption_region'],'service':['service_scope','service_duration'],'digital':['product_format','access_method'],'account':['rank','account_level','server_id','competitive_rank','current_rank']}.get(row['product_type'],[])
    return [row.get('game_id') or row.get('game_slug'),row['product_type'],normalize(row.get('platform','')),normalize(row.get('region',''))]+[normalize(attrs.get(k,'')) for k in keys]

def parse_import(raw,fmt):
    if len(raw)>2*1024*1024:raise ValueError('Import hajmi 2 MB dan oshmasin.')
    if fmt=='csv':
        content=raw.decode('utf-8-sig');reader=csv.DictReader(io.StringIO(content));rows=[]
        if not reader.fieldnames or len(reader.fieldnames)>40:raise ValueError('CSV sarlavhalari noto‘g‘ri.')
        for row in reader:
            rows.append(row)
            if len(rows)>200:raise ValueError('Bir importda 200 tagacha e’lon mumkin.')
        return rows
    if fmt!='xlsx':raise ValueError('CSV yoki XLSX fayl tanlang.')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos=archive.infolist()
        if sum(i.file_size for i in infos)>8*1024*1024 or len(infos)>100:raise ValueError('XLSX fayl hajmi juda katta.')
        ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'};shared=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            shared=[''.join(n.itertext()) for n in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si',ns)]
        names=[n for n in archive.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml',n)]
        if not names:raise ValueError('XLSX sahifasi topilmadi.')
        grid=[]
        for row in ET.fromstring(archive.read(sorted(names)[0])).findall('.//m:sheetData/m:row',ns):
            cells={}
            for c in row.findall('m:c',ns):
                if c.find('m:f',ns) is not None:raise ValueError('Importda formulalardan foydalanmang; qiymatlarni qo‘ying.')
                letters=re.sub('[0-9]','',c.get('r','A'));index=0
                for letter in letters:index=index*26+ord(letter)-64
                if index>40:raise ValueError('Ustunlar 40 tadan oshmasin.')
                v=c.find('m:v',ns);value=v.text if v is not None else ''.join(c.find('m:is',ns).itertext()) if c.find('m:is',ns) is not None else ''
                if c.get('t')=='s':value=shared[int(value)]
                cells[index-1]=value
            grid.append(cells)
            if len(grid)>201:raise ValueError('Bir importda 200 tagacha e’lon mumkin.')
        if not grid:return []
        headers=[grid[0].get(i,'') for i in range(max(grid[0])+1)]
        return [{h:str(row.get(i,'')) for i,h in enumerate(headers)} for row in grid[1:]]

def validate_import(rows,core):
    good=[];errors=[]
    allowed={'game_name','category_id','title','description','price_minor','stock','platform','region','delivery_eta','requirements','item_name','unit','amount','code_kind','redemption_region','product_format','access_method','min_quantity','unit_label',*core['LISTING_PUBLIC_ATTRIBUTES']}
    for n,row in enumerate(rows,2):
        issues={};clean={}
        for k in set(row)-allowed:issues[k]='Noma’lum ustun.'
        for k,minimum,maximum in [('game_name',2,80),('category_id',1,60),('title',5,120),('description',60,5000),('platform',1,60),('region',1,60),('delivery_eta',2,60),('requirements',1,1000)]:
            try:clean[k]=core['clean_text'](row.get(k,''),k,minimum,maximum)
            except core['HttpError']:issues[k]=f'{minimum}–{maximum} belgi kiriting.'
        for k,default,minimum,maximum in [('price_minor','',1,10**12),('stock','1',0,10000),('min_quantity','1',1,10000)]:
            try:
                raw=str(row.get(k) or default)
                if not raw.isdigit() or not minimum<=int(raw)<=maximum:raise ValueError()
                clean[k]=int(raw)
            except ValueError:issues[k]='Ruxsat etilgan oraliqda butun son kiriting.'
        clean['unit_label']=str(row.get('unit_label') or 'item')[:40]
        clean['attributes']={k:str(row[k]) for k in core['LISTING_PUBLIC_ATTRIBUTES'] if row.get(k)}
        clean['submit_for_review']=False
        if issues:errors.append({'row':n,'fields':issues})
        good.append(clean)
    return good,errors

def allocate_codes(db,oid,core):
    """Called inside the existing verified payment transaction; never settles funds."""
    import trade_workflows as trade
    for item in db.execute('SELECT i.*,l.automatic_delivery,l.product_type FROM order_items i JOIN listings l ON l.id=i.listing_id WHERE i.order_id=?',(oid,)).fetchall():
        insight(db,item['listing_id'],'order')
        stock_check(db,item['listing_id'],core)
        if not json.loads(item['snapshot_json'] or '{}').get('automatic_delivery',item['automatic_delivery']) or item['product_type']!='code' or item['delivered_quantity']>=item['quantity']:continue
        rows=db.execute('SELECT id,cipher FROM seller_code_inventory WHERE listing_id=? AND order_item_id IS NULL ORDER BY created_at,id LIMIT ?',(item['listing_id'],item['quantity'])).fetchall()
        if len(rows)!=item['quantity']:raise core['HttpError'](409,'Avtomatik kodlar qoldig‘i yetarli emas; to‘lov tasdiqlanmadi.')
        payload=[]
        for row in rows:
            if db.execute('UPDATE seller_code_inventory SET order_item_id=?,allocated_at=CURRENT_TIMESTAMP WHERE id=? AND order_item_id IS NULL',(item['id'],row['id'])).rowcount!=1:raise core['HttpError'](409,'Kod boshqa buyurtmaga band qilindi.')
            payload.append(trade.decrypt(core,row['cipher'],'inventory:'+row['id']))
        body='\n'.join(payload);bid=core['ident']()
        db.execute('INSERT INTO delivery_batches(id,order_item_id,seller_id,quantity,delivered_total,payload,request_key) VALUES(?,?,?,?,?,?,?)',(bid,item['id'],item['seller_id'],item['quantity'],item['quantity'],trade.encrypt(core,body,'batch:'+bid),'automatic:'+item['id']))
        db.execute('INSERT INTO deliveries(id,order_item_id,seller_id,protected_payload) VALUES(?,?,?,?)',(core['ident'](),item['id'],item['seller_id'],trade.encrypt(core,body,item['id'])))
        db.execute('UPDATE order_items SET delivered_quantity=quantity WHERE id=?',(item['id'],))
        core['notify'](db,db.execute('SELECT buyer_id FROM orders WHERE id=?',(oid,)).fetchone()['buyer_id'],'delivery','Kod himoyalangan buyurtmaga yetkazildi','Kodlarni buyurtma ichida ko‘ring.','/order/'+oid)
    if not db.execute('SELECT 1 FROM order_items WHERE order_id=? AND delivered_quantity<quantity',(oid,)).fetchone():
        db.execute("UPDATE orders SET status='delivered',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='paid'",(oid,));core['event'](db,oid,None,'paid','delivered','Avtomatik himoyalangan yetkazish')

def route(handler,db,ctx,method,path,qs,data,raw,core):
    uid=ctx['uid'];error=core['HttpError'];text=core['clean_text'];require=core['require_user'];verify=core['require_verified'];now=datetime.now(timezone.utc)
    param=lambda k,default='':qs.get(k,[default])[0]
    if path=='/api/conversations' and method=='GET':
        require(ctx);query=param('q').strip()[:120];archive=1 if param('archived')=='1' else 0
        rows=db.execute("SELECT c.*,l.title listing_title,o.reference order_reference,CASE WHEN c.buyer_id=? THEN su.display_name ELSE bu.display_name END other_name,COALESCE(p.muted,0) muted,COALESCE(p.archived,0) archived,(SELECT body FROM messages m WHERE m.conversation_id=c.id ORDER BY m.created_at DESC,m.id DESC LIMIT 1) last_message,(SELECT COUNT(*) FROM messages m WHERE m.conversation_id=c.id AND m.sender_id<>? AND m.read_at IS NULL) unread FROM conversations c LEFT JOIN listings l ON l.id=c.listing_id LEFT JOIN orders o ON o.id=c.order_id JOIN users su ON su.id=c.seller_id JOIN users bu ON bu.id=c.buyer_id LEFT JOIN conversation_preferences p ON p.conversation_id=c.id AND p.user_id=? WHERE (c.buyer_id=? OR c.seller_id=?) AND COALESCE(p.archived,0)=? ORDER BY c.created_at DESC LIMIT 1000",(uid,uid,uid,uid,uid,archive)).fetchall()
        result=[]
        for row in rows:
            r=dict(row)
            if query and query.casefold() not in ' '.join(str(r.get(k) or '') for k in ('other_name','listing_title','order_reference','last_message')).casefold() and not db.execute('SELECT 1 FROM messages WHERE conversation_id=? AND lower(body) LIKE ?',(r['id'],'%'+query.casefold()+'%')).fetchone():continue
            if r['muted']:r['unread']=0
            result.append(r)
        return result
    message_match=re.fullmatch(r'/api/conversations/([^/]+)/messages',path)
    if message_match and method=='POST':
        verify(ctx);cid=message_match.group(1);conv=db.execute('SELECT * FROM conversations WHERE id=?',(cid,)).fetchone()
        if not conv or uid not in (conv['buyer_id'],conv['seller_id']):raise error(404,'Suhbat topilmadi.')
        ops.chat_allowed(db,conv,uid,core);body=text(data.get('body'),'Xabar',1,2000);key=text(data.get('request_key') or core['ident'](),'So‘rov kaliti',1,100)
        core['check_rate'](db,'message',uid,40,3600);db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('UPDATE conversations SET created_at=created_at WHERE id=?',(cid,))
            prior=db.execute('SELECT message_id FROM message_retry_keys WHERE conversation_id=? AND sender_id=? AND request_key=?',(cid,uid,key)).fetchone()
            if prior:db.execute('COMMIT');return {'id':prior['message_id'],'idempotent':True}
            mid=core['ident']();db.execute('INSERT INTO messages(id,conversation_id,sender_id,body) VALUES(?,?,?,?)',(mid,cid,uid,body));db.execute('INSERT INTO message_retry_keys(conversation_id,sender_id,request_key,message_id) VALUES(?,?,?,?)',(cid,uid,key,mid))
            other=conv['seller_id'] if uid==conv['buyer_id'] else conv['buyer_id'];prefs=db.execute('SELECT muted FROM conversation_preferences WHERE user_id=? AND conversation_id=?',(other,cid)).fetchone()
            if not prefs or not prefs['muted']:core['notify'](db,other,'message','Yangi xabar','Suhbatda yangi xabar bor.','/conversation/'+cid)
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'id':mid}
    if path=='/api/catalogue/schema' and method=='GET':return {'fields':schema(param('game'),param('type','item')),'games':GAME_FIELDS,'recommendation':['Verified buyer reviews','Completed sales and response times','Delivery speed and on-time fulfilment','Seller-caused cancellations and upheld disputes']}
    if path=='/api/catalogue/facets' and method=='GET':
        category=param('category');typ=param('type')
        if category:
            row=db.execute('SELECT product_type FROM categories WHERE slug=?',(category,)).fetchone()
            if row:typ=row['product_type']
        fields=schema(param('game'),typ) if typ else [{'key':k,'label':LABELS.get(k,k.capitalize())} for k in ('platform','region')]
        out={};joins=' FROM listings l JOIN games g ON g.id=l.game_id JOIN categories c ON c.id=l.category_id JOIN seller_profiles s ON s.user_id=l.seller_id'
        for f in fields:
            key=f['key']
            if key not in ('platform','region','rank','server','condition','item_type','item_variant','rarity','account_level','redemption_region','code_kind','unit'):continue
            filters={k:v for k,v in qs.items() if k!=key};where,args=core['catalogue_predicates'](db,filters,uid)
            expression='l.'+key if key in ('platform','region') else f"COALESCE(l.attributes_json::jsonb->>'{key}','')" if core['DATABASE_URL'] else f"COALESCE(json_extract(l.attributes_json,'$.{key}'),'')"
            rows=db.execute(f"SELECT {expression} value,COUNT(*) count {joins} WHERE {' AND '.join(where)} AND l.stock>l.reserved AND {expression}<>'' GROUP BY {expression} ORDER BY COUNT(*) DESC,{expression} LIMIT 60",tuple(args)).fetchall()
            out[key]=[dict(r) for r in rows]
        return {'type':typ,'fields':fields,'facets':out}
    if path=='/api/help/search' and method=='GET':
        q=normalize(param('q'))[:120]
        rows=[r for r in TOPICS if not q or q in normalize(' '.join(r['title']+r['body']))]
        if not rows and q:rows=sorted(TOPICS,key=lambda r:SequenceMatcher(None,q,normalize(' '.join(r['title']))).ratio(),reverse=True)[:3]
        return {'items':rows}
    match=re.fullmatch(r'/api/catalogue/offers/([^/]+)',path)
    if match and method=='GET':
        lid=match.group(1);it=core['listing_detail'](db,lid,uid)
        if not it or it['status'] not in core['PUBLIC_LISTING_STATES'] or not core['listing_allowed_for_production'](db,it['game_id'],it['product_type']):raise error(404,'Mahsulot topilmadi.')
        candidates=db.execute("SELECT * FROM listings WHERE game_id=? AND product_type=? AND status='published' AND stock>reserved ORDER BY price_minor LIMIT 1000",(it['game_id'],it['product_type'])).fetchall();key=signature(it);rows=[]
        for row in candidates:
            if core['MODE']=='production' and core['launch_readiness'].test_listing(db,row['id']):continue
            if signature(dict(row))!=key:continue
            seller=db.execute('SELECT shop_name FROM seller_profiles WHERE user_id=?',(row['seller_id'],)).fetchone()
            rows.append({'id':row['id'],'seller_name':seller['shop_name'] if seller else '', 'store_id':row['seller_id'],'price_minor':row['price_minor'],'currency':row['currency'],'delivery_eta':row['delivery_eta'],'available':row['stock']-row['reserved'],'min_quantity':row['min_quantity'],'unit_label':row['unit_label']})
        return {'items':rows[:30],'matched_attributes':key[1:]}
    if path=='/api/experience/settings' and method in ('GET','POST'):
        require(ctx)
        if method=='GET':return {k:v for k,v in settings(db,uid).items() if k!='push_devices'}
        allowed={'order','message','favorite','seller_listing','saved_search','email','browser'}
        if set(data)-allowed or any(type(v) is not bool for v in data.values()):raise error(400,'Bildirishnoma sozlamalarini tekshiring.')
        if data.get('email') and not ctx['user']['email_verified']:raise error(403,'Avval emailni tasdiqlang.')
        value=core['launch_readiness'].save_preferences(db,uid,lambda prefs:prefs.update(data),core)
        return {k:v for k,v in settings(db,uid).items() if k!='push_devices'}
    match=re.fullmatch(r'/api/collections/(recent|compare)',path)
    if match and method in ('GET','POST'):
        require(ctx);kind=match.group(1);limit=20 if kind=='recent' else 3
        if method=='POST':
            ids=data.get('ids')
            if not isinstance(ids,list) or len(ids)>limit or any(not isinstance(i,str) for i in ids):raise error(400,'Ro‘yxat noto‘g‘ri.')
            db.execute('BEGIN IMMEDIATE')
            try:
                # Serialize collection/preferences writes using a base-schema column;
                # presence tracking is optional on existing production databases.
                db.execute('UPDATE users SET display_name=display_name WHERE id=?',(uid,));db.execute('DELETE FROM account_collections WHERE user_id=? AND kind=?',(uid,kind))
                for n,lid in enumerate(dict.fromkeys(ids)):
                    if db.execute("SELECT id FROM listings WHERE id=? AND status IN ('published','sold_out')",(lid,)).fetchone():db.execute('INSERT INTO account_collections(user_id,kind,listing_id,updated_at) VALUES(?,?,?,?)',(uid,kind,lid,ops.iso(now-timedelta(seconds=n))))
                prefs=settings(db,uid);prefs['collections_initialized']=list(set(prefs.get('collections_initialized',[])+[kind]))
                db.execute('INSERT INTO experience_preferences(user_id,settings_json) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET settings_json=excluded.settings_json',(uid,json.dumps(prefs)))
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
        return {'initialized':kind in settings(db,uid).get('collections_initialized',[]),'ids':[r['listing_id'] for r in db.execute('SELECT listing_id FROM account_collections WHERE user_id=? AND kind=? ORDER BY updated_at DESC',(uid,kind))]}
    match=re.fullmatch(r'/api/price-watches/([^/]+)',path)
    if match and method in ('GET','POST','DELETE'):
        require(ctx);lid=match.group(1)
        if method=='POST':
            target=data.get('target_minor')
            if type(target) is not int or not 1<=target<=10**12:raise error(400,'Kerakli narx musbat butun son bo‘lsin.')
            item=core['listing_detail'](db,lid,uid)
            if not item or item['status']!='published':raise error(404,'E’lon topilmadi.')
            db.execute('INSERT INTO price_watches(user_id,listing_id,target_minor) VALUES(?,?,?) ON CONFLICT(user_id,listing_id) DO UPDATE SET target_minor=excluded.target_minor,last_triggered_minor=NULL',(uid,lid,target));price_alerts(db,lid,core)
        elif method=='DELETE':db.execute('DELETE FROM price_watches WHERE user_id=? AND listing_id=?',(uid,lid))
        return core['rowdict'](db.execute('SELECT target_minor,last_triggered_minor FROM price_watches WHERE user_id=? AND listing_id=?',(uid,lid)).fetchone())
    if path=='/api/catalogue/view' and method=='POST':
        lid=text(data.get('listing_id'),'E’lon',1,100);row=core['listing_detail'](db,lid,uid)
        if not row or row['status']!='published' or row['seller_id']==uid:return {'ok':True}
        if not core['listing_allowed_for_production'](db,row['game_id'],row['product_type']):raise error(404,'E’lon topilmadi.')
        day=now.date().isoformat();visitor=hmac.new(core['SESSION_SECRET'].encode(),(day+':'+str(uid or handler.client_address[0])).encode(),hashlib.sha256).hexdigest()
        changed=db.execute('INSERT INTO listing_view_keys(listing_id,day,visitor_key) VALUES(?,?,?) ON CONFLICT(listing_id,day,visitor_key) DO NOTHING',(lid,day,visitor))
        if changed.rowcount:insight(db,lid,'view')
        return {'ok':True}
    if path=='/api/seller/insights' and method=='GET':
        verify(ctx);core['seller_ok'](db,uid)
        try:days=int(param('days','30'))
        except ValueError:raise error(400,'Davr noto‘g‘ri.')
        if days not in (7,30,90):raise error(400,'7, 30 yoki 90 kun tanlang.')
        cutoff=(now-timedelta(days=days)).date().isoformat()
        funnel=[dict(r) for r in db.execute('SELECT l.id,l.title,e.kind,COALESCE(SUM(e.total),0) total FROM listings l LEFT JOIN listing_insights e ON e.listing_id=l.id AND e.day>=? WHERE l.seller_id=? GROUP BY l.id,l.title,e.kind ORDER BY l.title',(cutoff,uid))]
        return {'quality':quality(db,uid,days),'listings':funnel,'reply_seconds':core['marketplace_features'].profile(db,uid,uid,core)['avg_reply_seconds']}
    if path=='/api/seller/import/preview' and method=='POST':
        verify(ctx);core['seller_ok'](db,uid);core['check_rate'](db,'listing_import',uid,10,3600)
        try:rows=parse_import(raw,param('format','csv'));cleaned,errors=validate_import(rows,core)
        except (ValueError,UnicodeError,zipfile.BadZipFile,ET.ParseError,KeyError,IndexError) as exc:raise error(400,'Import o‘qilmadi: '+str(exc)[:150])
        if not rows:raise error(400,'Importda kamida bitta mahsulot bo‘lsin.')
        # Validate catalogue and product-type attributes before creating any drafts.
        for i,row in enumerate(cleaned,2):
            category=db.execute('SELECT product_type FROM categories WHERE id=?',(row.get('category_id'),)).fetchone()
            if not category:errors.append({'row':i,'fields':{'category_id':'Mavjud kategoriya ID sini tanlang.'}});continue
            try:
                core['seller_catalog'].validate_selection(db,row.get('game_name',''),row.get('category_id'),error)
                core['validate_listing_attributes'](row['attributes'],category['product_type'],True)
                validate_game(row['attributes'],game_query(row.get('game_name','')) or '',category['product_type'],core)
            except error as exc:errors.append({'row':i,'fields':{'attributes':exc.message}})
        iid=core['ident']();db.execute('INSERT INTO listing_imports(id,seller_id,rows_json,errors_json,expires_at) VALUES(?,?,?,?,?)',(iid,uid,json.dumps(cleaned),json.dumps(errors),ops.iso(now+timedelta(minutes=30))))
        return {'id':iid,'rows':cleaned,'errors':errors,'valid':not errors,'expires_in_minutes':30}
    match=re.fullmatch(r'/api/seller/import/([^/]+)/commit',path)
    if match and method=='POST':
        verify(ctx);core['seller_ok'](db,uid);iid=match.group(1);db.execute('BEGIN IMMEDIATE')
        try:
            changed=db.execute('UPDATE listing_imports SET committed=1 WHERE id=? AND seller_id=? AND committed=0 AND expires_at>?',(iid,uid,ops.iso(now)))
            if changed.rowcount!=1:raise error(409,'Import muddati tugagan yoki allaqachon qabul qilingan.')
            row=db.execute('SELECT * FROM listing_imports WHERE id=?',(iid,)).fetchone()
            if json.loads(row['errors_json']):raise error(400,'Avval import xatolarini to‘g‘rilang.')
            ids=[]
            for value in json.loads(row['rows_json']):
                value['accept_account_terms']=data.get('accept_account_terms') is True
                result=handler.route(db,{**ctx,'bulk_import':True},'POST','/api/listings',{},value);result=result[1] if isinstance(result,tuple) else result;ids.append(result['id']);db.execute('UPDATE listings SET min_quantity=?,unit_label=? WHERE id=?',(value['min_quantity'],value['unit_label'],result['id']))
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'ids':ids,'status':'draft','count':len(ids)}
    match=re.fullmatch(r'/api/seller/listings/([^/]+)/(stock-alert|codes|sales-settings)',path)
    if match and method in ('GET','POST'):
        verify(ctx);core['seller_ok'](db,uid);lid,action=match.groups();row=db.execute('SELECT * FROM listings WHERE id=? AND seller_id=?',(lid,uid)).fetchone()
        if not row:raise error(404,'E’lon topilmadi.')
        if action=='stock-alert':
            if method=='POST':
                value=data.get('threshold')
                if type(value) is not int or not 0<=value<=10000:raise error(400,'Chegara 0–10000 bo‘lsin.')
                db.execute('INSERT INTO seller_stock_alerts(listing_id,threshold) VALUES(?,?) ON CONFLICT(listing_id) DO UPDATE SET threshold=excluded.threshold,alerted=0',(lid,value));stock_check(db,lid,core)
            return core['rowdict'](db.execute('SELECT threshold,alerted FROM seller_stock_alerts WHERE listing_id=?',(lid,)).fetchone()) or {'threshold':2,'alerted':False}
        if action=='sales-settings':
            if method=='GET':return {'min_quantity':row['min_quantity'],'unit_label':row['unit_label'],'automatic_delivery':bool(row['automatic_delivery'])}
            minimum=data.get('min_quantity',1);unit=text(data.get('unit_label','item'),'Birlik',1,40);auto=data.get('automatic_delivery',False)
            if type(minimum) is not int or not 1<=minimum<=10000 or type(auto) is not bool:raise error(400,'Minimal son yoki yetkazish sozlamasi noto‘g‘ri.')
            available=db.execute('SELECT COUNT(*) n FROM seller_code_inventory WHERE listing_id=? AND order_item_id IS NULL',(lid,)).fetchone()['n']
            if auto and (row['product_type']!='code' or available<row['stock']-row['reserved']):raise error(409,'Avtomatik yetkazish uchun qoldiq miqdoricha kod yuklang. Faqat kod mahsulotlari qo‘llanadi.')
            next_status='pending_review' if (minimum!=row['min_quantity'] or unit!=row['unit_label'] or int(auto)!=row['automatic_delivery']) and row['status'] in ('published','approved_private') else row['status']
            db.execute('UPDATE listings SET min_quantity=?,unit_label=?,automatic_delivery=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(minimum,unit,int(auto),next_status,lid));return {'ok':True,'status':next_status}
        if row['product_type']!='code':raise error(400,'Kod ombori faqat kod mahsulotlariga tegishli.')
        if method=='POST':
            codes=data.get('codes')
            if not isinstance(codes,list) or not 1<=len(codes)<=100 or any(not isinstance(c,str) or not 2<=len(c.strip())<=300 for c in codes):raise error(400,'2–300 belgili 1–100 ta kod yuboring.')
            import trade_workflows as trade
            db.execute('BEGIN IMMEDIATE');added=0
            try:
                db.execute('UPDATE listings SET updated_at=updated_at WHERE id=?',(lid,))
                for code in codes:
                    key=core['ident']();fingerprint=hmac.new(core['os'].environ.get('DELIVERY_ENCRYPTION_KEY','').encode(),code.strip().encode(),hashlib.sha256).hexdigest()
                    added+=db.execute('INSERT INTO seller_code_inventory(id,listing_id,seller_id,cipher,fingerprint) VALUES(?,?,?,?,?) ON CONFLICT(listing_id,fingerprint) DO NOTHING',(key,lid,uid,trade.encrypt(core,code.strip(),'inventory:'+key),fingerprint)).rowcount
                db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
            core['audit'](db,uid,'code_inventory_uploaded','listing',lid,{'count':added})
        counts=db.execute('SELECT COUNT(*) total,SUM(CASE WHEN order_item_id IS NULL THEN 1 ELSE 0 END) available FROM seller_code_inventory WHERE listing_id=?',(lid,)).fetchone()
        return {'total':counts['total'],'available':counts['available'] or 0,'added':added if method=='POST' else 0}
    if path=='/api/seller/quick-replies' and method in ('GET','POST'):
        verify(ctx)
        if not ctx['user']['seller']:raise error(403,'Sotuvchi profili kerak.')
        if method=='POST':
            if db.execute('SELECT COUNT(*) n FROM seller_quick_replies WHERE user_id=?',(uid,)).fetchone()['n']>=30:raise error(400,'30 tagacha tayyor javob saqlash mumkin.')
            db.execute('INSERT INTO seller_quick_replies(id,user_id,title,body) VALUES(?,?,?,?)',(core['ident'](),uid,text(data.get('title'),'Nom',2,60),text(data.get('body'),'Javob',2,2000)))
        return [dict(r) for r in db.execute('SELECT id,title,body FROM seller_quick_replies WHERE user_id=? ORDER BY title',(uid,))]
    match=re.fullmatch(r'/api/seller/quick-replies/([^/]+)',path)
    if match and method=='DELETE':require(ctx);db.execute('DELETE FROM seller_quick_replies WHERE id=? AND user_id=?',(match.group(1),uid));return {'ok':True}
    match=re.fullmatch(r'/api/conversations/([^/]+)/(preferences|report)',path)
    if match and method in ('GET','POST'):
        require(ctx);cid,action=match.groups();conv=db.execute('SELECT * FROM conversations WHERE id=? AND (buyer_id=? OR seller_id=?)',(cid,uid,uid)).fetchone()
        if not conv:raise error(404,'Suhbat topilmadi.')
        if action=='preferences':
            if method=='POST':
                if set(data)-{'muted','archived'} or any(type(v) is not bool for v in data.values()):raise error(400,'Suhbat sozlamasi noto‘g‘ri.')
                old=core['rowdict'](db.execute('SELECT muted,archived FROM conversation_preferences WHERE user_id=? AND conversation_id=?',(uid,cid)).fetchone()) or {'muted':0,'archived':0}
                db.execute('INSERT INTO conversation_preferences(user_id,conversation_id,muted,archived) VALUES(?,?,?,?) ON CONFLICT(user_id,conversation_id) DO UPDATE SET muted=excluded.muted,archived=excluded.archived',(uid,cid,int(data.get('muted',old['muted'])),int(data.get('archived',old['archived']))))
            return core['rowdict'](db.execute('SELECT muted,archived FROM conversation_preferences WHERE user_id=? AND conversation_id=?',(uid,cid)).fetchone()) or {'muted':0,'archived':0}
        if method=='POST':
            verify(ctx);core['check_rate'](db,'chat_report',uid,10,3600);body=text(data.get('details'),'Shikoyat',10,3000);mid=data.get('message_id','')
            if mid and not db.execute('SELECT 1 FROM messages WHERE id=? AND conversation_id=?',(mid,cid)).fetchone():raise error(400,'Xabar shu suhbatga tegishli emas.')
            rid=core['ident']();db.execute('INSERT INTO reports(id,reporter_id,order_id,reason,details) VALUES(?,?,?,?,?)',(rid,uid,conv['order_id'],'chat_abuse',json.dumps({'conversation_id':cid,'message_id':mid,'details':body})))
            for a in db.execute('SELECT user_id FROM admin_accounts LIMIT 30'):core['notify'](db,a['user_id'],'moderation','Chat shikoyati','Suhbat bo‘yicha shikoyatni ko‘ring.','/admin')
            return 201,{'id':rid}
    if path=='/api/experience/email-dispatch' and method=='GET':
        secret=core['os'].environ.get('CRON_SECRET','')
        if not secret or not hmac.compare_digest(handler.headers.get('Authorization',''),'Bearer '+secret):raise error(401,'Cron avtorizatsiyasi kerak.')
        return dispatch_emails(db,core)
    return UNHANDLED

def dispatch_emails(db,core,notification_id=None):
    if not core['email_service'].is_configured():return {'sent':0,'configured':False}
    sent=0;failed=0
    query="SELECT q.notification_id,q.user_id,n.title,n.body,n.kind FROM notification_outbox q JOIN notifications n ON n.id=q.notification_id WHERE (q.status='pending' OR (q.status='failed' AND n.kind='seller_verification_decision')) AND q.attempts<3"
    if notification_id: query+=' AND q.notification_id=?'
    for row in db.execute(query+' ORDER BY q.created_at LIMIT 50',(notification_id,) if notification_id else ()).fetchall():
        verification=row['kind']=='seller_verification_decision'
        user=db.execute('SELECT email,display_name,email_verified,suspended,language FROM users WHERE id=?',(row['user_id'],)).fetchone()
        if not user or not user['email_verified'] or (not verification and (user['suspended'] or not settings(db,row['user_id'])['email'] or not notification_allowed(db,row['user_id'],row['kind']))):
            db.execute("UPDATE notification_outbox SET status='skipped' WHERE notification_id=?",(row['notification_id'],));continue
        # Claim once. A crash leaves an unknown send outcome for operator review rather than double emailing.
        if not db.execute("UPDATE notification_outbox SET status='sending',attempts=attempts+1 WHERE notification_id=? AND (status='pending' OR (status='failed' AND ?=1)) AND attempts<3",(row['notification_id'],int(verification))).rowcount:continue
        try:
            if verification: core['email_service'].send_verification_update(user['email'],user['display_name'],row['title'],row['body'],row['notification_id'])
            else: core['email_service'].send_marketplace_alert(user['email'],user['display_name'],row['title'],language=user['language'])
            db.execute("UPDATE notification_outbox SET status='sent' WHERE notification_id=?",(row['notification_id'],));sent+=1
        except Exception:
            db.execute("UPDATE notification_outbox SET status='failed' WHERE notification_id=?",(row['notification_id'],));failed+=1
    return {'sent':sent,'failed':failed,'configured':True}

def correction(db,query):
    normalized=normalize(query)
    substitutions={'карамбит':'karambit','карамбіт':'karambit','karambti':'karambit','скин':'skin','скины':'skins','аккаунт':'account','akkaunt':'account','алмазы':'diamonds','olmos':'diamonds','валюта':'currency'}
    if normalized in substitutions:return substitutions[normalized]
    tokens=set()
    for r in db.execute("SELECT title FROM listings WHERE status='published' ORDER BY created_at DESC LIMIT 1000"):
        tokens.update(normalize(r['title']).split())
    closest=get_close_matches(normalized,list(tokens),n=1,cutoff=.8)
    return closest[0] if closest and closest[0]!=normalized else None

def compatibility(item,context):
    if not context:return []
    attrs=item.get('attributes') or json.loads(item.get('attributes_json') or '{}');issues=[]
    for key in ('platform','region'):
        actual=attrs.get('redemption_region') if key=='region' and item['product_type']=='code' else item.get(key,'')
        aliases={'uz':'uzbekistan','us':'united states','usa':'united states','ru':'russia','eu':'europe'}
        canonical=lambda v:aliases.get(normalize(v),normalize(v))
        selected=canonical(context.get(key,''));actual=canonical(actual or '')
        if selected and actual and actual not in ('global','all','any','all regions','barchasi','worldwide') and selected not in [canonical(v) for v in re.split('[,;/|]',str(attrs.get('redemption_region') if key=='region' and item['product_type']=='code' else item.get(key,'')))]:issues.append(key)
    return issues

def seo_html(path,core):
    """Public store/game pages have real status codes, canonical URLs and crawlable copy."""
    import html
    db=core['connect']()
    try:
        store=re.fullmatch(r'/store/([A-Za-z0-9_-]{1,100})',path);game=re.fullmatch(r'/games/([a-z0-9-]+)(?:/([a-z0-9-]+))?',path)
        if store:
            row=db.execute('SELECT s.shop_name,s.bio FROM seller_profiles s JOIN users u ON u.id=s.user_id WHERE s.user_id=? AND u.suspended=0',(store.group(1),)).fetchone()
            if not row:return None
            title=row['shop_name']+' — SentryLoot store';description=row['bio'] or 'Browse this seller’s game listings, verified buyer reviews and delivery details.'
            body='<h1>'+html.escape(title)+'</h1><p>'+html.escape(description)+'</p><p>Review this seller’s available listings, ratings, working hours and delivery terms.</p>'
        elif game:
            row=db.execute('SELECT name FROM games WHERE slug=? AND active=1',(game.group(1),)).fetchone()
            if not row:return None
            category=db.execute('SELECT name FROM categories WHERE slug=? AND active=1',(game.group(2),)).fetchone() if game.group(2) else None
            if game.group(2) and not category:return None
            title=row['name']+(' · '+category['name'] if category else '')+' — SentryLoot';description='Compare '+row['name']+' offers, seller reviews, regions, platforms and delivery terms.'
            body='<h1>'+html.escape(title)+'</h1><p>'+html.escape(description)+'</p><h2>Before you buy</h2><p>For accounts check rank, level and region. For items check the exact name and condition. For codes check the platform and activation region. Read publisher rules before ordering.</p><a href="/browse?'+html.escape(urlencode({'game':game.group(1),**({'category':game.group(2)} if game.group(2) else {})}),quote=True)+'">Browse offers and filters</a>'
        else:return None
    finally:db.close()
    template=(core['STATIC']/'index.html').read_text() if 'STATIC' in core else (core['ROOT']/'static/index.html').read_text()
    canonical=core['public_site_base']()+path
    template=re.sub(r'<title>.*?</title>',lambda _: '<title>'+html.escape(title)+'</title>',template,count=1,flags=re.S)
    for name,value in [('description',description)]:template=re.sub(r'<meta name="'+name+r'" content="[^"]*">',lambda _: '<meta name="'+name+'" content="'+html.escape(value,quote=True)+'">',template,count=1)
    template=re.sub(r'<link rel="canonical" href="[^"]*">',lambda _: '<link rel="canonical" href="'+html.escape(canonical,quote=True)+'">',template,count=1)
    for key,value in [('title',title),('description',description),('url',canonical)]:template=re.sub(r'<meta property="og:'+key+r'" content="[^"]*">',lambda _: '<meta property="og:'+key+'" content="'+html.escape(value,quote=True)+'">',template,count=1)
    template=re.sub(r'<main id="app"[^>]*>.*?</main>',lambda _: '<main id="app" tabindex="-1"><section class="page">'+body+'</section></main>',template,count=1,flags=re.S)
    return template.encode()

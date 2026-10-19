"""Participant-scoped fulfilment, cancellation, after-sale cases and saved searches.

Uses the caller's connection and transaction. Never creates a payment adapter.
"""
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import marketplace_operations as ops

UNHANDLED=object()
TABLES=('order_buyer_details','delivery_batches','order_artifacts','order_cancellations','cancellation_replies','order_cases','order_case_entries','saved_searches','saved_search_matches')
SCHEMA=(
 "CREATE TABLE IF NOT EXISTS order_buyer_details(order_item_id TEXT PRIMARY KEY REFERENCES order_items(id),payload TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
 "CREATE TABLE IF NOT EXISTS delivery_batches(id TEXT PRIMARY KEY,order_item_id TEXT NOT NULL REFERENCES order_items(id),seller_id TEXT NOT NULL REFERENCES users(id),quantity INTEGER NOT NULL CHECK(quantity>0),delivered_total INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL,request_key TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(order_item_id,request_key))",
 "CREATE TABLE IF NOT EXISTS order_artifacts(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),order_item_id TEXT REFERENCES order_items(id),case_id TEXT,owner_id TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL DEFAULT '',object_path TEXT UNIQUE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
 "CREATE TABLE IF NOT EXISTS order_cancellations(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),requester_id TEXT NOT NULL REFERENCES users(id),reason TEXT NOT NULL,details TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',resolution TEXT NOT NULL DEFAULT '',response_due_at TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
 "CREATE UNIQUE INDEX IF NOT EXISTS idx_cancellation_active ON order_cancellations(order_id) WHERE status IN ('pending','escalated')",
 "CREATE TABLE IF NOT EXISTS cancellation_replies(cancellation_id TEXT NOT NULL REFERENCES order_cancellations(id),seller_id TEXT NOT NULL REFERENCES users(id),decision TEXT NOT NULL,note TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(cancellation_id,seller_id))",
 "CREATE TABLE IF NOT EXISTS order_cases(id TEXT PRIMARY KEY,order_id TEXT NOT NULL REFERENCES orders(id),requester_id TEXT NOT NULL REFERENCES users(id),kind TEXT NOT NULL,source_id TEXT NOT NULL,reason TEXT NOT NULL,details TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',resolution TEXT NOT NULL DEFAULT '',remedy TEXT NOT NULL DEFAULT '',response_due_at TEXT NOT NULL,reviewed_by TEXT REFERENCES users(id),created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(order_id,requester_id,kind,source_id))",
 "CREATE TABLE IF NOT EXISTS order_case_entries(id TEXT PRIMARY KEY,case_id TEXT NOT NULL REFERENCES order_cases(id),sender_id TEXT NOT NULL REFERENCES users(id),body TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)",
 "CREATE TABLE IF NOT EXISTS saved_searches(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL,filters_json TEXT NOT NULL,fingerprint TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(user_id,fingerprint))",
 "CREATE TABLE IF NOT EXISTS saved_search_matches(search_id TEXT NOT NULL REFERENCES saved_searches(id) ON DELETE CASCADE,listing_id TEXT NOT NULL REFERENCES listings(id) ON DELETE CASCADE,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,PRIMARY KEY(search_id,listing_id))",
 "CREATE INDEX IF NOT EXISTS idx_delivery_batches_item ON delivery_batches(order_item_id,created_at)",
 "CREATE INDEX IF NOT EXISTS idx_order_artifacts_order ON order_artifacts(order_id,created_at)",
 "CREATE INDEX IF NOT EXISTS idx_order_cases_queue ON order_cases(status,updated_at)",
)
COLUMNS={'orders':{'completed_at':'TEXT','protection_until':'TEXT'},'order_items':{'delivered_quantity':'INTEGER NOT NULL DEFAULT 0'},'reports':{'resolved_at':'TEXT'},'delivery_batches':{'delivered_total':'INTEGER NOT NULL DEFAULT 0'}}
FILTERS={'q','game','category','type','seller','min','max','platform','region','server','rank','item_type','condition','item_variant','rarity','float_min','float_max','delivery','online','verified','account_level','redemption_region','code_kind','unit'}
REASONS={'changed_mind','wrong_details','seller_unavailable','late_delivery','other'}
CASE_REASONS={'account_reclaimed','not_as_described','invalid_code','missing_items','service_issue','new_evidence'}

def migrate(db,postgres=False):
    for statement in SCHEMA:db.execute(statement)
    for table,fields in COLUMNS.items():
        known=set() if postgres else {r['name'] for r in db.execute('PRAGMA table_info('+table+')')}
        for field,definition in fields.items():
            if postgres:db.execute(f'ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS {field} {definition}')
            elif field not in known:db.execute(f'ALTER TABLE {table} ADD COLUMN {field} {definition}')
    # Existing single-delivery records represent the whole line. Never overwrite new batches.
    db.execute('UPDATE order_items SET delivered_quantity=quantity WHERE delivered_quantity=0 AND id IN (SELECT order_item_id FROM deliveries) AND id NOT IN (SELECT order_item_id FROM delivery_batches)')
    if postgres:
        for table in TABLES:
            db.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            db.execute(f'REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated')

def policy(product_type):
    return {'version':'2026-10-fulfilment-1','days':14 if product_type=='account' else 7,'appeal_days':7,'issues':['account_reclaimed','not_as_described'] if product_type=='account' else {'code':['invalid_code','not_as_described'],'item':['missing_items','not_as_described'],'currency':['missing_items','not_as_described'],'service':['service_issue','not_as_described']}.get(product_type,['not_as_described']), 'exclusions':['buyer_caused_damage','publisher_action_unrelated_to_seller'],'financial_guarantee':False}

def account_order(db,oid):
    for row in db.execute('SELECT i.snapshot_json,l.product_type FROM order_items i JOIN listings l ON l.id=i.listing_id WHERE i.order_id=?',(oid,)):
        if json.loads(row['snapshot_json'] or '{}').get('product_type',row['product_type'])=='account':return True
    return False

def completion(db,oid,moment=None):
    now=moment or datetime.now(timezone.utc)
    values=[json.loads(r['snapshot_json'] or '{}').get('after_sale_policy',{}) for r in db.execute('SELECT snapshot_json FROM order_items WHERE order_id=?',(oid,))]
    days=max((v.get('days',0) for v in values),default=0)
    db.execute('UPDATE orders SET completed_at=COALESCE(completed_at,?),protection_until=COALESCE(protection_until,?) WHERE id=?',(ops.iso(now),ops.iso(now+timedelta(days=days)) if days else None,oid))

def requirements(item):
    """No passwords, recovery codes or OTP fields. Ask only for delivery identifiers."""
    typ=item['product_type'];game=item['game_id'];method=item['delivery_method']
    if typ not in ('item','currency','service') or method in ('automatic','instant','auto'):return []
    # Manual game delivery requires a recipient; account/code delivery remains protected text.
    fields=[{'key':'player_id','label':'Player ID / character name','required':True}]
    if game in ('pubg-mobile','mobile-legends','genshin-impact','honor-of-kings') or typ=='currency':fields.append({'key':'server','label':'Server / zone','required':True})
    fields += [{'key':'platform','label':'Platform','required':False},{'key':'meeting','label':'Meeting / delivery method','required':False}]
    return fields

def clean_details(value,fields,core,required=True):
    if not isinstance(value,dict) or set(value)-{f['key'] for f in fields}:raise core['HttpError'](400,'Xaridor ma’lumotlari maydonlarini tekshiring.')
    result={}
    for field in fields:
        val=core['clean_text'](value.get(field['key'],''),field['label'],1 if required and field['required'] else 0,120)
        if val:result[field['key']]=val
    return result

def encrypt(core,value,aad):
    try:return core['delivery_crypto'].encrypt_payload(value,aad)
    except core['delivery_crypto'].DeliveryCryptoError as exc:raise core['HttpError'](503,'Maxfiy ma’lumotlarni shifrlash xizmati tayyor emas.') from exc

def decrypt(core,value,aad):
    try:return core['delivery_crypto'].decrypt_payload(value,aad)
    except core['delivery_crypto'].DeliveryCryptoError as exc:raise core['HttpError'](503,'Maxfiy ma’lumotni ochish xizmati tayyor emas.') from exc

def store_details(db,iid,value,core):
    try:cipher=core['delivery_crypto'].encrypt_payload(json.dumps(value,ensure_ascii=False),'buyer:'+iid)
    except core['delivery_crypto'].DeliveryCryptoError as exc:raise core['HttpError'](503,'Xaridor ma’lumotlarini shifrlash xizmati tayyor emas.') from exc
    db.execute('INSERT INTO order_buyer_details(order_item_id,payload) VALUES(?,?) ON CONFLICT(order_item_id) DO UPDATE SET payload=excluded.payload,updated_at=CURRENT_TIMESTAMP',(iid,cipher))

def details_view(db,iid,core):
    row=db.execute('SELECT payload FROM order_buyer_details WHERE order_item_id=?',(iid,)).fetchone()
    if not row:return {}
    return json.loads(decrypt(core,row['payload'],'buyer:'+iid))

def active_cancel(db,oid):return db.execute("SELECT * FROM order_cancellations WHERE order_id=? AND status IN ('pending','escalated')",(oid,)).fetchone()

def guard(db,oid,core):
    if active_cancel(db,oid):raise core['HttpError'](409,'Bekor qilish so‘rovi hal bo‘lguncha buyurtma amallari to‘xtatilgan.')

def escalate_due(db,core,oid=None):
    now=ops.iso(datetime.now(timezone.utc));count=0
    rows=db.execute("SELECT id,order_id FROM order_cancellations WHERE status='pending' AND response_due_at<=?"+(' AND order_id=?' if oid else '')+' LIMIT 1000',(now,oid) if oid else (now,)).fetchall()
    for request in rows:
        db.execute('BEGIN IMMEDIATE')
        try:
            lock_order(db,request['order_id'])
            changed=db.execute("UPDATE order_cancellations SET status='escalated',resolution='48 soat ichida kelishuv bo‘lmadi; moderator ko‘radi',updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending' AND response_due_at<=?",(request['id'],now))
            if changed.rowcount:
                order=db.execute('SELECT * FROM orders WHERE id=?',(request['order_id'],)).fetchone();alert(db,order,core,'Bekor qilish muddati o‘tdi · moderatorga yuborildi');count+=1
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
    return count

def targets(db,order):return {order['buyer_id']}|{r['seller_id'] for r in db.execute('SELECT DISTINCT seller_id FROM order_items WHERE order_id=?',(order['id'],))}
def alert(db,order,core,title,href=None):
    for uid in targets(db,order)|{r['user_id'] for r in db.execute('SELECT user_id FROM admin_accounts LIMIT 30')}:core['notify'](db,uid,'order_case',title,order['reference'],href or '/order/'+order['id'])

def lock_order(db,oid):db.execute('UPDATE orders SET updated_at=updated_at WHERE id=?',(oid,))

def cancel_settle(db,order,core):
    oid=order['id']
    if order['status']=='pending_payment':
        for i in db.execute('SELECT listing_id,quantity FROM order_items WHERE order_id=?',(oid,)):
            db.execute('UPDATE listings SET reserved=CASE WHEN reserved>=? THEN reserved-? ELSE 0 END WHERE id=?',(i['quantity'],i['quantity'],i['listing_id']))
        db.execute("UPDATE payments SET status='cancelled',updated_at=CURRENT_TIMESTAMP WHERE order_id=? AND status='pending'",(oid,));status='cancelled'
    else:
        p=db.execute('SELECT provider,status FROM payments WHERE order_id=?',(oid,)).fetchone()
        if not p or p['provider']!='sandbox' or p['status']!='succeeded' or (core['MODE']!='development' and not core['internal_testing_enabled']()):raise core['HttpError'](503,'Qaytarim adapteri ulanmagan. So‘rov saqlanadi; haqiqiy pul o‘zgarmaydi.')
        core['refund_sandbox_escrow'](db,oid,order['buyer_id']);db.execute("UPDATE payments SET status='sandbox_refunded',updated_at=CURRENT_TIMESTAMP WHERE order_id=?",(oid,));status='refunded'
        # Restock only completely undelivered lines; an item already sent may be irrecoverable.
        for i in db.execute('SELECT listing_id,quantity,delivered_quantity FROM order_items WHERE order_id=?',(oid,)):
            if i['delivered_quantity']==0:db.execute("UPDATE listings SET stock=stock+?,status=CASE WHEN status='sold_out' THEN 'published' ELSE status END WHERE id=?",(i['quantity'],i['listing_id']))
    db.execute('UPDATE orders SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(status,oid));core['event'](db,oid,None,order['status'],status,'Bekor qilish kelishuvi · sandbox bo‘lsa haqiqiy pul o‘zgarmaydi')
    return status

def artifact_view(db,order,uid,core):
    admin=core['is_admin'](db,uid);buyer=uid==order['buyer_id'];out=[]
    for row in db.execute('SELECT a.*,u.display_name owner_name FROM order_artifacts a JOIN users u ON u.id=a.owner_id WHERE a.order_id=? ORDER BY a.created_at,a.id',(order['id'],)):
        a=dict(row)
        # A seller sees only their own line's evidence (or their own case evidence).
        if not admin and not buyer and a['owner_id']!=uid and (not a['order_item_id'] or not db.execute('SELECT 1 FROM order_items WHERE id=? AND seller_id=?',(a['order_item_id'],uid)).fetchone()):continue
        key=a.pop('object_path')
        if key:
            try:a['image_url']=core['storage_r2'].evidence_url(key)
            except Exception:a['image_unavailable']=True
        out.append(a)
    return out

def appeal_decisions(db,oid):
    rows=[]
    for r in db.execute("SELECT id,resolved_at FROM reports WHERE order_id=? AND reason='order_dispute' AND status='resolved' AND resolved_at IS NOT NULL",(oid,)):
        rows.append({'id':r['id'],'kind':'dispute','decided_at':r['resolved_at']})
    for r in db.execute("SELECT id,updated_at FROM order_cases WHERE order_id=? AND kind='after_sale' AND status='resolved'",(oid,)):
        rows.append({'id':'case:'+r['id'],'kind':'after_sale','decided_at':r['updated_at']})
    for r in db.execute("SELECT reviewed_at FROM account_reviews WHERE order_id=? AND status IN ('approved','refunded') AND reviewed_at IS NOT NULL",(oid,)):
        rows.append({'id':'account:'+oid,'kind':'account_review','decided_at':r['reviewed_at']})
    for row in rows:row['deadline_at']=ops.iso(ops.utc(row['decided_at'])+timedelta(days=7))
    return sorted(rows,key=lambda r:ops.utc(r['decided_at']),reverse=True)

def workflow_view(db,order,uid,core):
    admin=core['is_admin'](db,uid);buyer=uid==order['buyer_id'];lines=[]
    for r in db.execute('SELECT i.*,l.product_type,l.game_id FROM order_items i JOIN listings l ON l.id=i.listing_id WHERE i.order_id=?',(order['id'],)):
        if not (admin or buyer or r['seller_id']==uid):continue
        item=dict(r);snap=json.loads(item['snapshot_json'] or '{}');typ=snap.get('product_type',item['product_type']);fields=snap.get('buyer_fields',requirements(item));item['product_type']=typ
        batches=[]
        for b in db.execute('SELECT * FROM delivery_batches WHERE order_item_id=? ORDER BY delivered_total,created_at,id',(item['id'],)):
            val=dict(b);val.pop('request_key');cipher=val.pop('payload')
            val['body']=decrypt(core,cipher,'batch:'+val['id']) if buyer or admin or uid==item['seller_id'] else ''
            batches.append(val)
        lines.append({'id':item['id'],'title':item['title'],'seller_id':item['seller_id'],'quantity':item['quantity'],'delivered_quantity':item['delivered_quantity'],'buyer_fields':fields,'buyer_details':details_view(db,item['id'],core),'batches':batches,'policy':snap.get('after_sale_policy',{'days':0,'appeal_days':7,'legacy':True})})
    cancellations=[]
    for r in db.execute('SELECT * FROM order_cancellations WHERE order_id=? ORDER BY created_at DESC,id DESC',(order['id'],)):
        c=dict(r);c['replies']=[dict(x) for x in db.execute('SELECT r.*,u.display_name seller_name FROM cancellation_replies r JOIN users u ON u.id=r.seller_id WHERE cancellation_id=?',(c['id'],))];cancellations.append(c)
    cases=[dict(r) for r in db.execute('SELECT * FROM order_cases WHERE order_id=? ORDER BY created_at DESC,id DESC',(order['id'],))]
    reports=[dict(r) for r in db.execute("SELECT id,resolution,resolved_at,status FROM reports WHERE order_id=? AND reason='order_dispute' ORDER BY created_at DESC,id DESC",(order['id'],))]
    return {'order':{'id':order['id'],'reference':order['reference'],'status':order['status'],'buyer':buyer,'admin':admin,'completed_at':order['completed_at'],'protection_until':order['protection_until']},'items':lines,'cancellations':cancellations,'cases':cases,'reports':reports,'artifacts':artifact_view(db,order,uid,core),'is_paused':bool(active_cancel(db,order['id'])),'appeal_decisions':appeal_decisions(db,order['id'])}

def normalize_filters(value,core):
    if not isinstance(value,dict) or set(value)-FILTERS:raise core['HttpError'](400,'Qidiruv filtrlarini tekshiring.')
    cleaned={}
    for key,val in value.items():
        if not isinstance(val,str) or len(val)>120:raise core['HttpError'](400,'Filtr qiymati noto‘g‘ri.')
        if val.strip():cleaned[key]=val.strip()
    if not cleaned:raise core['HttpError'](400,'Kamida bitta qidiruv yoki filtr tanlang.')
    if cleaned.get('min') and cleaned.get('max'):
        try:
            if int(cleaned['min'])>int(cleaned['max']):raise ValueError()
        except ValueError:raise core['HttpError'](400,'Narx oralig‘i noto‘g‘ri.')
    return cleaned

def search_alert(db,lid,core):
    """Run catalogue's own predicates, including launch gates, against this listing only."""
    handler=core['Handler'].__new__(core['Handler'])
    for search in db.execute('SELECT * FROM saved_searches WHERE enabled=1').fetchall():
        f=json.loads(search['filters_json']);qs={k:[v] for k,v in f.items()};qs['_match_listing']=[lid]
        r=handler.route(db,{'uid':search['user_id'],'user':None},'GET','/api/listings',qs,{})
        if not r['items']:continue
        changed=db.execute('INSERT INTO saved_search_matches(search_id,listing_id) VALUES(?,?) ON CONFLICT(search_id,listing_id) DO NOTHING',(search['id'],lid))
        if changed.rowcount==1:core['notify'](db,search['user_id'],'saved_search','Qidiruvingizga mos yangi e’lon',search['name'],'/listing/'+lid)


def route(handler,db,ctx,method,path,qs,data,raw,core):
    uid=ctx['uid'];err=core['HttpError'];now=datetime.now(timezone.utc);text=core['clean_text'];require=core['require_user'];verify=core['require_verified']
    if path=='/api/saved-searches' and method in ('GET','POST'):
        require(ctx)
        if method=='GET':return [{**dict(r),'filters':json.loads(r['filters_json']),'href':'/browse?'+urlencode(json.loads(r['filters_json']))} for r in db.execute('SELECT * FROM saved_searches WHERE user_id=? ORDER BY created_at DESC,id',(uid,))]
        verify(ctx);core['check_rate'](db,'saved_search',uid,30,3600);filters=normalize_filters(data.get('filters'),core);name=text(data.get('name'),'Qidiruv nomi',2,80)
        # The catalogue validates numeric/range fields before anything is saved.
        result=handler.route(db,ctx,'GET','/api/listings',{k:[v] for k,v in filters.items()},{})
        fingerprint=hashlib.sha256(json.dumps(filters,sort_keys=True).encode()).hexdigest();sid=core['ident']()
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('SELECT COUNT(*) n FROM saved_searches WHERE user_id=?',(uid,)).fetchone()['n']>=30:raise err(400,'30 tagacha qidiruv saqlash mumkin.')
            db.execute('INSERT INTO saved_searches(id,user_id,name,filters_json,fingerprint) VALUES(?,?,?,?,?) ON CONFLICT(user_id,fingerprint) DO UPDATE SET name=excluded.name,enabled=1',(sid,uid,name,json.dumps(filters),fingerprint))
            sid=db.execute('SELECT id FROM saved_searches WHERE user_id=? AND fingerprint=?',(uid,fingerprint)).fetchone()['id']
            # Existing results are not new-listing notifications. All existing published IDs are seeded.
            db.execute('INSERT INTO saved_search_matches(search_id,listing_id) SELECT ?,id FROM listings WHERE status=\'published\' ON CONFLICT(search_id,listing_id) DO NOTHING',(sid,))
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return 201,{'id':sid,'current_matches':result['total_count']}
    match=re.fullmatch(r'/api/saved-searches/([^/]+)',path)
    if match and method in ('DELETE','PATCH'):
        require(ctx);sid=match.group(1)
        if not db.execute('SELECT 1 FROM saved_searches WHERE id=? AND user_id=?',(sid,uid)).fetchone():raise err(404,'Qidiruv topilmadi.')
        if method=='DELETE':db.execute('DELETE FROM saved_searches WHERE id=? AND user_id=?',(sid,uid))
        else:
            if type(data.get('enabled')) is not bool:raise err(400,'Bildirishnoma sozlamasi noto‘g‘ri.')
            db.execute('UPDATE saved_searches SET enabled=? WHERE id=? AND user_id=?',(int(data['enabled']),sid,uid))
        return {'ok':True}
    if path=='/api/order-cases' and method=='GET':
        core['require_admin'](ctx)
        return {'cases':[dict(r) for r in db.execute("SELECT c.*,o.reference FROM order_cases c JOIN orders o ON o.id=c.order_id ORDER BY CASE WHEN c.status IN ('open','reviewing','followup') THEN 0 ELSE 1 END,c.updated_at DESC LIMIT 200")],'cancellations':[dict(r) for r in db.execute("SELECT c.*,o.reference FROM order_cancellations c JOIN orders o ON o.id=c.order_id WHERE c.status IN ('pending','escalated') ORDER BY c.created_at LIMIT 200")]}
    match=re.fullmatch(r'/api/orders/([^/]+)/(workflow|buyer-details|deliver|evidence|cancellation|after-sale|appeal)',path)
    if not match:return UNHANDLED
    require(ctx);oid,action=match.groups();order=ops.order_member(db,oid,uid,core);admin=core['is_admin'](db,uid);buyer=uid==order['buyer_id'];sellers={r['seller_id'] for r in db.execute('SELECT seller_id FROM order_items WHERE order_id=?',(oid,))}
    if action=='workflow' and method=='GET':
        escalate_due(db,core,oid)
        return workflow_view(db,order,uid,core)
    if method!='POST':return UNHANDLED
    verify(ctx);core['check_rate'](db,'trade_'+action,uid,60,3600)
    if action=='buyer-details':
        if not buyer:raise err(403,'Faqat xaridor yetkazish ma’lumotlarini o‘zgartiradi.')
        iid=text(data.get('item_id'),'Mahsulot',1,100);item=db.execute('SELECT i.*,l.product_type,l.game_id FROM order_items i JOIN listings l ON l.id=i.listing_id WHERE i.id=? AND i.order_id=?',(iid,oid)).fetchone()
        if not item:raise err(404,'Mahsulot topilmadi.')
        fields=json.loads(item['snapshot_json']).get('buyer_fields',requirements(item));value=clean_details(data.get('details'),fields,core)
        db.execute('BEGIN IMMEDIATE')
        try:
            lock_order(db,oid);current=db.execute('SELECT status FROM orders WHERE id=?',(oid,)).fetchone()['status']
            if current not in ('pending_payment','paid','awaiting_delivery') or db.execute('SELECT delivered_quantity FROM order_items WHERE id=?',(iid,)).fetchone()['delivered_quantity']>0:raise err(409,'Yetkazish boshlangan; ma’lumotni o‘zgartirib bo‘lmaydi.')
            guard(db,oid,core);store_details(db,iid,value,core);core['audit'](db,uid,'buyer_details_updated','order_item',iid);db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'ok':True}
    if action=='deliver':
        iid=text(data.get('item_id'),'Mahsulot',1,100);body=text(data.get('delivery'),'Yetkazish dalili / natija',2,5000);key=text(data.get('request_key') or core['ident'](),'So‘rov kaliti',1,100)
        db.execute('BEGIN IMMEDIATE')
        try:
            lock_order(db,oid);order=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone();guard(db,oid,core)
            item=db.execute('SELECT i.*,l.product_type,l.game_id FROM order_items i JOIN listings l ON l.id=i.listing_id WHERE i.id=? AND i.order_id=? AND i.seller_id=?',(iid,oid,uid)).fetchone()
            if not item:raise err(403,'Bu mahsulotni yetkazish huquqingiz yo‘q.')
            prior=db.execute('SELECT id,quantity FROM delivery_batches WHERE order_item_id=? AND request_key=?',(iid,key)).fetchone()
            if prior:
                db.execute('COMMIT');return {'id':prior['id'],'idempotent':True,'status':order['status']}
            if order['status'] not in ('paid','awaiting_delivery'):raise err(409,'Buyurtma yetkazishga tayyor emas.')
            remaining=item['quantity']-item['delivered_quantity'];quantity=data.get('quantity',remaining)
            if type(quantity) is not int or not 1<=quantity<=remaining:raise err(400,'Miqdor qolgan mahsulotlar sonidan oshmasin.')
            fields=json.loads(item['snapshot_json']).get('buyer_fields',[])
            if fields:clean_details(details_view(db,iid,core),fields,core)
            bid=core['ident']();cipher=encrypt(core,body,'batch:'+bid)
            db.execute('INSERT INTO delivery_batches(id,order_item_id,seller_id,quantity,delivered_total,payload,request_key) VALUES(?,?,?,?,?,?,?)',(bid,iid,uid,quantity,item['delivered_quantity']+quantity,cipher,key));db.execute('UPDATE order_items SET delivered_quantity=delivered_quantity+? WHERE id=?',(quantity,iid))
            # Keep legacy protected delivery available, but only after the whole line is delivered.
            if quantity==remaining:
                encrypted=encrypt(core,body,iid)
                db.execute('INSERT INTO deliveries(id,order_item_id,seller_id,protected_payload) VALUES(?,?,?,?) ON CONFLICT(order_item_id) DO UPDATE SET protected_payload=excluded.protected_payload,submitted_at=CURRENT_TIMESTAMP',(core['ident'](),iid,uid,encrypted))
            missing=db.execute('SELECT COUNT(*) n FROM order_items WHERE order_id=? AND delivered_quantity<quantity',(oid,)).fetchone()['n'];state='awaiting_delivery' if missing else 'delivered'
            db.execute('UPDATE orders SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(state,oid));core['event'](db,oid,uid,order['status'],state,f"Yetkazildi: {item['delivered_quantity']+quantity}/{item['quantity']} · {item['title']}");core['notify'](db,order['buyer_id'],'delivery','Yetkazish yangilandi',f"{item['title']}: {item['delivered_quantity']+quantity}/{item['quantity']}",'/order/'+oid);db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        core['email_order_update'](db,order['buyer_id'],order['reference'],state,'Yetkazish holati yangilandi. Tafsilotlarni buyurtma sahifasida tekshiring.')
        return {'id':bid,'status':state,'delivered_quantity':item['delivered_quantity']+quantity}
    if action=='evidence':
        iid=data.get('item_id') or qs.get('item_id',[''])[0] or None;case_id=data.get('case_id') or qs.get('case_id',[''])[0] or None
        if iid and not db.execute('SELECT 1 FROM order_items WHERE id=? AND order_id=?'+('' if buyer or admin else ' AND seller_id=?'),(iid,oid) if buyer or admin else (iid,oid,uid)).fetchone():raise err(404,'Mahsulot topilmadi.')
        if case_id and not db.execute("SELECT 1 FROM order_cases WHERE id=? AND order_id=? AND status IN ('open','reviewing','followup')",(case_id,oid)).fetchone():raise err(409,'Murojaat yopilgan.')
        if order['status'] in ('cancelled','refunded') and not case_id:raise err(409,'Yopilgan buyurtmaga dalil qo‘shib bo‘lmaydi.')
        if not buyer and not admin and not iid and not case_id:raise err(400,'Dalil uchun o‘zingizning mahsulotingizni tanlang.')
        key=None
        if raw and handler.headers.get('Content-Type','').startswith('image/'):
            core['require_private_evidence_bucket']();image=core['normalize_account_evidence'](raw,handler.headers.get('Content-Type',''));key=secrets.token_hex(12)+'/'+secrets.token_hex(24)+'.webp'
            try:core['storage_r2'].put_evidence(key,image)
            except Exception as exc:raise err(503,'Dalil rasmi saqlanmadi; qayta urinib ko‘ring.') from exc
            body='Yetkazish / murojaat dalili'
        else:body=text(data.get('body'),'Dalil yoki bajarilgan natija',5,5000)
        aid=core['ident']()
        db.execute('BEGIN IMMEDIATE')
        try:
            lock_order(db,oid)
            if case_id:db.execute('UPDATE order_cases SET updated_at=updated_at WHERE id=?',(case_id,))
            if case_id and not db.execute("SELECT 1 FROM order_cases WHERE id=? AND order_id=? AND status IN ('open','reviewing','followup')",(case_id,oid)).fetchone():raise err(409,'Murojaat yopilgan.')
            db.execute('INSERT INTO order_artifacts(id,order_id,order_item_id,case_id,owner_id,body,object_path) VALUES(?,?,?,?,?,?,?)',(aid,oid,iid,case_id,uid,body,key));alert(db,order,core,'Buyurtmaga dalil qo‘shildi');db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            if key:core['storage_r2'].delete_evidence(key)
            raise
        return 201,{'id':aid}
    if action=='cancellation':
        choice=data.get('action','request');db.execute('BEGIN IMMEDIATE')
        try:
            lock_order(db,oid);order=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone();request=active_cancel(db,oid)
            if choice=='request':
                if not buyer or order['status'] not in ('pending_payment','paid','awaiting_delivery','delivered'):raise err(409,'Bu buyurtma uchun bekor qilish so‘rovi ochib bo‘lmaydi.')
                if request:raise err(409,'Ochiq bekor qilish so‘rovi mavjud.')
                reason=data.get('reason');details=text(data.get('details'),'Bekor qilish izohi',5,2000)
                if reason not in REASONS:raise err(400,'Bekor qilish sababini tanlang.')
                cid=core['ident']();db.execute('INSERT INTO order_cancellations(id,order_id,requester_id,reason,details,response_due_at) VALUES(?,?,?,?,?,?)',(cid,oid,uid,reason,details,ops.iso(now+timedelta(hours=48))))
                if order['status']=='pending_payment':cancel_settle(db,order,core);db.execute("UPDATE order_cancellations SET status='accepted',resolution='To‘lovdan oldin bekor qilindi' WHERE id=?",(cid,))
            else:
                if not request:raise err(409,'Ochiq bekor qilish so‘rovi topilmadi.')
                cid=request['id'];note=text(data.get('note',''),'Javob izohi',0 if choice=='withdraw' else 5,2000)
                if choice=='withdraw' and buyer:db.execute("UPDATE order_cancellations SET status='withdrawn',updated_at=CURRENT_TIMESTAMP WHERE id=?",(cid,))
                elif choice in ('accept','reject') and uid in sellers and not buyer and request['status']=='pending':
                    if db.execute('SELECT 1 FROM cancellation_replies WHERE cancellation_id=? AND seller_id=?',(cid,uid)).fetchone():raise err(409,'Javob allaqachon berilgan.')
                    db.execute('INSERT INTO cancellation_replies(cancellation_id,seller_id,decision,note) VALUES(?,?,?,?)',(cid,uid,choice,note))
                    if choice=='reject':db.execute("UPDATE order_cancellations SET status='escalated',resolution='Sotuvchi rozi emas; moderator javobi kutilmoqda',updated_at=CURRENT_TIMESTAMP WHERE id=?",(cid,))
                    elif db.execute("SELECT COUNT(*) n FROM cancellation_replies WHERE cancellation_id=? AND decision='accept'",(cid,)).fetchone()['n']==len(sellers):
                        if db.execute('SELECT 1 FROM order_items WHERE order_id=? AND delivered_quantity>0',(oid,)).fetchone():db.execute("UPDATE order_cancellations SET status='escalated',resolution='Qisman yetkazish bor; moderator tekshiradi',updated_at=CURRENT_TIMESTAMP WHERE id=?",(cid,))
                        else:cancel_settle(db,order,core);db.execute("UPDATE order_cancellations SET status='accepted',resolution=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(note,cid))
                elif choice=='escalate' and (buyer or uid in sellers):
                    if ops.utc(request['response_due_at'])>now and not db.execute('SELECT 1 FROM cancellation_replies WHERE cancellation_id=?',(cid,)).fetchone():raise err(409,'Javob muddati tugamaguncha sotuvchi javobini kuting.')
                    db.execute("UPDATE order_cancellations SET status='escalated',resolution=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(note,cid))
                elif choice in ('approve','decline') and admin:
                    if uid in sellers or buyer:raise err(403,'O‘zingiz qatnashgan buyurtmani moderatsiya qila olmaysiz.')
                    if choice=='approve':cancel_settle(db,order,core)
                    db.execute('UPDATE order_cancellations SET status=?,resolution=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',('accepted' if choice=='approve' else 'rejected',note,cid))
                else:raise err(403,'Bu amal uchun ruxsat yo‘q.')
            core['audit'](db,uid,'cancellation_'+choice,'order',oid);alert(db,order,core,'Bekor qilish so‘rovi yangilandi');db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'id':cid,'ok':True}
    if action in ('after-sale','appeal'):
        kind='after_sale' if action=='after-sale' else 'appeal';reason=data.get('reason');details=text(data.get('details'),'Sabab va yangi dalillar',20,5000)
        if reason not in CASE_REASONS:raise err(400,'Murojaat sababini tanlang.')
        db.execute('BEGIN IMMEDIATE')
        try:
            lock_order(db,oid);order=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone();source='completion'
            if kind=='after_sale':
                if not buyer or order['status']!='completed' or not order['protection_until'] or ops.utc(order['protection_until'])<now:raise err(409,'Sotuvdan keyingi murojaat muddati tugagan yoki buyurtma yakunlanmagan.')
                eligible=False
                for i in db.execute('SELECT snapshot_json FROM order_items WHERE order_id=?',(oid,)):
                    p=json.loads(i['snapshot_json']).get('after_sale_policy',{})
                    if reason in p.get('issues',[]) and order['completed_at'] and ops.utc(order['completed_at'])+timedelta(days=p.get('days',0))>=now:eligible=True
                if not eligible:raise err(400,'Bu muammo saqlangan murojaat qoidalariga kirmaydi.')
            else:
                if not (buyer or uid in sellers):raise err(403,'Faqat buyurtma tomonlari apellyatsiya yuboradi.')
                decisions=appeal_decisions(db,oid);requested=data.get('source_id')
                if requested is not None and not isinstance(requested,str):raise err(400,'Qaror ID noto‘g‘ri.')
                decision=next((d for d in decisions if d['id']==requested),None) if requested else (decisions[0] if decisions else None)
                if not decision or ops.utc(decision['deadline_at'])<now:raise err(409,'Apellyatsiya muddati tugagan yoki yakuniy moderator qarori yo‘q.')
                if reason!='new_evidence':raise err(400,'Apellyatsiya uchun yangi dalil ko‘rsating.')
                source=decision['id']
            if db.execute('SELECT 1 FROM order_cases WHERE order_id=? AND requester_id=? AND kind=? AND source_id=?',(oid,uid,kind,source)).fetchone():raise err(409,'Bu masala bo‘yicha murojaat allaqachon mavjud.')
            cid=core['ident']();db.execute('INSERT INTO order_cases(id,order_id,requester_id,kind,source_id,reason,details,response_due_at) VALUES(?,?,?,?,?,?,?,?)',(cid,oid,uid,kind,source,reason,details,ops.iso(now+timedelta(hours=48))))
            alert(db,order,core,'Yangi apellyatsiya' if kind=='appeal' else 'Sotuvdan keyingi murojaat','/order-case/'+cid);core['audit'](db,uid,'case_created','order_case',cid);db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return 201,{'id':cid}
    return UNHANDLED


def case_route(db,ctx,method,path,data,core):
    match=re.fullmatch(r'/api/order-cases/([^/]+)',path)
    if not match or method not in ('GET','POST'):return UNHANDLED
    core['require_user'](ctx);uid=ctx['uid'];cid=match.group(1);case=db.execute('SELECT * FROM order_cases WHERE id=?',(cid,)).fetchone()
    if not case:raise core['HttpError'](404,'Murojaat topilmadi.')
    order=ops.order_member(db,case['order_id'],uid,core);admin=core['is_admin'](db,uid)
    if method=='GET':return {'case':dict(case),'order':{'id':order['id'],'reference':order['reference']},'can_manage':admin and uid not in targets(db,order),'entries':[dict(r) for r in db.execute('SELECT e.*,u.display_name sender_name FROM order_case_entries e JOIN users u ON u.id=e.sender_id WHERE case_id=? ORDER BY e.created_at,e.id',(cid,))],'artifacts':[a for a in artifact_view(db,order,uid,core) if a['case_id']==cid]}
    core['require_verified'](ctx);core['check_rate'](db,'case_reply',uid,40,3600);body=core['clean_text'](data.get('body'),'Izoh / qaror',5,5000);choice=data.get('action','reply')
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('UPDATE order_cases SET updated_at=updated_at WHERE id=?',(cid,));case=db.execute('SELECT * FROM order_cases WHERE id=?',(cid,)).fetchone()
        if case['status'] not in ('open','reviewing','followup'):raise core['HttpError'](409,'Murojaat yakunlangan.')
        if choice in ('request_info','uphold','revise','close_followup'):
            if not admin or uid in targets(db,order):raise core['HttpError'](403,'Mustaqil moderator kerak.')
            if choice=='close_followup' and case['status']!='followup':raise core['HttpError'](409,'Avval keyingi chora uchun qarorni qayta ko‘rib chiqing.')
            state='reviewing' if choice=='request_info' else 'followup' if choice=='revise' else 'resolved';remedy='' if choice=='request_info' else 'decision_upheld' if choice=='uphold' else 'followup_completed' if choice=='close_followup' else 'manual_followup_required'
            db.execute('UPDATE order_cases SET status=?,resolution=?,remedy=?,reviewed_by=?,response_due_at=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(state,body,remedy,uid,ops.iso(datetime.now(timezone.utc)+timedelta(hours=48)),cid));core['audit'](db,uid,'case_'+choice,'order_case',cid,{'real_money_moved':False})
        elif choice!='reply':raise core['HttpError'](400,'Amal noto‘g‘ri.')
        db.execute('INSERT INTO order_case_entries(id,case_id,sender_id,body) VALUES(?,?,?,?)',(core['ident'](),cid,uid,body));alert(db,order,core,'Murojaat yangilandi','/order-case/'+cid);db.execute('COMMIT')
    except Exception:db.execute('ROLLBACK');raise
    return {'ok':True,'real_money_moved':False}

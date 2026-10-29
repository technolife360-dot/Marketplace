"""Launch preparation on existing private configuration/preferences tables.

No provider is enabled here and no credentials or private delivery payloads are
included in public configuration or personal exports.
"""
import json
import os
import re
import account_contacts
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UNHANDLED = object()
CONFIG_KEY = 'launch_public_profile'
TEST_SQL = "NOT EXISTS(SELECT 1 FROM platform_config audience WHERE audience.key='listing_audience:'||l.id AND audience.value='test') AND NOT (l.title='ads sdasde ded' AND l.seller_id IN (SELECT user_id FROM seller_profiles WHERE shop_name='SentryLoot Test Seller'))"
PACKAGE_ART = {str(n)+'-uc':'/static/assets/topup-uc-'+str(n)+'.png' for n in (60,325,660,1800,3850,8100)}
PACKAGE_ART.update({'elite-pass-lv1-100':'/static/assets/topup-elite-pass.png','elite-pass-plus-lv1-100':'/static/assets/topup-elite-pass.png','weekly-mythic-emblem-value-pack':'/static/assets/topup-weekly-mythic.png','weekly-deal-pack-2':'/static/assets/topup-weekly-deal-2.png','weekly-deal-pack-1':'/static/assets/topup-weekly-deal-1.png'})
CONTENTS = {'weekly-deal-pack-2':[['Premium',2],['Classic',4],['Supply',6],['UC',60]],'weekly-deal-pack-1':[['Bonus',1],['Classic',2],['Supply',2],['UC',30]],'weekly-mythic-emblem-value-pack':[['Mythic Emblem',1]]}

def config(db,key,default=None):
    row=db.execute('SELECT value FROM platform_config WHERE key=?',(key,)).fetchone()
    if not row:return default
    try:return json.loads(row['value'])
    except (ValueError,TypeError):return default

def put_config(db,key,value):
    db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',(key,json.dumps(value,ensure_ascii=False)))

def capabilities(db,uid):
    return config(db,'staff_capabilities:'+str(uid),[]) if uid else []

def staff_allowed(db,uid,capability):
    return capability in capabilities(db,uid)

def route_capability(path):
    if path=='/api/admin/blog' or re.fullmatch(r'/api/admin/blog/[A-Za-z0-9_-]+',path):return 'content'
    if path=='/api/catalog/readiness' or path=='/api/admin/listings' or re.fullmatch(r'/api/admin/listings/[^/]+',path):return 'moderation'
    return None

def test_listing(db,lid):
    return bool(db.execute("SELECT 1 FROM listings l WHERE l.id=? AND NOT ("+TEST_SQL+")",(lid,)).fetchone())

def public_profile(db):
    draft=config(db,CONFIG_KEY,{})
    return draft if draft.get('published') else {'published':False}

def validate_profile(data,core):
    fields={'business_name':160,'public_email':254,'public_address':500,'support_owner':100,'support_hours':300,'timezone':100,'response_target':160,'protection_scope':2000,'protection_exclusions':2000}
    if set(data)-set(fields)-{'published'}:raise core['HttpError'](400,'Unknown profile field.')
    if any(k in data and not isinstance(data[k],str) for k in fields) or ('published' in data and type(data['published']) is not bool):raise core['HttpError'](400,'Check profile values.')
    result={k:data.get(k,'').strip() for k in fields}
    if any(len(result[k])>limit for k,limit in fields.items()):raise core['HttpError'](400,'Profile text is too long.')
    if result['timezone']:
        try:ZoneInfo(result['timezone'])
        except (ZoneInfoNotFoundError,ValueError):raise core['HttpError'](400,'Choose a valid timezone, for example Asia/Tashkent.')
    if result['public_email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',result['public_email']):raise core['HttpError'](400,'Check the public email address.')
    result['published']=data.get('published') is True
    if result['published'] and any(not result[k] for k in fields):raise core['HttpError'](400,'Complete and confirm the real business and support details before publishing.')
    return result

def launch_summary(db,core):
    """Admin-only preparation facts. Presence of keys is never an API verification."""
    profile=config(db,CONFIG_KEY,{})
    required=('business_name','public_email','public_address','support_owner','support_hours',
              'timezone','response_target','protection_scope','protection_exclusions')
    missing=[key for key in required if not str(profile.get(key,'')).strip()]
    provider=os.environ.get('PAYMENT_PROVIDER','disabled').strip().lower()
    test_keys=all(os.environ.get(key,'').strip() for key in
                  ('STRIPE_TEST_SECRET_KEY','STRIPE_TEST_ACCOUNT_ID','STRIPE_TEST_WEBHOOK_SECRET','PUBLIC_BASE_URL'))
    payment_state=('test_configuration_present' if test_keys else 'needs_test_configuration') if provider=='stripe_test' else (
        'local_sandbox' if core['MODE']=='development' and provider in ('disabled','sandbox') else 'closed')
    topup=db.execute("SELECT COUNT(*) total,COALESCE(SUM(CASE WHEN price_minor<=0 THEN 1 ELSE 0 END),0) unpriced,COALESCE(SUM(CASE WHEN supplier_enabled=0 OR supplier_type_id='' THEN 1 ELSE 0 END),0) unmapped FROM topup_packages WHERE enabled=1").fetchone()
    return {
        # No live payment/fulfillment adapter exists in this release.
        'live_sales':False,
        'payments':{'state':payment_state,'verification':'not_checked','test_only':True},
        'business':{'state':'published' if profile.get('published') and not missing else 'needs_details',
                    'missing':missing,'published':bool(profile.get('published') and not missing)},
        'topup':{'state':'needs_supplier','total':topup['total'],'unpriced':topup['unpriced'],
                 'unmapped':topup['unmapped'],'credentials_present':bool(os.environ.get('SEAGM_UID','').strip() and os.environ.get('SEAGM_SECRET_KEY','').strip()),
                 'delivery_verified':False},
    }

def package_metadata(row,db=None):
    slug=row['url_slug']
    base={'image_url':PACKAGE_ART.get(slug,'') if row['game_slug']=='pubg-mobile' else '', 'contents':CONTENTS.get(slug,[]) if row['game_slug']=='pubg-mobile' else []}
    if db:base.update(config(db,'topup_presentation:'+row['id'],{}))
    return base

def save_preferences(db,uid,transform,core):
    # Lock a base-schema user row before reading: concurrent tabs cannot lose
    # notification preferences or another package saved at the same time.
    db.execute('BEGIN IMMEDIATE')
    try:
        db.execute('UPDATE users SET display_name=display_name WHERE id=?',(uid,))
        row=db.execute('SELECT settings_json FROM experience_preferences WHERE user_id=?',(uid,)).fetchone()
        value=json.loads(row['settings_json']) if row else {}
        transform(value)
        db.execute('INSERT INTO experience_preferences(user_id,settings_json) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET settings_json=excluded.settings_json',(uid,json.dumps(value)))
        db.execute('COMMIT')
        return value
    except Exception:
        db.execute('ROLLBACK');raise

def personal_export(db,uid):
    # Explicit field lists: never SELECT * from sessions, users or deliveries.
    profile=dict(db.execute('SELECT id,display_name,email,country,language,currency,created_at FROM users WHERE id=?',(uid,)).fetchone())
    profile['phone']=account_contacts.read(db,uid)
    profile['phone_verified']=account_contacts.verified(db,uid)
    queries={
        'orders':('SELECT id,reference,status,currency,total_minor,created_at FROM orders WHERE buyer_id=?',(uid,)),
        'reviews':('SELECT rating,body,created_at,hidden FROM reviews WHERE reviewer_id=?',(uid,)),
        'topup_reviews':('SELECT rating,body,created_at,hidden FROM topup_reviews WHERE reviewer_id=?',(uid,)),
        'review_helpful_votes':('SELECT kind,review_id,created_at FROM purchase_review_helpful WHERE user_id=?',(uid,)),
        'review_reports':('SELECT kind,review_id,reason,status,created_at FROM purchase_review_reports WHERE reporter_id=?',(uid,)),
        'support_requests':('SELECT id,subject,category,status,created_at FROM support_tickets WHERE requester_id=?',(uid,)),
        'saved_listings':('SELECT listing_id FROM favorites WHERE user_id=?',(uid,)),
        'collections':('SELECT kind,listing_id,updated_at FROM account_collections WHERE user_id=?',(uid,)),
        'own_messages':('SELECT id,conversation_id,body,created_at FROM messages WHERE sender_id=?',(uid,)),
    }
    result={'format_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'profile':profile}
    for key,(sql,args) in queries.items():result[key]=[dict(r) for r in db.execute(sql,args)]
    result['notice']='Includes your own messages; does not include attachments, credentials, private deliveries or other users’ profile data.'
    return json.loads(json.dumps(result,default=str))

def unit_price(db,lid,base,quantity):
    price=base
    for tier in config(db,'listing_tiers:'+lid,[]):
        if quantity>=tier['quantity']:price=min(base,tier['unit_price_minor'])
    return price

def reputation(db,sid):
    # Sandbox orders never create a public reputation tier.
    row=db.execute("SELECT COUNT(DISTINCT o.id) n FROM orders o JOIN order_items i ON i.order_id=o.id WHERE i.seller_id=? AND o.status='completed' AND o.payment_mode NOT IN ('sandbox','disabled','stripe_test')",(sid,)).fetchone()
    reviews=db.execute("SELECT COUNT(*) n,AVG(r.rating) rating FROM visible_reviews r JOIN order_items i ON i.id=r.order_item_id JOIN orders o ON o.id=i.order_id WHERE r.seller_id=? AND o.payment_mode NOT IN ('sandbox','disabled','stripe_test')",(sid,)).fetchone()
    sales=row['n'];rating=float(reviews['rating']) if reviews['rating'] is not None else None
    tier='established' if sales>=100 and reviews['n']>=20 and rating>=4.7 else 'experienced' if sales>=20 and reviews['n']>=5 and rating>=4.5 else 'new'
    return {'tier':tier,'real_completed_orders':sales,'verified_review_count':reviews['n'],'rating':rating,'criteria':{'experienced':{'orders':20,'reviews':5,'rating':4.5},'established':{'orders':100,'reviews':20,'rating':4.7}},'sample':'completed non-sandbox orders only'}

def milestones(db,item):
    snapshot=json.loads(item['snapshot_json'] or '{}')
    plan=snapshot.get('service_plan',[])
    saved=config(db,'service_progress:'+item['id'],{})
    return [{'index':i,'title':title,'status':saved.get(str(i),{}).get('status','pending'),'note':saved.get(str(i),{}).get('note','')} for i,title in enumerate(plan)]

def milestones_complete(db,oid):
    return all(step['status']=='accepted' for item in db.execute('SELECT id,snapshot_json FROM order_items WHERE order_id=?',(oid,)) for step in milestones(db,item))

def route(handler,db,ctx,method,path,qs,data,raw,core):
    uid=ctx['uid'];error=core['HttpError']
    match=re.fullmatch(r'/api/disputes/([A-Za-z0-9_-]{1,100})/videos',path)
    if match and method=='POST':
        core['require_verified'](ctx);oid=match.group(1)
        core['marketplace_operations'].order_member(db,oid,uid,core)
        if not db.execute("SELECT 1 FROM orders WHERE id=? AND status='disputed'",(oid,)).fetchone():raise error(409,'This dispute is closed.')
        if not db.execute("SELECT 1 FROM reports WHERE order_id=? AND reason='order_dispute'",(oid,)).fetchone():raise error(409,'Open the dispute first.')
        core['check_rate'](db,'dispute_video',uid,5,300)
        if handler.headers.get('Content-Type','').split(';')[0]!='video/mp4':raise error(400,'Choose an MP4 video.')
        import video_evidence
        try:value=video_evidence.normalize(raw)
        except video_evidence.InvalidVideo as exc:raise error(400,str(exc))
        except video_evidence.VideoUnavailable as exc:raise error(503,str(exc))
        core['require_private_evidence_bucket']();key='dispute-video/'+core['ident']()+'/'+core['ident']()+'.mp4'
        core['storage_r2'].put_video_evidence(key,value)
        db.execute('BEGIN IMMEDIATE')
        try:
            core['trade_workflows'].lock_order(db,oid)
            order=core['marketplace_operations'].order_member(db,oid,uid,core)
            if order['status']!='disputed':raise error(409,'This dispute is closed.')
            eid=core['ident']();db.execute('INSERT INTO dispute_entries(id,order_id,sender_id,body) VALUES(?,?,?,?)',(eid,oid,uid,'Private video evidence'))
            db.execute('INSERT INTO dispute_attachments(entry_id,owner_id,object_path) VALUES(?,?,?)',(eid,uid,key))
            core['audit'](db,uid,'dispute_video_uploaded','order',oid);db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');core['delete_account_evidence_object'](key);raise
        return 201,{'id':eid}
    match=re.fullmatch(r'/api/admin/staff/([A-Za-z0-9_-]{1,100})',path)
    if match and method=='POST':
        core['require_admin'](ctx);core['marketplace_operations'].reauthenticate(db,uid,data,core)
        target=match.group(1);scopes=data.get('capabilities')
        if not isinstance(scopes,list) or len(scopes)>3 or any(s not in ('support','moderation','content') for s in scopes):raise error(400,'Choose support, moderation or content permissions.')
        user=db.execute('SELECT email_verified,suspended FROM users WHERE id=?',(target,)).fetchone()
        if not user or not user['email_verified'] or user['suspended']:raise error(400,'Choose a verified, active user.')
        if core['is_admin'](db,target):raise error(400,'Full administrator access is managed separately.')
        put_config(db,'staff_capabilities:'+target,sorted(set(scopes)));core['audit'](db,uid,'staff_permissions_updated','user',target,{'capabilities':scopes})
        core['marketplace_operations'].security_notice(db,target,'Staff permissions updated',core);return {'capabilities':sorted(set(scopes))}
    if path=='/api/launch/profile' and method=='GET':return public_profile(db)
    if path=='/api/admin/launch/profile' and method in ('GET','POST'):
        core['require_admin'](ctx)
        if method=='GET':return config(db,CONFIG_KEY,{'published':False})
        value=validate_profile(data,core);put_config(db,CONFIG_KEY,value);core['audit'](db,uid,'launch_profile_updated','platform',CONFIG_KEY,{'published':value['published']});return value
    if path=='/api/status' and method=='GET':
        incident=config(db,'public_incident',{})
        return {'status':incident.get('status','not_reported'),'message':incident.get('message',''),'updated_at':incident.get('updated_at'),'live_payments':False,'automatic_topup':False,'source':'operator_report','support':public_profile(db)}
    if path=='/api/admin/status' and method=='POST':
        core['require_admin'](ctx)
        if data.get('status') not in ('operational','degraded','maintenance','not_reported'):raise error(400,'Check service status.')
        message=core['clean_text'](data.get('message',''),'Message',0,2000)
        if data['status'] in ('degraded','maintenance') and len(message)<10:raise error(400,'Explain the service interruption.')
        value={'status':data['status'],'message':message,'updated_at':core['now_iso']()};put_config(db,'public_incident',value);core['audit'](db,uid,'status_updated','platform','status',value);return value
    if path=='/api/top-up/preferences' and method in ('GET','POST'):
        core['require_verified'](ctx)
        if method=='POST':
            package=data.get('package_id');kind=data.get('kind');enabled=data.get('enabled')
            if kind not in ('saved','launch_alert') or type(enabled) is not bool:raise error(400,'Check package preference.')
            if not isinstance(package,str) or not db.execute('SELECT 1 FROM topup_packages WHERE id=? AND enabled=1',(package,)).fetchone():raise error(404,'Package not found.')
            if kind=='launch_alert' and enabled and data.get('consent') is not True:raise error(400,'Consent is required for launch notifications.')
            def transform(prefs):
                values=list(prefs.get('topup_'+kind,[]))
                values=[p for p in values if p!=package]
                if enabled:values.append(package)
                if len(values)>100:raise error(400,'At most 100 packages can be saved.')
                prefs['topup_'+kind]=values
            prefs=save_preferences(db,uid,transform,core)
        else:
            row=db.execute('SELECT settings_json FROM experience_preferences WHERE user_id=?',(uid,)).fetchone();prefs=json.loads(row['settings_json']) if row else {}
        return {'saved':prefs.get('topup_saved',[]),'launch_alert':prefs.get('topup_launch_alert',[])}
    match=re.fullmatch(r'/api/admin/top-up/presentation/([A-Za-z0-9_-]{1,120})',path)
    if match and method in ('GET','POST'):
        core['require_admin'](ctx);package=db.execute('SELECT * FROM topup_packages WHERE id=?',(match.group(1),)).fetchone()
        if not package:raise error(404,'Package not found.')
        if method=='GET':return {**core['topup_package_metadata'](package),**package_metadata(package,db)}
        name=core['clean_text'](data.get('product_name'),'Name',2,140);image=data.get('image_url','')
        if image not in set(PACKAGE_ART.values())|{''}:raise error(400,'Choose a supported package image.')
        contents=data.get('contents',[])
        if not isinstance(contents,list) or len(contents)>12:raise error(400,'Check package contents.')
        checked=[]
        for row in contents:
            if not isinstance(row,list) or len(row)!=2 or type(row[1]) is not int or not 1<=row[1]<=1000000:raise error(400,'Each content requires a label and a positive whole quantity.')
            checked.append([core['clean_text'](row[0],'Content',1,70),row[1]])
        value={'product_name':name,'image_url':image,'contents':checked};put_config(db,'topup_presentation:'+package['id'],value);core['audit'](db,uid,'topup_presentation_updated','topup_package',package['id']);return value
    match=re.fullmatch(r'/api/admin/listings/([A-Za-z0-9_-]{1,100})/audience',path)
    if match and method=='POST':
        core['require_admin'](ctx)
        if data.get('audience') not in ('public','test'):raise error(400,'Choose public or test.')
        if not db.execute('SELECT 1 FROM listings WHERE id=?',(match.group(1),)).fetchone():raise error(404,'Listing not found.')
        # Audience is not publication approval: existing safety/sales gates still apply.
        db.execute('INSERT INTO platform_config(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',('listing_audience:'+match.group(1),data['audience']))
        core['audit'](db,uid,'listing_audience_updated','listing',match.group(1),{'audience':data['audience']});return {'audience':data['audience']}
    if path=='/api/account/export' and method=='POST':
        core['require_verified'](ctx);core['marketplace_operations'].reauthenticate(db,uid,data,core);core['check_rate'](db,'personal_export',uid,2,3600)
        result=personal_export(db,uid);core['audit'](db,uid,'personal_data_export','user',uid);return result
    if path=='/api/seller/readiness' and method=='GET':
        core['require_verified'](ctx)
        seller=db.execute('SELECT * FROM seller_profiles WHERE user_id=?',(uid,)).fetchone()
        listings=[dict(r) for r in db.execute('SELECT * FROM listings WHERE seller_id=? ORDER BY updated_at DESC LIMIT 100',(uid,))]
        return {'profile_created':bool(seller),'identity_verified':bool(seller and seller['identity_provider']=='didit' and seller['identity_status']=='verified'),'selling_enabled':bool(seller and seller['selling_enabled']),'listings':[{'id':r['id'],'title':r['title'],'status':r['status'],'issues':core['marketplace_operations'].quality(r)} for r in listings],'sales_enabled':core['production_marketplace_sales_enabled']() and core['MODE']=='production'}
    match=re.fullmatch(r'/api/stores/([A-Za-z0-9_-]{1,100})/reputation',path)
    if match and method=='GET':
        if not db.execute('SELECT 1 FROM seller_profiles WHERE user_id=?',(match.group(1),)).fetchone():raise error(404,'Store not found.')
        return reputation(db,match.group(1))
    match=re.fullmatch(r'/api/seller/listings/([A-Za-z0-9_-]{1,100})/price-tiers',path)
    if match and method in ('GET','POST'):
        core['require_verified'](ctx);lid=match.group(1)
        row=db.execute('SELECT * FROM listings WHERE id=? AND seller_id=?',(lid,uid)).fetchone()
        if not row:raise error(404,'Listing not found.')
        if method=='GET':return {'base_price_minor':row['price_minor'],'tiers':config(db,'listing_tiers:'+lid,[])}
        core['seller_ok'](db,uid);tiers=data.get('tiers')
        if not isinstance(tiers,list) or len(tiers)>5:raise error(400,'Use at most five quantity tiers.')
        previous_quantity=row['min_quantity']-1;previous_price=row['price_minor'];checked=[]
        for tier in tiers:
            if not isinstance(tier,dict) or set(tier)!={'quantity','unit_price_minor'} or any(type(v) is not int for v in tier.values()):raise error(400,'A tier needs a whole quantity and unit price.')
            q,p=tier['quantity'],tier['unit_price_minor']
            if not previous_quantity<q<=1000000 or not 0<p<=previous_price:raise error(400,'Quantities must increase and unit prices must not increase.')
            checked.append(tier);previous_quantity=q;previous_price=p
        db.execute('BEGIN IMMEDIATE')
        try:
            # Do not change prices underneath an outstanding reservation.
            locked=db.execute('UPDATE listings SET updated_at=CURRENT_TIMESTAMP WHERE id=? AND seller_id=? AND reserved=0',(lid,uid)).rowcount
            if not locked:raise error(409,'Wait until outstanding reservations are cleared.')
            put_config(db,'listing_tiers:'+lid,checked)
            db.execute("UPDATE listings SET status='pending_review' WHERE id=? AND status IN ('published','approved_private')",(lid,))
            core['audit'](db,uid,'quantity_prices_updated','listing',lid,{'tiers':checked});db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'tiers':checked,'moderation_required':True}
    match=re.fullmatch(r'/api/seller/listings/([A-Za-z0-9_-]{1,100})/service-plan',path)
    if match and method in ('GET','POST'):
        core['require_verified'](ctx);lid=match.group(1)
        row=db.execute('SELECT * FROM listings WHERE id=? AND seller_id=?',(lid,uid)).fetchone()
        if not row:raise error(404,'Listing not found.')
        if row['product_type']!='service':raise error(400,'Milestones apply to service listings only.')
        if method=='GET':return {'steps':config(db,'service_plan:'+lid,[])}
        core['seller_ok'](db,uid);steps=data.get('steps')
        if not isinstance(steps,list) or len(steps)>10:raise error(400,'Use at most ten service milestones.')
        steps=[core['clean_text'](step,'Milestone',5,200) for step in steps]
        if len(set(steps))!=len(steps):raise error(400,'Use different milestone titles.')
        db.execute('BEGIN IMMEDIATE')
        try:
            if not db.execute('UPDATE listings SET updated_at=CURRENT_TIMESTAMP WHERE id=? AND seller_id=? AND reserved=0',(lid,uid)).rowcount:raise error(409,'Wait until outstanding reservations are cleared.')
            put_config(db,'service_plan:'+lid,steps)
            db.execute("UPDATE listings SET status='pending_review' WHERE id=? AND status IN ('published','approved_private')",(lid,))
            core['audit'](db,uid,'service_plan_updated','listing',lid,{'steps':steps});db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'steps':steps,'moderation_required':True}
    match=re.fullmatch(r'/api/orders/([A-Za-z0-9_-]{1,100})/milestones(?:/([A-Za-z0-9_-]{1,100})/([0-9]{1,2}))?',path)
    if match and method in ('GET','POST'):
        core['require_verified'](ctx);oid,iid,index=match.groups();order=core['marketplace_operations'].order_member(db,oid,uid,core)
        if method=='GET':
            items=db.execute('SELECT id,title,seller_id,snapshot_json FROM order_items WHERE order_id=?'+('' if uid==order['buyer_id'] or core['is_admin'](db,uid) else ' AND seller_id=?'),(oid,) if uid==order['buyer_id'] or core['is_admin'](db,uid) else (oid,uid)).fetchall()
            return {'buyer':uid==order['buyer_id'],'items':[{'id':i['id'],'title':i['title'],'seller':uid==i['seller_id'],'steps':milestones(db,i)} for i in items]}
        if not iid or index is None:raise error(400,'Choose a milestone.')
        action=data.get('action');note=core['clean_text'](data.get('note',''),'Milestone note',0,2000)
        if action not in ('submit','accept','request_changes'):raise error(400,'Check milestone action.')
        db.execute('BEGIN IMMEDIATE')
        try:
            core['trade_workflows'].lock_order(db,oid)
            order=core['marketplace_operations'].order_member(db,oid,uid,core)
            if order['status'] not in ('paid','awaiting_delivery','delivered'):raise error(409,'This order cannot change service progress now.')
            item=db.execute('SELECT id,seller_id,snapshot_json FROM order_items WHERE id=? AND order_id=?',(iid,oid)).fetchone()
            if not item:raise error(404,'Order item not found.')
            steps=milestones(db,item);index=int(index)
            if not 0<=index<len(steps):raise error(404,'Milestone not found.')
            current=steps[index]
            if action=='submit':
                if uid!=item['seller_id']:raise error(403,'Only this service seller can submit its result.')
                if current['status']=='accepted' or any(s['status']!='accepted' for s in steps[:index]):raise error(409,'Complete previous milestones first.')
                if len(note)<10:raise error(400,'Describe the delivered result.')
                state='submitted';target=order['buyer_id']
            else:
                if uid!=order['buyer_id']:raise error(403,'Only the buyer can review this milestone.')
                if current['status']!='submitted':raise error(409,'The seller has not submitted this milestone.')
                if action=='request_changes' and len(note)<10:raise error(400,'Explain the required changes.')
                state='accepted' if action=='accept' else 'changes_requested';target=item['seller_id']
            saved=config(db,'service_progress:'+iid,{})
            saved[str(index)]={'status':state,'note':note,'updated_at':core['now_iso']()};put_config(db,'service_progress:'+iid,saved)
            core['audit'](db,uid,'service_milestone_'+state,'order_item',iid,{'index':index})
            core['notify'](db,target,'order','Service milestone updated',current['title'],'/order/'+oid)
            db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'index':index,'status':state,'funds_released':False}
    return UNHANDLED

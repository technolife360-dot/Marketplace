"""Opt-in, account-scoped Web Push. Notifications contain no chat/order details."""
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime,timezone
from urllib.parse import urlparse
import launch_readiness as launch
import marketplace_operations as ops

PROVIDERS={'fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com'}

def b64(value):return base64.urlsafe_b64encode(value).rstrip(b'=').decode()
def decode(value):return base64.urlsafe_b64decode(value+'='*((4-len(value)%4)%4))

def validate(value):
    if not isinstance(value,dict):raise ValueError('Invalid subscription.')
    endpoint=value.get('endpoint','');keys=value.get('keys',{})
    if not isinstance(endpoint,str) or len(endpoint)>4096 or not isinstance(keys,dict):raise ValueError('Invalid subscription.')
    parsed=urlparse(endpoint)
    if parsed.scheme!='https' or parsed.hostname not in PROVIDERS or parsed.port not in (None,443) or parsed.username or parsed.password or parsed.fragment or len(parsed.path)<10:raise ValueError('Unsupported push provider.')
    try:
        from cryptography.hazmat.primitives.asymmetric import ec
        if len(decode(keys['auth']))!=16:raise ValueError('Invalid subscription keys.')
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),decode(keys['p256dh']))
    except Exception as exc:raise ValueError('Invalid subscription keys.') from exc
    return {'endpoint':endpoint,'keys':{'auth':keys['auth'],'p256dh':keys['p256dh']}}

def keypair(db,core):
    saved=launch.config(db,'webpush_vapid')
    if not saved:
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import serialization
        key=ec.generate_private_key(ec.SECP256R1())
        private=b64(key.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        public=b64(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint))
        encrypted=core['delivery_crypto'].encrypt_payload(private,'webpush-vapid:v1')
        db.execute("INSERT INTO platform_config(key,value) VALUES('webpush_vapid',?) ON CONFLICT(key) DO NOTHING",(json.dumps({'public':public,'cipher':encrypted}),))
        saved=launch.config(db,'webpush_vapid')
    return saved

def token():
    scoped=os.environ.get('PUSH_DISPATCH_TOKEN','').strip()
    if len(scoped)>=32:return scoped
    secret=os.environ.get('CRON_SECRET','')
    return hmac.new(secret.encode(),b'webpush-dispatch-v1',hashlib.sha256).hexdigest() if len(secret)>=24 else ''

def dispatch(db,core,send=None,limit=3):
    if send is None:
        from pywebpush import webpush
        send=webpush
    pair=launch.config(db,'webpush_vapid')
    if not pair:return {'configured':False,'sent':0,'failed':0}
    private=core['delivery_crypto'].decrypt_payload(pair['cipher'],'webpush-vapid:v1')
    result={'configured':True,'sent':0,'failed':0};attempted=0;deadline=time.monotonic()+7
    cursor=launch.config(db,'webpush_cursor','')
    # Rotate the complete bounded batch: an empty account after the cursor
    # must not postpone an earlier account with newly queued notifications.
    accounts=db.execute("SELECT user_id,settings_json FROM experience_preferences WHERE settings_json LIKE '%push_devices%' ORDER BY CASE WHEN user_id>? THEN 0 ELSE 1 END,user_id LIMIT 100",(cursor,)).fetchall()
    for account in accounts:
        if attempted>=limit or time.monotonic()>deadline:return result
        launch.put_config(db,'webpush_cursor',account['user_id'])
        uid=account['user_id'];prefs=json.loads(account['settings_json'])
        if not prefs.get('browser'):continue
        user=db.execute('SELECT suspended,email_verified FROM users WHERE id=?',(uid,)).fetchone()
        if not user or user['suspended'] or not user['email_verified']:continue
        devices=prefs.get('push_devices',[]);cursor_device=prefs.get('push_device_cursor','')
        devices=sorted(devices,key=lambda d:(d['id']<=cursor_device,d['id']))
        for device in devices:
            if attempted>=limit or time.monotonic()>deadline:return result
            subscription=json.loads(core['delivery_crypto'].decrypt_payload(device['cipher'],'webpush:'+uid))
            validate(subscription)
            unread=[dict(r) for r in db.execute('SELECT id,kind,created_at FROM notifications WHERE user_id=? AND read_at IS NULL ORDER BY created_at DESC LIMIT 50',(uid,)) if r['id'] not in device.get('delivered',[]) and ops.utc(r['created_at'])>=ops.utc(device['since']) and core['catalogue_experience'].notification_allowed(db,uid,r['kind'])]
            if not unread:continue
            attempted+=1
            ids=[r['id'] for r in unread]
            try:
                send(subscription_info=subscription,data=json.dumps({'title':'SentryLoot','body':{'uz':'Hisobingizda yangi bildirishnoma bor.','ru':'В вашем аккаунте новое уведомление.','en':'You have a new account notification.'},'tag':ids[0]}),vapid_private_key=private,vapid_claims={'sub':'mailto:sentryloot@gamestorehub.com'},ttl=300,timeout=2)
            except Exception as exc:
                response=getattr(exc,'response',None);status=getattr(response,'status_code',None) if response is not None else getattr(exc,'status_code',None)
                if status in (404,410):
                    launch.save_preferences(db,uid,lambda p:p.update(push_devices=[d for d in p.get('push_devices',[]) if d['id']!=device['id']]),core)
                else:result['failed']+=1
                continue
            def mark(p):
                p['push_device_cursor']=device['id']
                for current in p.get('push_devices',[]):
                    if current['id']==device['id']:current['delivered']=list(dict.fromkeys(ids+current.get('delivered',[])))[:100]
            launch.save_preferences(db,uid,mark,core);result['sent']+=1
    return result

def route(handler,db,ctx,method,path,data,core):
    if path=='/api/cron/push-delivery' and method=='POST':
        expected=token()
        if not expected or not hmac.compare_digest(handler.headers.get('Authorization',''),'Bearer '+expected):raise core['HttpError'](403,'Push dispatch authorization required.')
        result=dispatch(db,core);launch.put_config(db,'webpush_last_dispatch',{'at':core['now_iso'](),**result});return result
    if path not in ('/api/push/setup','/api/push/subscriptions'):return launch.UNHANDLED
    core['require_verified'](ctx);uid=ctx['uid'];core['check_rate'](db,'push_setup',uid,20,3600)
    if path=='/api/push/setup' and method=='POST':
        try:pair=keypair(db,core)
        except core['delivery_crypto'].DeliveryCryptoError:raise core['HttpError'](503,'Push encryption is not configured.')
        return {'public_key':pair['public']}
    if path=='/api/push/subscriptions' and method=='POST':
        if data.get('consent') is not True:raise core['HttpError'](400,'Push notification consent is required.')
        try:subscription=validate(data.get('subscription'))
        except ValueError as exc:raise core['HttpError'](400,str(exc))
        fingerprint=hashlib.sha256(subscription['endpoint'].encode()).hexdigest()
        cipher=core['delivery_crypto'].encrypt_payload(json.dumps(subscription),'webpush:'+uid)
        def add(p):
            devices=[d for d in p.get('push_devices',[]) if d['id']!=fingerprint]
            if len(devices)>=5:raise core['HttpError'](400,'At most five push devices per account.')
            devices.append({'id':fingerprint,'cipher':cipher,'since':ops.iso(datetime.now(timezone.utc)),'delivered':[r['id'] for r in db.execute('SELECT id FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 100',(uid,))]});p.update(push_devices=devices,browser=True)
        launch.save_preferences(db,uid,add,core);return {'id':fingerprint,'enabled':True}
    if path=='/api/push/subscriptions' and method=='DELETE':
        endpoint=data.get('endpoint','')
        if not isinstance(endpoint,str):raise core['HttpError'](400,'Invalid endpoint.')
        fingerprint=hashlib.sha256(endpoint.encode()).hexdigest()
        launch.save_preferences(db,uid,lambda p:p.update(push_devices=[d for d in p.get('push_devices',[]) if d['id']!=fingerprint]),core)
        return {'enabled':False}
    raise core['HttpError'](405,'Method not allowed.')

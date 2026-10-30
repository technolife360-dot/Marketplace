"""Transactional platform promotions. Credits are not cash or seller proceeds.

All records use the existing private/RLS-protected configuration table. Quotes
snapshot server FX before transactions; reserving/settling never calls a service.
Ledger amounts are USD micro-units; legacy bonus points are deliberately separate.
"""
import hashlib
import json
import math
import re
import secrets
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING, InvalidOperation
import launch_readiness as launch

UNHANDLED=object()
PREFIX='rewards2:'
SCALE=1000000
DEFAULTS={'enabled':True,'account_bps':100,'topup_bps':50,'redemption_bps':2000,
          'stacking':False,'credit_expiry_days':180}

def read(db,key,default=None):
    return launch.config(db,key,default)

def write(db,key,value):
    launch.put_config(db,key,value)

def rows(db,prefix):
    return [json.loads(row['value']) for row in db.execute(
        'SELECT value FROM platform_config WHERE key>=? AND key<? ORDER BY key',(prefix,prefix+'~'))]

def user_hash(uid):
    return hashlib.sha256(uid.encode()).hexdigest()[:32]

def stamp():
    return datetime.now(timezone.utc).isoformat()

def settings(db):
    return {**DEFAULTS,**read(db,PREFIX+'settings',{})}

def mode(core):
    try:return 'test' if core['configured_payment_provider']().name in ('sandbox','stripe_test') else 'real'
    except RuntimeError:return 'real'

def fail(core,message,status=409):
    raise core['HttpError'](status,message)

def lock(db):
    # A stable shared row also serializes different buyers competing for a code
    # on PostgreSQL (BEGIN IMMEDIATE alone only serializes SQLite).
    db.execute("INSERT INTO platform_config(key,value) VALUES(?,'{}') ON CONFLICT(key) DO NOTHING",(PREFIX+'lock',))
    db.execute('UPDATE platform_config SET updated_at=updated_at WHERE key=?',(PREFIX+'lock',))

def rates(core):
    snapshot=core['regional_preferences'].exchange_rates()
    now=time.time();updated=snapshot.get('updated_at')
    if (snapshot.get('available') is False or not snapshot.get('rates') or type(updated) not in (int,float)
            or not 0<=now-updated<=172800):
        fail(core,'Rewards exchange rates are unavailable. Retry or continue without promotional benefits.',503)
    result={}
    for currency,raw in snapshot['rates'].items():
        if not isinstance(currency,str) or not re.fullmatch('[A-Z]{3}',currency):continue
        try:value=Decimal(str(raw))
        except (InvalidOperation,ValueError,TypeError):fail(core,'Rewards exchange rates are unavailable.',503)
        if not value.is_finite() or value<=0:fail(core,'Rewards exchange rates are invalid.',503)
        result[currency]=str(value)
    if not all(c in result for c in ('USD','MYR','UZS')) or Decimal(result['USD'])!=1:fail(core,'Rewards exchange-rate base is invalid.',503)
    return {'rates':result,'updated_at':int(updated)}

def factor(currency):
    return 1 if currency=='UZS' else 100

def to_micro(amount,currency,fx,ceil=False):
    result=Decimal(amount)*SCALE/Decimal(factor(currency))/Decimal(fx[currency])
    return int(result.to_integral_value(rounding=ROUND_CEILING if ceil else ROUND_FLOOR))

def from_micro(amount,currency,fx):
    return int((Decimal(amount)*Decimal(fx[currency])*factor(currency)/SCALE).to_integral_value(rounding=ROUND_FLOOR))

def key_for(kind,uid,identifier):
    return PREFIX+kind+':'+user_hash(uid)+':'+identifier

def lots(db,uid,current_mode):
    return [lot for lot in rows(db,key_for('lot',uid,'')) if lot['uid']==uid and lot['mode']==current_mode]

def wallet_values(db,uid,current_mode,kind=None):
    now=int(time.time());available=pending=exposure=0
    for lot in lots(db,uid,current_mode):
        if lot['state']=='active' and lot['expires_at']>now and (kind is None or lot.get('scope','both') in ('both',kind)):available+=lot['remaining_micro']
        elif lot['state']=='pending':pending+=lot['remaining_micro']
        if lot['state'] in ('revoked','frozen'):
            exposure+=max(0,lot['amount_micro']-lot['remaining_micro'])
    return {'balance_micro':available-exposure,'available_micro':max(0,available-exposure),
            'pending_micro':pending,'debt_micro':max(0,exposure-available),'exposure_micro':exposure}

def wallet(db,uid,core,fx=None):
    current_mode=mode(core)
    if fx is None:
        try:fx=rates(core)
        except core['HttpError']:fx={'rates':{'USD':'1'},'updated_at':None}
    user=db.execute('SELECT currency FROM users WHERE id=?',(uid,)).fetchone()
    history=rows(db,key_for('entry',uid,''))
    history=[{k:v for k,v in row.items() if k!='uid'} for row in history if row['uid']==uid and row['mode']==current_mode]
    return {**wallet_values(db,uid,current_mode),'mode':current_mode,'test_only':current_mode=='test',
            'settings':settings(db),'display_currency':user['currency'] if user and user['currency'] in fx['rates'] else 'USD',
            'rates':fx['rates'],'usable_for':{kind:wallet_values(db,uid,current_mode,kind)['available_micro'] for kind in ('account','topup')},
            'history':sorted(history,key=lambda x:x['created_at'],reverse=True)[:50]}

def entry(db,uid,current_mode,kind,amount,reference,core):
    identifier=core['ident']()
    write(db,key_for('entry',uid,identifier),{'id':identifier,'uid':uid,'mode':current_mode,
          'type':kind,'amount_micro':amount,'reference':reference,'status':kind,'created_at':stamp()})

def make_lot(db,uid,current_mode,identifier,amount,days,state,reference,core,scope='both'):
    key=key_for('lot',uid,identifier)
    lot={'id':identifier,'uid':uid,'mode':current_mode,'amount_micro':amount,'remaining_micro':amount,
         'state':state,'expires_at':int(time.time())+days*86400,'reference':reference,'scope':scope}
    write(db,key,lot)
    return identifier

def context(db,uid,data,core):
    kind=data.get('kind')
    if kind=='topup':
        quantity=data.get('quantity',1)
        if type(quantity) is not int or not 1<=quantity<=99:fail(core,'Choose a quantity from 1 to 99.',400)
        row=db.execute('SELECT id,price_minor,currency FROM topup_packages WHERE id=? AND enabled=1',(data.get('package_id'),)).fetchone()
        if not row or row['price_minor']<=0:fail(core,'This Top Up package has no price.')
        return [{'package_id':row['id'],'quantity':quantity,'price_minor':row['price_minor']}],'UZS',row['price_minor']*quantity,0
    if kind!='account':fail(core,'Choose account or topup rewards.',400)
    lines=[dict(r) for r in db.execute('SELECT c.listing_id,c.quantity,l.* FROM carts c JOIN listings l ON l.id=c.listing_id WHERE c.user_id=? ORDER BY l.id',(uid,))]
    if not lines or any(x['product_type']!='account' for x in lines):fail(core,'These promotional benefits apply to account purchases and Top Up only.')
    if len({x['currency'] for x in lines})!=1:fail(core,'Choose products in one currency.')
    for line in lines:line['price_minor']=launch.unit_price(db,line['listing_id'],line['price_minor'],line['quantity'])
    subtotal=sum(x['price_minor']*x['quantity'] for x in lines)
    bps=int(read(db,'commission_bps',0))
    return lines,lines[0]['currency'],subtotal,subtotal*bps//10000

def fingerprint(kind,lines,currency,subtotal,fee):
    if kind=='topup':bound=[{k:x.get(k) for k in ('package_id','quantity','price_minor')} for x in lines]
    else:bound=[{k:x.get(k) for k in ('listing_id','quantity','price_minor','product_type')} for x in lines]
    return hashlib.sha256(json.dumps([kind,sorted(bound,key=lambda x:json.dumps(x,sort_keys=True)),currency,subtotal,fee],sort_keys=True,separators=(',',':')).encode()).hexdigest()

def code_value(value,core):
    if not isinstance(value,str):fail(core,'Enter a valid promotional code.',400)
    value=value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{6,32}',value):fail(core,'Use a code with 6–32 letters or numbers.',400)
    return value

def campaign_key(code):
    return PREFIX+'campaign:'+hashlib.sha256(code.encode()).hexdigest()

def check_campaign(db,code,uid,current_mode,kind,core):
    campaign=read(db,campaign_key(code))
    if (not campaign or campaign['mode']!=current_mode or campaign['kind']!=kind
            or not campaign['enabled'] or campaign['expires_at']<=int(time.time())):
        fail(core,'This promotional code is unavailable or expired.')
    if campaign.get('recipient_id') and campaign['recipient_id']!=uid:fail(core,'This code belongs to another account.',403)
    return campaign

def uses(db,campaign,uid):
    state=read(db,PREFIX+'usage:'+campaign['id'],{'total':0})
    return state,read(db,PREFIX+'usage-user:'+campaign['id']+':'+user_hash(uid),0)

def check_uses(db,campaign,uid,core):
    state,own=uses(db,campaign,uid)
    if state['total']>=campaign['max_uses'] or own>=campaign['per_user_limit']:fail(core,'This promotional code has reached its usage limit.')

def change_uses(db,campaign_id,uid,delta):
    key=PREFIX+'usage:'+campaign_id;state=read(db,key,{'total':0})
    state['total']+=delta;write(db,key,state)
    own_key=PREFIX+'usage-user:'+campaign_id+':'+user_hash(uid)
    write(db,own_key,read(db,own_key,0)+delta)

def quote(db,uid,data,core):
    fx=rates(core);lines,currency,subtotal,fee=context(db,uid,data,core)
    if currency not in ('UZS','MYR'):fail(core,'This checkout currency is not supported for promotional benefits.')
    opts=settings(db)
    if not opts['enabled']:fail(core,'Promotional benefits are paused.')
    use_bonus=data.get('use_bonus',False)
    if type(use_bonus) is not bool:fail(core,'Check the bonus selection.',400)
    raw_code=data.get('coupon_code','')
    if not isinstance(raw_code,str):fail(core,'Check the promotional code.',400)
    code=code_value(raw_code,core) if raw_code.strip() else ''
    if code and use_bonus and not opts['stacking']:fail(core,'Use either a coupon or bonus credit for this purchase.')
    current_mode=mode(core);discount=0;campaign=None;gross=subtotal+fee
    if code:
        campaign=check_campaign(db,code,uid,current_mode,'coupon',core);check_uses(db,campaign,uid,core)
        if campaign['scope'] not in ('both',data['kind']):fail(core,'This coupon does not match this product type.')
        if to_micro(subtotal,currency,fx['rates'])<to_micro(campaign['minimum_minor'],campaign['currency'],fx['rates']):fail(core,'The minimum purchase amount for this coupon has not been reached.')
        discount=subtotal*campaign['value']//10000 if campaign['discount_type']=='percent' else from_micro(to_micro(campaign['value'],campaign['currency'],fx['rates']),currency,fx['rates'])
        if campaign['maximum_discount_minor']:
            discount=min(discount,from_micro(to_micro(campaign['maximum_discount_minor'],campaign['currency'],fx['rates']),currency,fx['rates']))
        discount=min(discount,subtotal,gross-1)
    available=wallet_values(db,uid,current_mode,data['kind'])['available_micro']
    bonus=min(from_micro(available,currency,fx['rates']),(gross-discount)*opts['redemption_bps']//10000,gross-discount-1) if use_bonus else 0
    if use_bonus and bonus<=0:fail(core,'No usable bonus credit is available for this purchase.')
    # No cashback loop: credits and discounts never earn further credits.
    eligible=max(0,subtotal-discount-bonus)
    earn=to_micro(eligible,currency,fx['rates'])*opts['account_bps' if data['kind']=='account' else 'topup_bps']//10000
    identifier=secrets.token_urlsafe(24)
    value={'id':identifier,'uid':uid,'kind':data['kind'],'mode':current_mode,'test_only':current_mode=='test',
           'currency':currency,'subtotal_minor':subtotal,'fee_minor':fee,'gross_total_minor':gross,
           'discount_minor':discount,'bonus_minor':bonus,'total_minor':gross-discount-bonus,
           'spent_micro':to_micro(bonus,currency,fx['rates'],ceil=True),'earn_micro':earn,
           'expires_at':int(time.time())+300,'rates':{c:fx['rates'][c] for c in ('USD','UZS','MYR')},'fx_updated_at':fx['updated_at'],
           'context':fingerprint(data['kind'],lines,currency,subtotal,fee),'campaign_id':campaign['id'] if campaign else '',
           'campaign_code':code,'credit_expiry_days':opts['credit_expiry_days'],'created_at':stamp()}
    write(db,PREFIX+'quote:'+identifier,value)
    user=db.execute('SELECT currency FROM users WHERE id=?',(uid,)).fetchone()
    display=user['currency'] if user and user['currency'] in fx['rates'] else 'USD'
    return {**{k:v for k,v in value.items() if k not in ('uid','context','rates')},
            'display_currency':display,'rates':{'USD':'1',display:fx['rates'][display]}}

def purchase(db,kind,source_id):
    key=read(db,PREFIX+'source:'+kind+':'+source_id)
    return read(db,key) if key else None

def save_purchase(db,value):
    write(db,key_for('purchase',value['uid'],value['id']),value)

def reserve(db,uid,quote_id,kind,source_id,lines,currency,subtotal,fee,core):
    lock(db)
    if purchase(db,kind,source_id):fail(core,'This purchase already has promotional benefits. Reuse the original checkout request.')
    if not isinstance(quote_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',quote_id):fail(core,'Refresh the promotional quote.',400)
    value=read(db,PREFIX+'quote:'+quote_id)
    if (not value or value['uid']!=uid or value['mode']!=mode(core) or value['kind']!=kind
            or value['expires_at']<=time.time() or value['context']!=fingerprint(kind,lines,currency,subtotal,fee)
            or value.get('consumed_by') or not settings(db)['enabled']):
        fail(core,'This promotional quote changed or expired. Review the total again.')
    if value['spent_micro']>wallet_values(db,uid,value['mode'],kind)['available_micro']:fail(core,'Your bonus balance changed. Refresh the quote.')
    if value['campaign_id']:
        campaign=check_campaign(db,value['campaign_code'],uid,value['mode'],'coupon',core)
        check_uses(db,campaign,uid,core);change_uses(db,campaign['id'],uid,1)
    allocations=[];remaining=value['spent_micro']
    for lot in sorted(lots(db,uid,value['mode']),key=lambda x:(x['expires_at'],x['id'])):
        if lot['state']!='active' or lot['expires_at']<=time.time() or lot.get('scope','both') not in ('both',kind):continue
        amount=min(remaining,lot['remaining_micro'])
        if amount:
            lot['remaining_micro']-=amount;remaining-=amount
            write(db,key_for('lot',uid,lot['id']),lot);allocations.append({'lot_id':lot['id'],'amount_micro':amount})
        if remaining<=0:break
    if remaining:fail(core,'Your bonus balance changed. Refresh the quote.')
    identifier=core['ident']();value={**value,'id':identifier,'quote_id':quote_id,'source_id':source_id,
        'allocations':allocations,'state':'held','credits_restored':False,'campaign_released':False,
        'earn_lot_id':identifier,'earned_once':False}
    make_lot(db,uid,value['mode'],identifier,value['earn_micro'],value['credit_expiry_days'],'pending',source_id,core)
    save_purchase(db,value);write(db,PREFIX+'source:'+kind+':'+source_id,key_for('purchase',uid,identifier))
    consumed=read(db,PREFIX+'quote:'+quote_id);consumed['consumed_by']=source_id;write(db,PREFIX+'quote:'+quote_id,consumed)
    if value['spent_micro']:entry(db,uid,value['mode'],'reserved',-value['spent_micro'],source_id,core)
    return value

def settle(db,record,state,verified,refund_confirmed,core):
    lock(db)
    # Re-read under the shared lock after a concurrent callback/claim.
    record=purchase(db,record['kind'],record['source_id'])
    lot=read(db,key_for('lot',record['uid'],record['earn_lot_id']))
    cancelled=state=='cancelled' and not verified
    if refund_confirmed or cancelled:
        if not record['credits_restored']:
            for allocation in record['allocations']:
                key=key_for('lot',record['uid'],allocation['lot_id']);original=read(db,key)
                original['remaining_micro']+=allocation['amount_micro'];write(db,key,original)
            record['credits_restored']=True
            if record['spent_micro']:entry(db,record['uid'],record['mode'],'restored',record['spent_micro'],record['source_id'],core)
        if record['campaign_id'] and not record['campaign_released']:
            change_uses(db,record['campaign_id'],record['uid'],-1);record['campaign_released']=True
        if lot['state'] not in ('revoked',) and record['earned_once']:
            entry(db,record['uid'],record['mode'],'reversed',-lot['amount_micro'],record['source_id'],core)
        lot['state']='revoked';record['state']='refunded' if refund_confirmed else 'cancelled'
    elif state=='completed' and verified:
        if lot['state']!='active':
            if not record['earned_once']:
                entry(db,record['uid'],record['mode'],'earned',lot['amount_micro'],record['source_id'],core)
                lot['expires_at']=int(time.time())+record['credit_expiry_days']*86400
            lot['state']='active';record['earned_once']=True
        record['state']='completed'
    elif state in ('disputed','refund_pending','refunded'):
        if record['earned_once']:lot['state']='frozen'
        record['state']='refund_pending' if state in ('refunded','refund_pending') else 'disputed'
    elif verified:record['state']='paid'
    write(db,key_for('lot',record['uid'],lot['id']),lot);save_purchase(db,record)

def sync_order(db,oid,core):
    record=purchase(db,'account',oid)
    if not record:return
    order=db.execute('SELECT status,buyer_id,payment_mode,currency,total_minor FROM orders WHERE id=?',(oid,)).fetchone()
    payment=db.execute('SELECT status,provider,amount_minor,currency FROM payments WHERE order_id=?',(oid,)).fetchone()
    if not order or not payment:return
    test=payment['provider'] in ('sandbox','stripe_test')
    if ((record['mode']=='test')!=test or record['uid']!=order['buyer_id']
            or payment['amount_minor']!=record['total_minor'] or payment['currency']!=record['currency']
            or order['payment_mode']!=payment['provider'] or order['currency']!=record['currency']
            or order['total_minor']!=record['total_minor']):
        fail(core,'Rewards payment reconciliation is required.')
    verified=payment['status'] in ('succeeded','refund_pending')
    settle(db,record,order['status'],verified,payment['status'] in ('refunded','sandbox_refunded'),core)

def sync_topup(db,oid,core):
    record=purchase(db,'topup',oid)
    if not record:return
    order=db.execute('SELECT status,buyer_id,payment_reference FROM topup_orders WHERE id=?',(oid,)).fetchone()
    if not order or order['buyer_id']!=record['uid']:return
    reference=order['payment_reference'] or ''
    is_test=reference.startswith('stripe_test_') or bool(read(db,'stripe_test:topup:'+oid))
    if (record['mode']=='test')!=is_test:fail(core,'Rewards Top Up mode reconciliation is required.')
    paid=read(db,'stripe_test:paid:'+oid) if is_test else None
    verified=bool(paid and reference=='stripe_test_'+paid.get('intent','')
                  and paid.get('amount_minor')==record['total_minor'] and paid.get('currency')==record['currency']) if is_test else False
    # A future live supplier adapter must provide an independently verified
    # receipt; a manually entered payment_reference cannot mint real credits.
    settle(db,record,order['status'],verified,verified and order['status']=='refunded',core)

def campaign_view(campaign):
    return {**campaign,'expires_at':datetime.fromtimestamp(campaign['expires_at'],timezone.utc).isoformat()}

def admin_view(db,core):
    current_mode=mode(core);all_lots=rows(db,PREFIX+'lot:');all_purchases=rows(db,PREFIX+'purchase:')
    issued=sum(x['amount_micro'] for x in all_lots if x['mode']==current_mode and x['state']=='active')
    pending=sum(x['remaining_micro'] for x in all_lots if x['mode']==current_mode and x['state']=='pending')
    spent=sum(x['spent_micro'] for x in all_purchases if x['mode']==current_mode and x['state']=='completed')
    liability=sum(x['remaining_micro'] for x in all_lots if x['mode']==current_mode and x['state']=='active' and x['expires_at']>time.time())
    return {'settings':settings(db),'mode':current_mode,'test_only':current_mode=='test',
            'campaigns':[{**campaign_view(x),'used':uses(db,x,'')[0]['total']} for x in rows(db,PREFIX+'campaign:') if x['mode']==current_mode],
            'summary':{'issued_micro':issued,'spent_micro':spent,'pending_micro':pending,'liability_micro':liability}}

def create_campaign(db,uid,data,core):
    kind=data.get('kind');discount_type=data.get('discount_type','fixed');scope=data.get('scope','both');currency=data.get('currency','USD')
    if kind not in ('coupon','voucher') or scope not in ('account','topup','both') or currency not in ('USD','UZS','MYR') or discount_type not in ('percent','fixed'):
        fail(core,'Check campaign kind, scope and currency.',400)
    if kind=='voucher' and discount_type!='fixed':fail(core,'A voucher needs a fixed credit amount.',400)
    value=data.get('value');minimum=data.get('minimum_minor',0);maximum=data.get('maximum_discount_minor',0)
    if type(value) is not int or not 1<=value<=1000000000000 or any(type(x) is not int or not 0<=x<=1000000000000 for x in (minimum,maximum)):
        fail(core,'Enter valid whole-unit campaign amounts.',400)
    if discount_type=='percent' and value>10000:fail(core,'Discount cannot exceed 100%.',400)
    count=data.get('max_uses',1);per_user=data.get('per_user_limit',1);enabled=data.get('enabled',True)
    if type(count) is not int or not 1<=count<=100000 or type(per_user) is not int or not 1<=per_user<=count or type(enabled) is not bool:
        fail(core,'Check campaign usage limits.',400)
    recipient=data.get('recipient_id','')
    if not isinstance(recipient,str) or (recipient and not db.execute('SELECT 1 FROM users WHERE id=?',(recipient,)).fetchone()):fail(core,'Choose an existing recipient account.',400)
    try:expires=int(datetime.fromisoformat(str(data.get('expires_at','')).replace('Z','+00:00')).timestamp())
    except (ValueError,TypeError,OverflowError):fail(core,'Choose a valid expiry date.',400)
    if expires<=time.time():fail(core,'Choose a future expiry date.',400)
    code=code_value(data.get('code') or secrets.token_hex(12).upper(),core)
    fx=rates(core) if kind=='voucher' else None
    amount=to_micro(value,currency,fx['rates']) if fx else 0
    if kind=='voucher' and amount<=0:fail(core,'Voucher amount is too small.',400)
    db.execute('BEGIN IMMEDIATE')
    try:
        lock(db)
        if read(db,campaign_key(code)):fail(core,'This promotional code already exists.')
        campaign={'id':core['ident'](),'code':code,'mode':mode(core),'kind':kind,'scope':scope,'discount_type':discount_type,
            'value':value,'currency':currency,'minimum_minor':minimum,'maximum_discount_minor':maximum,
            'max_uses':1 if kind=='voucher' else count,'per_user_limit':1 if kind=='voucher' else per_user,
            'recipient_id':recipient,'expires_at':expires,'enabled':enabled,'amount_micro':amount,'created_at':stamp()}
        write(db,campaign_key(code),campaign);write(db,PREFIX+'campaign-id:'+campaign['id'],campaign_key(code))
        core['audit'](db,uid,'rewards_campaign_created','promotion',campaign['id'],{'kind':kind,'mode':campaign['mode']})
        db.execute('COMMIT')
    except Exception:db.execute('ROLLBACK');raise
    return campaign_view(campaign)

def claim(db,uid,data,core):
    code=code_value(data.get('code'),core);current_mode=mode(core)
    db.execute('BEGIN IMMEDIATE')
    try:
        lock(db);campaign=check_campaign(db,code,uid,current_mode,'voucher',core)
        claimed=read(db,PREFIX+'claim:'+campaign['id'])
        if claimed and claimed!=uid:fail(core,'This voucher has already been claimed.')
        if not claimed:
            check_uses(db,campaign,uid,core);change_uses(db,campaign['id'],uid,1)
            write(db,PREFIX+'claim:'+campaign['id'],uid)
            make_lot(db,uid,current_mode,'voucher-'+campaign['id'],campaign['amount_micro'],settings(db)['credit_expiry_days'],'active',campaign['code'],core,scope=campaign['scope'])
            entry(db,uid,current_mode,'voucher',campaign['amount_micro'],campaign['code'],core)
            core['audit'](db,uid,'rewards_voucher_claimed','promotion',campaign['id'])
        db.execute('COMMIT')
    except Exception:db.execute('ROLLBACK');raise
    return wallet(db,uid,core)

def route(db,ctx,method,path,data,core):
    if not path.startswith(('/api/rewards','/api/admin/rewards')):return UNHANDLED
    uid=core['require_verified'](ctx)
    if path=='/api/rewards' and method=='GET':return wallet(db,uid,core)
    if path=='/api/rewards/quote' and method=='POST':
        core['check_rate'](db,'rewards_quote',uid,60,300)
        return quote(db,uid,data,core)
    if path=='/api/rewards/vouchers/claim' and method=='POST':
        core['check_rate'](db,'rewards_claim',uid,10,300)
        return claim(db,uid,data,core)
    if path.startswith('/api/admin/rewards'):
        core['require_admin'](ctx)
        if path=='/api/admin/rewards' and method=='GET':return admin_view(db,core)
        if path=='/api/admin/rewards/campaigns' and method=='POST':return create_campaign(db,uid,data,core)
        match=re.fullmatch(r'/api/admin/rewards/campaigns/([A-Za-z0-9_-]+)',path)
        if match and method=='POST':
            if set(data)!={'enabled'} or type(data['enabled']) is not bool:fail(core,'Only campaign availability can be changed. Create a new campaign for new terms.',400)
            db.execute('BEGIN IMMEDIATE')
            try:
                lock(db);key=read(db,PREFIX+'campaign-id:'+match[1]);campaign=read(db,key) if key else None
                if not campaign:fail(core,'Campaign not found.',404)
                campaign['enabled']=data['enabled'];write(db,key,campaign)
                core['audit'](db,uid,'rewards_campaign_toggled','promotion',campaign['id'],data);db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
            return campaign_view(campaign)
        if path=='/api/admin/rewards/settings' and method=='POST':
            if set(data)-set(DEFAULTS):fail(core,'Unknown rewards setting.',400)
            updates={}
            for key,setting in data.items():
                if key in ('enabled','stacking'):
                    if type(setting) is not bool:fail(core,'Check rewards settings.',400)
                elif type(setting) is not int or not (1<=setting<=365 if key=='credit_expiry_days' else 0<=setting<=10000):fail(core,'Check rewards rates or expiry.',400)
                updates[key]=setting
            db.execute('BEGIN IMMEDIATE')
            try:
                lock(db);value={**settings(db),**updates};write(db,PREFIX+'settings',value)
                core['audit'](db,uid,'rewards_settings_updated','promotion','settings',data);db.execute('COMMIT')
            except Exception:db.execute('ROLLBACK');raise
            return value
    return UNHANDLED

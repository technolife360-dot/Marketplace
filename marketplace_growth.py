"""Seller-funded coupons and non-cash loyalty. No payment integration."""
import json
import re
import secrets
from datetime import datetime,timedelta,timezone
import launch_readiness as launch
import marketplace_operations as ops

def campaign(db,code,uid,core,lock=False):
    if not isinstance(code,str) or not re.fullmatch(r'[A-Z0-9]{6,20}',code):raise core['HttpError'](400,'Enter a coupon with 6–20 capital letters or numbers.')
    if lock:db.execute('UPDATE platform_config SET updated_at=updated_at WHERE key=?',('seller_coupon:'+code,))
    value=launch.config(db,'seller_coupon:'+code)
    if not value or not value.get('enabled') or ops.utc(value['expires_at'])<=datetime.now(timezone.utc):raise core['HttpError'](409,'This coupon is unavailable or expired.')
    uses=db.execute("SELECT COUNT(*) n FROM platform_config c JOIN orders o ON o.id=c.value WHERE c.key LIKE ? AND o.status NOT IN ('cancelled','refunded')",('coupon_use:'+code+':%',)).fetchone()['n']
    own=db.execute("SELECT 1 FROM platform_config c JOIN orders o ON o.id=c.value WHERE c.key=? AND o.status NOT IN ('cancelled','refunded')",('coupon_use:'+code+':'+uid,)).fetchone()
    if uses>=value['max_uses'] or own:raise core['HttpError'](409,'The coupon limit has been reached.')
    return value

def discount(db,code,uid,lines,core,lock=False):
    value=campaign(db,code,uid,core,lock)
    matching=[line for line in lines if line['listing_id']==value['listing_id'] and line['seller_id']==value['seller_id']]
    if len(matching)!=1:raise core['HttpError'](409,'This coupon does not match a product in your cart.')
    line=matching[0];original=line['price_minor'];line['price_minor']=max(1,original*(100-value['percent'])//100)
    return (original-line['price_minor'])*line['quantity']

def stats(db,uid):
    own=db.execute("SELECT COUNT(*) n FROM orders WHERE buyer_id=? AND status='completed' AND payment_mode NOT IN ('sandbox','disabled','stripe_test')",(uid,)).fetchone()['n']
    friends=db.execute("SELECT COUNT(DISTINCT o.buyer_id) n FROM orders o JOIN platform_config c ON c.key='referral_attribution:'||o.buyer_id WHERE c.value=? AND o.status='completed' AND o.payment_mode NOT IN ('sandbox','disabled','stripe_test')",(uid,)).fetchone()['n']
    row=db.execute('SELECT settings_json FROM experience_preferences WHERE user_id=?',(uid,)).fetchone();prefs=json.loads(row['settings_json']) if row else {}
    return {'referral_code':prefs.get('referral_code',''),'completed_purchases':own,'qualified_referrals':friends,'loyalty_points':own*10+friends*20,'rules':{'purchase_points':10,'referral_points':20,'cash_value':False,'redeemable':False,'sandbox_excluded':True},'tier':'regular' if own>=10 else 'member'}

def route(db,ctx,method,path,data,core):
    uid=ctx['uid'];error=core['HttpError']
    if path=='/api/loyalty' and method=='GET':core['require_verified'](ctx);return stats(db,uid)
    if path=='/api/referrals/code' and method=='POST':
        core['require_verified'](ctx)
        launch.save_preferences(db,uid,lambda p:p.setdefault('referral_code',secrets.token_hex(10).upper()),core)
        return stats(db,uid)
    if path=='/api/referrals/claim' and method=='POST':
        core['require_verified'](ctx);core['check_rate'](db,'referral_claim',uid,5,3600);code=data.get('code','')
        if not isinstance(code,str) or not re.fullmatch(r'[A-F0-9]{20}',code):raise error(400,'Check the invitation code.')
        owners=[]
        for row in db.execute("SELECT p.user_id,p.settings_json FROM experience_preferences p JOIN users u ON u.id=p.user_id WHERE u.email_verified=1 AND u.suspended=0 AND p.settings_json LIKE ?",('%'+code+'%',)):
            if json.loads(row['settings_json']).get('referral_code')==code:owners.append(row['user_id'])
        if len(owners)!=1 or owners[0]==uid:raise error(400,'Check the invitation code.')
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('UPDATE users SET display_name=display_name WHERE id=?',(uid,))
            if db.execute("SELECT 1 FROM platform_config WHERE key=?",('referral_attribution:'+uid,)).fetchone() or db.execute("SELECT 1 FROM orders WHERE buyer_id=? AND status NOT IN ('cancelled','refunded')",(uid,)).fetchone():raise error(409,'An invitation can be added once, before your first order.')
            db.execute('INSERT INTO platform_config(key,value) VALUES(?,?)',('referral_attribution:'+uid,owners[0]));core['audit'](db,uid,'referral_claimed','user',uid);db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return {'claimed':True,'cash_reward':False}
    if path=='/api/seller/coupons' and method in ('GET','POST'):
        core['require_verified'](ctx);core['seller_ok'](db,uid)
        if method=='GET':return [value for row in db.execute("SELECT value FROM platform_config WHERE key LIKE 'seller_coupon:%'") if (value:=json.loads(row['value'])).get('seller_id')==uid]
        code=data.get('code','');lid=data.get('listing_id');percent=data.get('percent');max_uses=data.get('max_uses');enabled=data.get('enabled',True)
        if not isinstance(lid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',lid) or not isinstance(code,str) or not re.fullmatch(r'[A-Z0-9]{6,20}',code) or type(percent) is not int or not 1<=percent<=50 or type(max_uses) is not int or not 1<=max_uses<=10000 or type(enabled) is not bool:raise error(400,'Check coupon code, percentage (1–50) and limit (1–10000).')
        try:expires=ops.utc(data.get('expires_at',''))
        except (ValueError,TypeError):raise error(400,'Choose a valid expiry date.')
        if not datetime.now(timezone.utc)<expires<=datetime.now(timezone.utc)+timedelta(days=90):raise error(400,'Coupon expiry must be within the next 90 days.')
        db.execute('BEGIN IMMEDIATE')
        try:
            if not db.execute('UPDATE listings SET updated_at=updated_at WHERE id=? AND seller_id=?',(lid,uid)).rowcount:raise error(404,'Listing not found.')
            prior=launch.config(db,'seller_coupon:'+code)
            if prior and (prior['seller_id']!=uid or prior['listing_id']!=lid):raise error(409,'That coupon code is already in use.')
            value={'code':code,'seller_id':uid,'listing_id':lid,'percent':percent,'max_uses':max_uses,'expires_at':ops.iso(expires),'enabled':enabled};launch.put_config(db,'seller_coupon:'+code,value)
            core['audit'](db,uid,'seller_coupon_updated','listing',lid,{'code':code,'percent':percent,'enabled':enabled});db.execute('COMMIT')
        except Exception:db.execute('ROLLBACK');raise
        return value
    if path=='/api/cart/coupon' and method=='POST':
        core['require_verified'](ctx)
        lines=[dict(r) for r in db.execute('SELECT c.listing_id,c.quantity,l.price_minor,l.seller_id,l.currency FROM carts c JOIN listings l ON l.id=c.listing_id WHERE c.user_id=?',(uid,))]
        for line in lines:line['price_minor']=launch.unit_price(db,line['listing_id'],line['price_minor'],line['quantity'])
        if len({line['currency'] for line in lines})!=1:raise error(400,'Choose products in one currency.')
        saved=discount(db,data.get('code'),uid,lines,core);subtotal=sum(line['price_minor']*line['quantity'] for line in lines)
        row=db.execute("SELECT value FROM platform_config WHERE key='commission_bps'").fetchone();fee=subtotal*int(row['value'])//10000 if row else 0
        return {'code':data['code'],'currency':lines[0]['currency'],'discount_minor':saved,'subtotal_minor':subtotal,'commission_minor':fee,'total_minor':subtotal+fee,'notice':'Revalidated at checkout; no funds have been taken.'}
    return launch.UNHANDLED

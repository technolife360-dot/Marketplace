"""Free daily promotional spins; awards, stock and credits settle atomically."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import os
import re
import secrets
import catalogue_experience
import rewards_engine as rewards

UNHANDLED = object()
PREFIX = 'spinwin:'
TOTAL = 100000
ZONE = ZoneInfo('Asia/Kuala_Lumpur')
PRIZES = (
    {'id':'iphone','name':'iPhone 18 Pro','kind':'physical','weight':1},
    {'id':'ps5','name':'PlayStation 5','kind':'physical','weight':2},
    {'id':'tv','name':'Smart TV','kind':'physical','weight':2},
    *({'id':f'rm{minor}','name':f'RM{minor/100:g}','kind':'voucher','minor':minor,'weight':weight}
      for minor,weight in ((10,6000),(20,2000),(50,1000),(100,700),(200,250),(500,50))),
    {'id':'none','name':'No prize this time','kind':'none','weight':89995},
)


def now():
    return datetime.now(timezone.utc)


def key(current_mode, kind):
    return PREFIX + current_mode + ':' + kind


def campaign_mode(core):
    environment = os.environ.get('VERCEL_ENV')
    if environment == 'production' and core['MODE'] == 'production':
        return 'real'
    if environment == 'preview':
        return 'test'
    return rewards.mode(core)


def settings(db, current_mode):
    return {**{'enabled':False,'budget_minor':0,'stock':{'iphone':0,'ps5':0,'tv':0},'version':0},
            **rewards.read(db,key(current_mode,'settings'),{})}


def counters(db, current_mode):
    return {**{'spent_minor':0,'awarded':{'iphone':0,'ps5':0,'tv':0}},
            **rewards.read(db,key(current_mode,'counters'),{})}


def effective_prizes(config, totals):
    result=[]; missing=0
    for source in PRIZES:
        prize=dict(source)
        available=(prize['kind']=='none' or
                   (prize['kind']=='physical' and config['stock'][prize['id']]>totals['awarded'][prize['id']]) or
                   (prize['kind']=='voucher' and prize['minor']<=config['budget_minor']-totals['spent_minor']))
        if available:result.append(prize)
        else:missing+=prize['weight']
    result[-1]['weight']+=missing
    return result


def public_record(record):
    return {k:record[k] for k in ('id','day','created_at','prize_id','prize_name','kind','minor','status','test_only','settings_version')}


def welcome_prize(db, daily_prefix, prizes):
    voucher=next((prize for prize in prizes if prize['id']=='rm100'),None)
    if voucher and not db.execute(
        'SELECT 1 FROM platform_config WHERE key>=? AND key<? LIMIT 1',
        (daily_prefix,daily_prefix+'~'),
    ).fetchone():
        return voucher
    return None


def state(db, uid, core):
    current_mode=campaign_mode(core); config=settings(db,current_mode); local=now().astimezone(ZONE)
    day=local.date().isoformat()
    record=rewards.read(db,key(current_mode,'daily:'+rewards.user_hash(uid)+':'+day))
    history=rewards.rows(db,key(current_mode,'daily:'+rewards.user_hash(uid)+':'))
    prizes=effective_prizes(config,counters(db,current_mode))
    enabled=config['enabled'] and len(prizes)>1
    return {'enabled':enabled,'test_only':current_mode=='test','timezone':str(ZONE),
            'day':day,'next_reset':datetime.combine(local.date()+timedelta(days=1),datetime.min.time(),ZONE).isoformat(),
            'can_spin':enabled and record is None,'today':public_record(record) if record else None,
            'prizes':prizes,
            'history':[public_record(r) for r in sorted(history,key=lambda r:r['created_at'],reverse=True)[:30]],
            'redemption_bps':rewards.settings(db)['redemption_bps'],'credit_expiry_days':rewards.settings(db)['credit_expiry_days']}


def spin(db, uid, data, core):
    if data:rewards.fail(core,'The server decides your prize. No spin parameters are accepted.',400)
    current_mode=campaign_mode(core)
    daily_prefix=key(current_mode,'daily:'+rewards.user_hash(uid)+':')
    day=now().astimezone(ZONE).date().isoformat()
    prior=rewards.read(db,daily_prefix+day)
    if prior:return public_record(prior)
    # Obtain FX before taking the database lock. Failures never consume a spin.
    fx=rewards.rates(core)
    email_notifications=[]
    db.execute('BEGIN IMMEDIATE')
    try:
        rewards.lock(db)
        local=now().astimezone(ZONE); day=local.date().isoformat()
        daily_key=daily_prefix+day
        prior=rewards.read(db,daily_key)
        if prior:
            db.execute('COMMIT');return public_record(prior)
        config=settings(db,current_mode); totals=counters(db,current_mode)
        prizes=effective_prizes(config,totals)
        if not config['enabled'] or len(prizes)==1:
            rewards.fail(core,'No Spin & Win prizes are available right now.')
        prize=welcome_prize(db,daily_prefix,prizes)
        if prize is None:
            ticket=secrets.randbelow(TOTAL)
            for prize in prizes:
                ticket-=prize['weight']
                if ticket<0:break
        identifier=core['ident']()
        record={'id':identifier,'uid':uid,'day':day,'created_at':now().isoformat(),
                'prize_id':prize['id'],'prize_name':prize['name'],'kind':prize['kind'],
                'minor':prize.get('minor',0),'status':'new' if prize['kind']=='physical' else 'credited' if prize['kind']=='voucher' else 'no_prize',
                'test_only':current_mode=='test','settings_version':config['version']}
        if prize['kind']=='voucher':
            amount=rewards.to_micro(prize['minor'],'MYR',fx['rates'])
            if amount<=0:rewards.fail(core,'Bonus conversion is unavailable.',503)
            deferred = current_mode == 'real' and core['MODE'] == 'production'
            days = None if deferred else rewards.settings(db)['credit_expiry_days']
            rewards.make_lot(db,uid,current_mode,'spin-'+identifier,amount,days,'active',
                             'Spin & Win '+identifier,core,scope='topup',
                             deferred_myr_minor=prize['minor'] if deferred else None)
            if deferred:
                record['status']='saved_for_live_topup'
            rewards.entry(db,uid,current_mode,'spin_win',amount,identifier,core)
            totals['spent_minor']+=prize['minor']
        if prize['kind']=='physical':
            totals['awarded'][prize['id']]+=1
            record['status_history']=[{'status':'new','at':record['created_at'],'actor_id':uid}]
            rewards.write(db,key(current_mode,'winner:'+identifier),record)
            for admin in db.execute('SELECT a.user_id FROM admin_accounts a JOIN users u ON u.id=a.user_id WHERE u.suspended=0').fetchall():
                notification_id=core['notify'](db,admin['user_id'],
                    'spin_win' if record['test_only'] else 'spin_win_admin',
                    ('TEST · ' if record['test_only'] else '')+'Spin & Win winner',
                    f"{prize['name']} · award: {identifier}",'/#admin-spin-win')
                if not record['test_only'] and notification_id:
                    email_notifications.append(notification_id)
            core['notify'](db,uid,'spin_win','Spin & Win',prize['name']+' · '+identifier,'/#spin-win')
        rewards.write(db,key(current_mode,'counters'),totals)
        rewards.write(db,daily_key,record)
        core['audit'](db,uid,'spin_win_result','spin_win',identifier,{'prize':prize['id'],'mode':current_mode})
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK');raise
    for notification_id in email_notifications:
        try:
            catalogue_experience.dispatch_emails(db,core,notification_id=notification_id)
        except Exception as exc:
            print('Spin & Win email dispatch failed:',type(exc).__name__)
    return public_record(record)


def admin_view(db, core, page=1):
    current_mode=campaign_mode(core)
    winners=sorted(rewards.rows(db,key(current_mode,'winner:')),key=lambda r:r['created_at'],reverse=True)
    selected=[]
    for record in winners[(page-1)*50:page*50]:
        user=db.execute('SELECT id,display_name,email FROM users WHERE id=?',(record['uid'],)).fetchone()
        selected.append({**record,'user':dict(user) if user else {'id':record['uid'],'display_name':'Deleted user','email':''}})
    return {'settings':settings(db,current_mode),'counters':counters(db,current_mode),'test_only':current_mode=='test',
            'prizes':list(PRIZES),'winners':selected,'page':page,'total':len(winners)}


def save_settings(db,uid,data,core):
    if set(data)!={'enabled','budget_minor','stock'} or type(data['enabled']) is not bool:
        rewards.fail(core,'Provide campaign availability, voucher budget and physical stock.',400)
    if type(data['budget_minor']) is not int or not 0<=data['budget_minor']<=10000000:
        rewards.fail(core,'Budget must be a valid MYR amount.',400)
    stock=data['stock']
    if not isinstance(stock,dict) or set(stock)!={'iphone','ps5','tv'} or any(type(v) is not int or not 0<=v<=1000 for v in stock.values()):
        rewards.fail(core,'Enter valid total prize stock.',400)
    current_mode=campaign_mode(core)
    db.execute('BEGIN IMMEDIATE')
    try:
        rewards.lock(db); totals=counters(db,current_mode)
        if data['budget_minor']<totals['spent_minor'] or any(stock[k]<totals['awarded'][k] for k in stock):
            rewards.fail(core,'Limits cannot be lower than awards already issued.')
        if data['enabled'] and len(effective_prizes(data,totals))==1:
            rewards.fail(core,'Add an available prize before enabling the campaign.')
        value={**data,'version':settings(db,current_mode)['version']+1}
        rewards.write(db,key(current_mode,'settings'),value)
        core['audit'](db,uid,'spin_win_settings','spin_win',current_mode,value)
        db.execute('COMMIT')
    except Exception:db.execute('ROLLBACK');raise
    return value


def update_winner(db,uid,identifier,data,core):
    states=('new','contacted','shipped','delivered')
    if set(data)!={'status'} or data['status'] not in states:rewards.fail(core,'Choose a valid fulfilment status.',400)
    current_mode=campaign_mode(core)
    db.execute('BEGIN IMMEDIATE')
    try:
        rewards.lock(db); winner_key=key(current_mode,'winner:'+identifier); record=rewards.read(db,winner_key)
        if not record:rewards.fail(core,'Winner not found.',404)
        if states.index(data['status'])<states.index(record['status']):rewards.fail(core,'Fulfilment status cannot move backwards.')
        if data['status']!=record['status']:
            record['status']=data['status']
            record['status_history'].append({'status':data['status'],'at':now().isoformat(),'actor_id':uid})
            rewards.write(db,winner_key,record)
            rewards.write(db,key(current_mode,'daily:'+rewards.user_hash(record['uid'])+':'+record['day']),record)
            core['audit'](db,uid,'spin_win_fulfilment','spin_win',identifier,data)
            core['notify'](db,record['uid'],'spin_win','Prize update',record['prize_name']+' · '+record['status'],'/#spin-win')
        db.execute('COMMIT')
    except Exception:db.execute('ROLLBACK');raise
    return public_record(record)


def route(db,ctx,method,path,qs,data,core):
    if not (path=='/api/spin-win' or path.startswith('/api/spin-win/') or path=='/api/admin/spin-win' or path.startswith('/api/admin/spin-win/')):return UNHANDLED
    if path=='/api/spin-win/preview' and method=='GET':
        current_mode = campaign_mode(core)
        config = settings(db, current_mode)
        prizes = effective_prizes(config, counters(db, current_mode)) if config['enabled'] else []
        return {
            'enabled': config['enabled'] and len(prizes)>1,
            'test_only': current_mode=='test',
            'prizes': [{k: prize[k] for k in ('id', 'name', 'kind')} for prize in prizes],
        }
    uid=core['require_verified'](ctx)
    if path=='/api/spin-win' and method=='GET':return state(db,uid,core)
    if path=='/api/spin-win/spin' and method=='POST':
        core['check_rate'](db,'daily_spin',uid,20,300)
        return spin(db,uid,data,core)
    if path.startswith('/api/admin/spin-win'):
        core['require_admin'](ctx)
        if path=='/api/admin/spin-win' and method=='GET':
            try:page=int(qs.get('page',['1'])[0])
            except (ValueError,TypeError):rewards.fail(core,'Invalid page.',400)
            if not 1<=page<=100000:rewards.fail(core,'Invalid page.',400)
            return admin_view(db,core,page)
        if path=='/api/admin/spin-win/settings' and method=='POST':return save_settings(db,uid,data,core)
        match=re.fullmatch(r'/api/admin/spin-win/winners/([A-Za-z0-9_-]+)',path)
        if match and method=='POST':return update_winner(db,uid,match[1],data,core)
    return UNHANDLED

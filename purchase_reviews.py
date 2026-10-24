"""Purchase-only feedback. Public scores exclude sandbox/unpaid purchases."""
import re
import json

UNHANDLED = object()
TABLES = ('topup_reviews', 'purchase_review_reports', 'purchase_review_helpful')
SCHEMA = (
    """CREATE TABLE IF NOT EXISTS topup_reviews (
        id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE REFERENCES topup_orders(id) ON DELETE CASCADE,
        reviewer_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5), body TEXT NOT NULL, hidden INTEGER NOT NULL DEFAULT 0 CHECK(hidden IN (0,1)),
        reply TEXT NOT NULL DEFAULT '', replied_by TEXT REFERENCES users(id) ON DELETE SET NULL, replied_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE IF NOT EXISTS purchase_review_reports (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('listing','topup')),
        review_id TEXT NOT NULL, reporter_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','dismissed','removed')),
        resolution TEXT NOT NULL DEFAULT '', resolved_by TEXT REFERENCES users(id) ON DELETE SET NULL, resolved_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(kind,review_id,reporter_id))""",
    """CREATE TABLE IF NOT EXISTS purchase_review_helpful (
        kind TEXT NOT NULL CHECK(kind IN ('listing','topup')), review_id TEXT NOT NULL,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(kind,review_id,user_id))""",
    'CREATE INDEX IF NOT EXISTS purchase_review_reports_status ON purchase_review_reports(status,created_at)',
    'CREATE INDEX IF NOT EXISTS review_order_items_listing ON order_items(listing_id,order_id)',
    'CREATE INDEX IF NOT EXISTS review_topup_orders_package ON topup_orders(package_id,status)',
)


def migrate(db, postgres=False):
    for sql in SCHEMA:
        db.execute(sql)
    if postgres:
        db.execute('ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS updated_at TEXT')
        db.execute('ALTER TABLE public.reviews ADD COLUMN IF NOT EXISTS hidden INTEGER NOT NULL DEFAULT 0')
        for table in TABLES:
            db.execute(f'ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY')
            db.execute(f'REVOKE ALL ON public.{table} FROM PUBLIC, anon, authenticated')
    elif 'updated_at' not in {r['name'] for r in db.execute('PRAGMA table_info(reviews)')}:
        db.execute('ALTER TABLE reviews ADD COLUMN updated_at TEXT')
    if not postgres and 'hidden' not in {r['name'] for r in db.execute('PRAGMA table_info(reviews)')}:
        db.execute('ALTER TABLE reviews ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0')
    for table in ('reviews','topup_reviews'):
        if postgres:db.execute(f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS language TEXT NOT NULL DEFAULT ''")
        elif 'language' not in {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}:
            db.execute(f"ALTER TABLE {table} ADD COLUMN language TEXT NOT NULL DEFAULT ''")
    db.execute('CREATE OR REPLACE VIEW public.visible_reviews WITH (security_invoker=true) AS SELECT * FROM public.reviews WHERE hidden=0' if postgres else 'CREATE VIEW IF NOT EXISTS visible_reviews AS SELECT * FROM reviews WHERE hidden=0')
    if postgres:db.execute('REVOKE ALL ON public.visible_reviews FROM PUBLIC, anon, authenticated')


MARKET_REAL = "o.status='completed' AND o.payment_mode NOT IN ('sandbox','disabled','stripe_test')"
# Avoid a literal percent wildcard: Psycopg parses it as a parameter marker
# when the shared database wrapper passes a parameter sequence.
TOPUP_REAL = "o.status='completed' AND o.completed_at IS NOT NULL AND o.payment_reference<>'' AND lower(substr(o.payment_reference,1,7))<>'sandbox' AND lower(substr(o.payment_reference,1,12))<>'stripe_test_'"


def add_listing_scores(db, items):
    ids=list(dict.fromkeys(x['id'] for x in items))
    if not ids:
        return
    marks=','.join('?' for _ in ids)
    rows=db.execute(f'''SELECT i.listing_id,COUNT(*) n,AVG(r.rating) rating
        FROM reviews r JOIN order_items i ON i.id=r.order_item_id JOIN orders o ON o.id=i.order_id
        WHERE r.hidden=0 AND {MARKET_REAL} AND i.listing_id IN ({marks}) GROUP BY i.listing_id''',tuple(ids)).fetchall()
    scores={r['listing_id']:r for r in rows}
    for item in items:
        score=scores.get(item['id'])
        item['product_review_count']=score['n'] if score else 0
        item['product_rating']=float(score['rating']) if score else None
    add_seller_card_stats(db, items)


def add_seller_card_stats(db, items):
    """Batch public seller reputation and units sold; never count test payments."""
    sellers=list(dict.fromkeys(item['seller_id'] for item in items if item.get('seller_id')))
    if not sellers:
        return
    marks=','.join('?' for _ in sellers)
    ratings={row['seller_id']:row for row in db.execute(f'''SELECT i.seller_id,COUNT(*) n,AVG(r.rating) rating
        FROM reviews r JOIN order_items i ON i.id=r.order_item_id JOIN orders o ON o.id=i.order_id
        WHERE r.hidden=0 AND {MARKET_REAL} AND i.seller_id IN ({marks}) GROUP BY i.seller_id''',tuple(sellers))}
    sales={(row['seller_id'],row['product_type']):int(row['quantity']) for row in db.execute(f'''
        SELECT i.seller_id,l.product_type,SUM(i.quantity) quantity FROM order_items i
        JOIN orders o ON o.id=i.order_id JOIN listings l ON l.id=i.listing_id
        WHERE {MARKET_REAL} AND i.seller_id IN ({marks}) GROUP BY i.seller_id,l.product_type''',tuple(sellers))}
    for item in items:
        score=ratings.get(item.get('seller_id'))
        item['seller_card_review_count']=int(score['n']) if score else 0
        item['seller_card_rating']=float(score['rating']) if score else None
        item['seller_sales_count']=sales.get((item.get('seller_id'),item.get('product_type')),0)


def topup_scores(db):
    return {r['game_slug']:{'count':r['n'],'rating':float(r['rating'])} for r in db.execute(f'''
        SELECT p.game_slug,COUNT(*) n,AVG(r.rating) rating FROM topup_reviews r
        JOIN topup_orders o ON o.id=r.order_id JOIN topup_packages p ON p.id=o.package_id
        WHERE r.hidden=0 AND {TOPUP_REAL} GROUP BY p.game_slug''')}


def feedback(db,kind,rid):
    if kind=='listing':
        return db.execute('''SELECT r.*,o.buyer_id,o.status,i.listing_id,o.payment_mode
            FROM reviews r JOIN order_items i ON i.id=r.order_item_id JOIN orders o ON o.id=i.order_id WHERE r.id=?''',(rid,)).fetchone()
    return db.execute('''SELECT r.*,o.buyer_id,o.status,o.payment_reference,o.completed_at,p.game_slug
        FROM topup_reviews r JOIN topup_orders o ON o.id=r.order_id JOIN topup_packages p ON p.id=o.package_id WHERE r.id=?''',(rid,)).fetchone()


def route(db,ctx,method,path,qs,data,core):
    uid=ctx['uid']; error=core['HttpError']; text=core['clean_text']
    if path=='/api/review-hub/home' and method=='GET':
        sources=[
            (f"FROM reviews r JOIN order_items i ON i.id=r.order_item_id JOIN orders o ON o.id=i.order_id JOIN users u ON u.id=r.reviewer_id LEFT JOIN platform_config av ON av.key='public_avatar:'||u.id JOIN listings l ON l.id=i.listing_id JOIN games g ON g.id=l.game_id WHERE r.hidden=0 AND {MARKET_REAL}", 'i.title', "'/listing/'||i.listing_id", 'g.slug'),
            (f"FROM topup_reviews r JOIN topup_orders o ON o.id=r.order_id JOIN topup_packages p ON p.id=o.package_id JOIN users u ON u.id=r.reviewer_id LEFT JOIN platform_config av ON av.key='public_avatar:'||u.id WHERE r.hidden=0 AND {TOPUP_REAL}", 'p.game_name', "'/top-up/'||p.game_slug", 'p.game_slug')]
        items=[];count=0;total=0
        for joins,label,link,game in sources:
            score=db.execute(f'SELECT COUNT(*) n,COALESCE(SUM(r.rating),0) total {joins}').fetchone()
            count+=score['n'];total+=score['total']
            items.extend({**dict(r),'test_only':False} for r in db.execute(f'SELECT r.rating,r.body,r.created_at,u.display_name reviewer_name,av.value avatar_url,{label} product_title,{link} product_url,{game} game_slug {joins} ORDER BY r.created_at DESC,r.id DESC LIMIT 6'))
        if core['MODE']!='production':
            # Older test feedback stays private. A buyer must explicitly opt in.
            public_json="COALESCE(c.value::jsonb->>'public','false')='true'" if core['DATABASE_URL'] else "json_extract(c.value,'$.public')=1"
            for row in db.execute(f"""SELECT c.value,o.created_at,u.display_name reviewer_name,av.value avatar_url,
                (SELECT i.title FROM order_items i WHERE i.order_id=o.id ORDER BY i.id LIMIT 1) product_title,
                (SELECT g.slug FROM order_items i JOIN listings l ON l.id=i.listing_id JOIN games g ON g.id=l.game_id WHERE i.order_id=o.id ORDER BY i.id LIMIT 1) game_slug
                FROM orders o JOIN payments p ON p.order_id=o.id JOIN users u ON u.id=o.buyer_id LEFT JOIN platform_config av ON av.key='public_avatar:'||u.id
                JOIN platform_config c ON c.key='stripe_test:review:'||o.id
                WHERE o.status='completed' AND o.payment_mode='stripe_test' AND p.provider='stripe_test'
                AND p.status='succeeded' AND {public_json} ORDER BY c.updated_at DESC,o.id DESC LIMIT 6"""):
                review=json.loads(row['value'])
                if review.get('public') is not True:continue
                items.append({'rating':review['rating'],'body':review['body'],'created_at':review.get('updated_at') or row['created_at'],'reviewer_name':row['reviewer_name'],'avatar_url':row['avatar_url'],'product_title':row['product_title'],'product_url':None,'game_slug':row['game_slug'],'test_only':True})
        for item in items:
            game=core['seller_catalog'].find(item.pop('game_slug', ''))
            item['game_name']=game['name'] if game else ''
            item['game_image_url']=core['seller_catalog'].image_url(game['id']) if game else ''
            name=(item['reviewer_name'] or '').strip()
            item['reviewer_name']=name[0]+'***'+(name[-1] if len(name)>1 else '') if name else '***'
        return {'count':count,'rating':round(total/count,1) if count else None,'items':sorted(items,key=lambda r:r['created_at'],reverse=True)[:6]}
    def validate():
        core['require_verified'](ctx)
        core['check_rate'](db,'purchase_review',uid,30,3600)
        rating=data.get('rating')
        if isinstance(rating,bool) or not isinstance(rating,int) or not 1<=rating<=5:
            raise error(400,'Baho 1 dan 5 gacha bo‘lsin.')
        return rating,text(data.get('body'),'Sharh',5,1500)
    if path=='/api/review-hub/mine' and method=='GET':
        core['require_user'](ctx)
        listings=[dict(r) for r in db.execute("""SELECT 'listing' kind,i.id purchase_id,l.id target,l.title label,o.reference,
            r.id review_id,r.rating,r.body,r.language,COALESCE(r.hidden,0) hidden FROM order_items i JOIN orders o ON o.id=i.order_id
            JOIN listings l ON l.id=i.listing_id LEFT JOIN reviews r ON r.order_item_id=i.id
            WHERE o.buyer_id=? AND o.status='completed' ORDER BY o.created_at DESC LIMIT 100""",(uid,))]
        topups=[dict(r) for r in db.execute(f"""SELECT 'topup' kind,o.id purchase_id,p.game_slug target,p.game_name||' · '||p.amount||' '||p.currency label,
            o.reference,r.id review_id,r.rating,r.body,r.language,COALESCE(r.hidden,0) hidden FROM topup_orders o JOIN topup_packages p ON p.id=o.package_id
            LEFT JOIN topup_reviews r ON r.order_id=o.id WHERE o.buyer_id=? AND {TOPUP_REAL} ORDER BY o.created_at DESC LIMIT 100""",(uid,))]
        return listings+topups
    m=re.fullmatch(r'/api/review-hub/(listing|topup)/([A-Za-z0-9_-]+)',path)
    if m and method=='GET':
        kind,target=m.groups()
        try: page=max(1,min(10000,int(qs.get('page',['1'])[0])))
        except (TypeError,ValueError):raise error(400,'Sahifa noto‘g‘ri.')
        if kind=='listing':
            listing=core['listing_detail'](db,target,uid)
            if not listing or listing['status'] not in core['PUBLIC_LISTING_STATES'] or not core['listing_allowed_for_production'](db,listing['game_id'],listing['product_type']):raise error(404,'E’lon topilmadi.')
            joins="FROM reviews r JOIN order_items i ON i.id=r.order_item_id JOIN orders o ON o.id=i.order_id JOIN users u ON u.id=r.reviewer_id LEFT JOIN platform_config av ON av.key='public_avatar:'||u.id LEFT JOIN review_replies rr ON rr.review_id=r.id"
            where=f'i.listing_id=? AND r.hidden=0 AND {MARKET_REAL}'
            fields='i.title package_name,r.language,u.country,r.id,r.rating,r.body,r.created_at,r.updated_at,u.display_name reviewer_name,av.value avatar_url,r.reviewer_id,rr.body reply,rr.updated_at replied_at,r.seller_id'
            eligible=[dict(r) for r in db.execute("""SELECT i.id purchase_id,o.reference,l.title label,r.id review_id,r.rating,r.body,r.language,COALESCE(r.hidden,0) hidden
                FROM order_items i JOIN orders o ON o.id=i.order_id JOIN listings l ON l.id=i.listing_id
                LEFT JOIN reviews r ON r.order_item_id=i.id WHERE o.buyer_id=? AND o.status='completed' AND i.listing_id=? ORDER BY o.created_at DESC LIMIT 50""",(uid or '',target))]
        else:
            if not db.execute('SELECT 1 FROM topup_packages WHERE game_slug=? AND enabled=1',(target,)).fetchone():raise error(404,'O‘yin topilmadi.')
            joins="FROM topup_reviews r JOIN topup_orders o ON o.id=r.order_id JOIN topup_packages p ON p.id=o.package_id JOIN users u ON u.id=r.reviewer_id LEFT JOIN platform_config av ON av.key='public_avatar:'||u.id"
            where=f'p.game_slug=? AND r.hidden=0 AND {TOPUP_REAL}'
            fields="p.game_slug,p.url_slug,r.language,u.country,r.id,r.rating,r.body,r.created_at,r.updated_at,u.display_name reviewer_name,av.value avatar_url,r.reviewer_id,r.reply,r.replied_at,p.game_name package_name,p.amount,p.currency"
            eligible=[dict(r) for r in db.execute(f'''SELECT o.id purchase_id,o.reference,p.game_name label,p.amount,p.currency,r.id review_id,r.rating,r.body,r.language,COALESCE(r.hidden,0) hidden
                FROM topup_orders o JOIN topup_packages p ON p.id=o.package_id LEFT JOIN topup_reviews r ON r.order_id=o.id
                WHERE o.buyer_id=? AND p.game_slug=? AND {TOPUP_REAL} ORDER BY o.created_at DESC LIMIT 50''',(uid or '',target))]
        score=db.execute(f'SELECT COUNT(*) n,AVG(r.rating) rating {joins} WHERE {where}',(target,)).fetchone()
        language=qs.get('language',[''])[0]
        if language not in ('','en','uz','ru'):raise error(400,'Til noto‘g‘ri.')
        args=[target]
        if language:where+=' AND r.language=?';args.append(language)
        filtered=db.execute(f'SELECT COUNT(*) n {joins} WHERE {where}',tuple(args)).fetchone()['n']
        rows=[dict(r) for r in db.execute(f'SELECT {fields} {joins} WHERE {where} ORDER BY r.created_at DESC,r.id DESC LIMIT 10 OFFSET ?',(*args,(page-1)*10))]
        for row in rows:
            row['can_edit']=row.pop('reviewer_id')==uid
            seller_id=row.pop('seller_id',None)
            row['can_reply']=bool(uid and (seller_id==uid if kind=='listing' else core['is_admin'](db,uid)))
            row['can_report']=bool(uid and not row['can_edit'])
            row['verified_purchase']=True
            name=(row.get('reviewer_name') or '').strip()
            row['reviewer_name']=(name[0]+'***'+(name[-1] if len(name)>1 else '')) if name else '***'
            country=row.pop('country','') or ''
            row['country_code']=country if re.fullmatch('[A-Z]{2}',country) else ''
            votes=db.execute('SELECT COUNT(*) n FROM purchase_review_helpful WHERE kind=? AND review_id=?',(kind,row['id'])).fetchone()['n']
            row['helpful_count']=votes
            row['helpful']=bool(uid and db.execute('SELECT 1 FROM purchase_review_helpful WHERE kind=? AND review_id=? AND user_id=?',(kind,row['id'],uid)).fetchone())
            if kind=='topup':
                meta=core['topup_package_metadata'](row)
                split={325:'300 + 25',660:'600 + 60',1800:'1500 + 300',3850:'3000 + 850',8100:'6000 + 2100'}.get(row['amount']) if row['game_slug']=='pubg-mobile' and row['currency']=='UC' else None
                row['package_name']=split+' UC' if split else meta['product_name']
                row.pop('url_slug',None);row.pop('game_slug',None)
        return {'items':rows,'count':score['n'],'rating':float(score['rating']) if score['n'] else None,'page':page,'filtered_count':filtered,'has_more':page*10<filtered,'eligible':eligible,'language':language}
    def review_language():
        language=data.get('language') or (ctx.get('user') or {}).get('language','en')
        if language not in ('en','uz','ru'):raise error(400,'Til noto‘g‘ri.')
        return language
    if path=='/api/reviews' and method=='POST':
        rating,body=validate();iid=text(data.get('item_id'),'Buyurtma mahsuloti',1,100)
        row=db.execute('SELECT i.seller_id,o.buyer_id,o.status FROM order_items i JOIN orders o ON o.id=i.order_id WHERE i.id=?',(iid,)).fetchone()
        if not row or row['buyer_id']!=uid or row['status']!='completed' or row['seller_id']==uid:raise error(403,'Sharh faqat tugallangan xarid uchun mumkin.')
        rid=core['ident']();result=db.execute('INSERT INTO reviews(id,order_item_id,reviewer_id,seller_id,rating,body,language) VALUES(?,?,?,?,?,?,?) ON CONFLICT(order_item_id) DO NOTHING',(rid,iid,uid,row['seller_id'],rating,body,review_language()))
        if result.rowcount!=1:raise error(409,'Bu xarid uchun sharh yozilgan. Uni tahrirlashingiz mumkin.')
        return 201,{'id':rid}
    if path=='/api/top-up/reviews' and method=='POST':
        rating,body=validate();oid=text(data.get('order_id'),'Buyurtma',1,100)
        order=db.execute(f'SELECT o.id FROM topup_orders o WHERE o.id=? AND o.buyer_id=? AND {TOPUP_REAL}',(oid,uid)).fetchone()
        if not order:raise error(403,'Sharh faqat to‘langan va yetkazilgan xarid uchun mumkin.')
        rid=core['ident']();result=db.execute('INSERT INTO topup_reviews(id,order_id,reviewer_id,rating,body,language) VALUES(?,?,?,?,?,?) ON CONFLICT(order_id) DO NOTHING',(rid,oid,uid,rating,body,review_language()))
        if result.rowcount!=1:raise error(409,'Bu xarid uchun sharh yozilgan. Uni tahrirlashingiz mumkin.')
        return 201,{'id':rid}
    m=re.fullmatch(r'/api/(reviews|top-up/reviews)/([A-Za-z0-9_-]+)(/report|/reply|/helpful)?',path)
    if m:
        group,rid,action=m.groups();kind='listing' if group=='reviews' else 'topup'
        if method=='PATCH' and not action:
            rating,body=validate();row=feedback(db,kind,rid)
            if not row or row['reviewer_id']!=uid:raise error(404,'Sharh topilmadi.')
            if row['hidden'] or row['status']!='completed':raise error(409,'Xarid hali yakunlanmagan.')
            table='reviews' if kind=='listing' else 'topup_reviews'
            db.execute(f'UPDATE {table} SET rating=?,body=?,language=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND reviewer_id=?',(rating,body,review_language(),rid,uid))
            return {'ok':True}
        if method in ('POST','DELETE') and action=='/helpful':
            core['require_verified'](ctx);core['check_rate'](db,'review_helpful',uid,60,3600)
            row=feedback(db,kind,rid)
            if not row or row['hidden']:raise error(404,'Sharh topilmadi.')
            if row['reviewer_id']==uid:raise error(400,'O‘z sharhingizga ovoz bera olmaysiz.')
            if method=='POST':db.execute('INSERT INTO purchase_review_helpful(kind,review_id,user_id) VALUES(?,?,?) ON CONFLICT(kind,review_id,user_id) DO NOTHING',(kind,rid,uid))
            else:db.execute('DELETE FROM purchase_review_helpful WHERE kind=? AND review_id=? AND user_id=?',(kind,rid,uid))
            return {'helpful':method=='POST','count':db.execute('SELECT COUNT(*) n FROM purchase_review_helpful WHERE kind=? AND review_id=?',(kind,rid)).fetchone()['n']}
        if method=='POST' and action=='/report':
            core['require_verified'](ctx);core['check_rate'](db,'report_review',uid,10,3600)
            row=feedback(db,kind,rid)
            if not row:raise error(404,'Sharh topilmadi.')
            if row['reviewer_id']==uid:raise error(400,'O‘z sharhingizni tahrirlang.')
            reason=text(data.get('reason'),'Sabab',5,1000)
            db.execute('INSERT INTO purchase_review_reports(id,kind,review_id,reporter_id,reason) VALUES(?,?,?,?,?) ON CONFLICT(kind,review_id,reporter_id) DO NOTHING',(core['ident'](),kind,rid,uid,reason))
            return {'ok':True}
        if method=='POST' and action=='/reply' and kind=='topup':
            aid=core['require_admin'](ctx);core['check_rate'](db,'review_reply',uid,30,3600)
            review=feedback(db,kind,rid)
            if not review or review['hidden']:raise error(404,'Sharh topilmadi.')
            body=text(data.get('body'),'Javob',2,1500)
            db.execute('UPDATE topup_reviews SET reply=?,replied_by=?,replied_at=CURRENT_TIMESTAMP WHERE id=?',(body,aid,rid))
            return {'ok':True}
    if path=='/api/admin/review-reports' and method=='GET':
        core['require_admin'](ctx)
        rows=[dict(r) for r in db.execute("SELECT r.*,u.display_name reporter_name FROM purchase_review_reports r JOIN users u ON u.id=r.reporter_id WHERE r.status='open' ORDER BY r.created_at LIMIT 100")]
        for row in rows:
            review=feedback(db,row['kind'],row['review_id']);row['review']=dict(review) if review else None
        return rows
    m=re.fullmatch(r'/api/admin/review-reports/([A-Za-z0-9_-]+)',path)
    if m and method=='POST':
        aid=core['require_admin'](ctx);action=data.get('action');note=text(data.get('note'),'Moderator izohi',5,1000)
        if action not in ('dismiss','remove'):raise error(400,'Amal noto‘g‘ri.')
        row=db.execute("SELECT * FROM purchase_review_reports WHERE id=? AND status='open'",(m.group(1),)).fetchone()
        if not row:raise error(404,'Shikoyat topilmadi.')
        if action=='remove':
            table='reviews' if row['kind']=='listing' else 'topup_reviews'
            db.execute(f'UPDATE {table} SET hidden=1 WHERE id=?',(row['review_id'],))
        db.execute("UPDATE purchase_review_reports SET status=?,resolution=?,resolved_by=?,resolved_at=CURRENT_TIMESTAMP WHERE kind=? AND review_id=? AND status='open'",('removed' if action=='remove' else 'dismissed',note,aid,row['kind'],row['review_id']))
        core['audit'](db,aid,'review_'+action,'review',row['review_id'],{'kind':row['kind'],'note':note})
        return {'ok':True}
    return UNHANDLED

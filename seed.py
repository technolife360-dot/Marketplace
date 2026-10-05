#!/usr/bin/env python3
"""Apply schema and development fixtures. No built-in administrator credentials."""
import os
import app

app.migrate()
if app.MODE!='development':
    print('Development sample identities and listings were skipped outside development mode.')
else:
    db=app.connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        seller=db.execute('SELECT id FROM users WHERE email=?',('seller@example.test',)).fetchone()
        if not seller:
            seller_id=app.ident();db.execute('INSERT INTO users(id,email,password_hash,display_name,email_verified) VALUES(?,?,?,?,1)',(seller_id,'seller@example.test',app.password_hash('SellerDev!2026'),'Demo seller'))
        else:seller_id=seller['id']
        buyer=db.execute('SELECT id FROM users WHERE email=?',('buyer@example.test',)).fetchone()
        if not buyer:
            buyer_id=app.ident();db.execute('INSERT INTO users(id,email,password_hash,display_name,email_verified) VALUES(?,?,?,?,1)',(buyer_id,'buyer@example.test',app.password_hash('BuyerDev!2026'),'Demo buyer'))
        else:buyer_id=buyer['id']
        db.execute("INSERT OR IGNORE INTO seller_profiles(user_id,shop_name,bio,verification_status) VALUES(?,?,?,'unverified')",(seller_id,'Demo Shop · Development','Namuna do‘kon. Mahsulot va savdolar sinov ma’lumoti hisoblanadi.'))
        listings=[
            ('demo-valorant-account','valorant','accounts','[DEMO] Valorant account · Platinum','Namuna e’lon. Ushbu hisob tafsilotlari uydirma bo‘lib, faqat development sinovi uchun ishlatiladi.',145000,'PC','Asia','manual','24 soat',1),
            ('demo-pubg-items','pubg-mobile','items','[DEMO] PUBG Mobile kolleksiya buyumlari','Namuna e’lon. Haqiqiy tranzaksiya yoki mahsulotni anglatmaydi.',78000,'Mobile','Global','manual','12 soat',4),
            ('demo-dota-coaching','dota-2','services','[DEMO] Dota 2 coaching · 1 soat','Namuna xizmat e’loni. O‘yin noshiri qoidalarini tekshirish zarur.',110000,'PC','Europe','service','1 kun',3),
        ]
        for lid,game,cat,title,desc,price,platform,region,delivery,eta,stock in listings:
            db.execute("INSERT OR IGNORE INTO listings(id,seller_id,game_id,category_id,title,description,product_type,price_minor,currency,platform,region,delivery_method,delivery_eta,stock,status) VALUES(?,?,?,?,?,?,?,?, 'UZS',?,?,?,?,?, 'published')",(lid,seller_id,game,cat,title,desc,db.execute('SELECT product_type FROM categories WHERE id=?',(cat,)).fetchone()['product_type'],price,platform,region,delivery,eta,stock))
        # One clearly identified sample wanted post and a sample conversation; no reviews or completed orders.
        db.execute("INSERT OR IGNORE INTO product_requests(id,requester_id,game_id,category_id,title,description,budget_minor,currency,expires_at) VALUES('demo-request-valorant',?,'valorant','accounts','[DEMO] Valorant account wanted','Development namuna so‘rovi. Xarid taklifi emas.',200000,'UZS',datetime('now','+20 days'))",(buyer_id,))
        conv='demo-conversation-1'
        db.execute("INSERT OR IGNORE INTO conversations(id,buyer_id,seller_id,listing_id) VALUES(?,?,?,'demo-valorant-account')",(conv,buyer_id,seller_id))
        db.execute("INSERT OR IGNORE INTO messages(id,conversation_id,sender_id,body) VALUES('demo-message-1',?,?,?)",(conv,seller_id,'Salom! Bu development demo suhbati.'))
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK');raise
    finally:db.close()
    print('Development data ready. Test buyer: buyer@example.test / BuyerDev!2026; seller: seller@example.test / SellerDev!2026.')
    print('These sample accounts and listings are local development fixtures only. No built-in administrator password is provided.')

email=os.environ.get('SEED_ADMIN_EMAIL','').strip().lower()
password=os.environ.get('SEED_ADMIN_PASSWORD','')
if bool(email)!=bool(password):raise SystemExit('Set both SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD, or leave both empty.')
if email:
    if email in ('buyer@example.test','seller@example.test'):
        raise SystemExit('Choose a separate email; demo accounts cannot be promoted to admin.')
    if len(password)<14:raise SystemExit('SEED_ADMIN_PASSWORD must be at least 14 characters.')
    db=app.connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
        if row:
            uid=row['id'];db.execute('UPDATE users SET email_verified=1,suspended=0 WHERE id=?',(uid,));db.execute('UPDATE users SET password_hash=? WHERE id=?',(app.password_hash(password),uid))
        else:
            uid=app.ident();db.execute('INSERT INTO users(id,email,password_hash,display_name,email_verified) VALUES(?,?,?,?,1)',(uid,email,app.password_hash(password),'SentryLoot admin'))
        db.execute('INSERT OR IGNORE INTO admin_accounts(user_id) VALUES(?)',(uid,));app.audit(db,uid,'admin_bootstrap','user',uid,{'source':'local seed command'});db.execute('COMMIT')
        print(f'Administrator ready: {email}')
    except Exception:db.execute('ROLLBACK');raise
    finally:db.close()

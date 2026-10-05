#!/usr/bin/env python3
"""Encrypt legacy plaintext delivery rows before production deployment."""
import app
import delivery_crypto


def main():
    if not delivery_crypto.key_is_configured():
        raise SystemExit('Set a valid DELIVERY_ENCRYPTION_KEY before migrating delivery records.')
    app.migrate()
    db=app.connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        rows=db.execute('SELECT order_item_id,protected_payload FROM deliveries').fetchall()
        migrated=0
        for row in rows:
            if delivery_crypto.is_encrypted(row['protected_payload']):
                continue
            encrypted=delivery_crypto.encrypt_payload(row['protected_payload'],row['order_item_id'])
            db.execute('UPDATE deliveries SET protected_payload=? WHERE order_item_id=?',(encrypted,row['order_item_id']))
            migrated+=1
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise
    finally:
        db.close()
    print(f'Encrypted {migrated} legacy delivery record(s).')


if __name__=='__main__': main()

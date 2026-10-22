"""Run a bounded Stripe TEST settlement batch; never performs migrations."""
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    if os.environ.get('PAYMENT_PROVIDER') != 'stripe_test':
        raise SystemExit('This worker requires PAYMENT_PROVIDER=stripe_test.')
    os.environ.setdefault('SESSION_SECRET', secrets.token_urlsafe(48))
    import app
    db = app.connect()
    try:
        result = app.stripe_test_payments.process(db, vars(app), limit=5)
        print('Stripe TEST jobs:', len(result['jobs']), 'retry:', sum(j['status']=='retry' for j in result['jobs']))
    finally:
        db.close()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Bounded authenticated load rehearsal against a disposable local database only."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import contextlib
import http.cookiejar
import io
import json
import os
from pathlib import Path
import secrets
import statistics
import sys
import tempfile
import threading
import time
from urllib.request import Request,build_opener,HTTPCookieProcessor
from urllib.error import HTTPError

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--users',type=int,default=8);parser.add_argument('--requests-per-user',type=int,default=12);args=parser.parse_args()
    if not 1<=args.users<=8 or not 1<=args.requests_per_user<=100:parser.error('Use 1–8 users and 1–100 requests per user.')
    os.environ.update(SENTRYLOOT_ENV_FILE='/dev/null',DATABASE_URL='',MARKETPLACE_MODE='development',PAYMENT_PROVIDER='disabled',EMAIL_PROVIDER='disabled',SESSION_SECRET=secrets.token_urlsafe(48),DELIVERY_ENCRYPTION_KEY=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    with tempfile.TemporaryDirectory(prefix='sentryloot-load-') as directory:
        os.environ['DATABASE_PATH']=str(Path(directory)/'load.sqlite3')
        import app
        app.migrate();db=app.connect()
        password=secrets.token_urlsafe(18)
        for i in range(args.users):db.execute('INSERT INTO users(id,email,password_hash,display_name,email_verified) VALUES(?,?,?,?,1)',('qa-'+str(i),'qa-'+str(i)+'@example.test',app.password_hash(password),'Local QA user'))
        db.close()
        class QuietHandler(app.Handler):
            def log_message(self,*args):pass
        server=app.ThreadingHTTPServer(('127.0.0.1',0),QuietHandler);base='http://127.0.0.1:'+str(server.server_address[1])
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        paths=['/api/me','/api/listings?limit=12','/api/categories','/api/top-up/catalog','/api/status','/api/catalogue/facets']
        def worker(i):
            opener=build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()));samples=[]
            calls=[('/api/login',{'email':'qa-'+str(i)+'@example.test','password':password})]+[(paths[n%len(paths)],None) for n in range(args.requests_per_user)]
            for path,body in calls:
                started=time.monotonic()
                request=Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
                try:
                    with opener.open(request,timeout=15) as response:
                        status=response.status;json.load(response)
                except HTTPError as exc:status=exc.code
                except Exception:status=0
                samples.append({'status':status,'ms':(time.monotonic()-started)*1000})
            return samples
        try:
            started=time.monotonic()
            with contextlib.redirect_stdout(io.StringIO()),ThreadPoolExecutor(max_workers=args.users) as pool:results=[sample for group in pool.map(worker,range(args.users)) for sample in group]
            elapsed=time.monotonic()-started
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
        timings=sorted(r['ms'] for r in results);failures=[r for r in results if r['status']!=200]
        report={'environment':'disposable SQLite + local Python server; not a production or physical-device result','concurrent_users':args.users,'requests':len(results),'elapsed_seconds':round(elapsed,2),'successful':len(results)-len(failures),'failed':len(failures),'status_counts':{str(s):sum(r['status']==s for r in results) for s in sorted({r['status'] for r in results})},'latency_ms':{'median':round(statistics.median(timings),2),'p95':round(timings[min(len(timings)-1,int(len(timings)*.95))],2),'max':round(max(timings),2)}}
        print(json.dumps(report,indent=2));return 1 if failures else 0

if __name__=='__main__':raise SystemExit(main())

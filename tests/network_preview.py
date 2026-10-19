"""Local-only aggregate bandwidth/latency proxy for repeatable browser QA, never deployed."""
import argparse
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8032);parser.add_argument('--upstream',type=int,default=8031);parser.add_argument('--kbps',type=int,default=1600);parser.add_argument('--latency-ms',type=int,default=200);args=parser.parse_args()
lock=threading.Lock();next_chunk=0.0
class Proxy(BaseHTTPRequestHandler):
    def do_GET(self):
        global next_chunk
        if self.path.startswith(('http:','https:','//')):self.send_error(400);return
        time.sleep(args.latency_ms/1000)
        try:
            response=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:'+str(args.upstream)+self.path,headers={'Accept-Encoding':self.headers.get('Accept-Encoding','identity')}),timeout=30)
        except urllib.error.HTTPError as error:response=error
        except Exception:self.send_error(502);return
        with response:
            body=response.read();self.send_response(response.status)
            self.send_header('Content-Type',response.headers.get('Content-Type','application/octet-stream'));self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
            if response.headers.get('Content-Encoding'):self.send_header('Content-Encoding',response.headers['Content-Encoding'])
            self.end_headers()
            try:
                for offset in range(0,len(body),8192):
                    chunk=body[offset:offset+8192]
                    with lock:
                        next_chunk=max(time.monotonic(),next_chunk)+len(chunk)/(args.kbps*1000/8);when=next_chunk
                    time.sleep(max(0,when-time.monotonic()));self.wfile.write(chunk)
            except (BrokenPipeError,ConnectionResetError):pass
    def log_message(self,*args):pass
print(f'Local QA proxy: 127.0.0.1:{args.port}, {args.kbps} kbps aggregate, {args.latency_ms} ms response latency',flush=True)
ThreadingHTTPServer(('127.0.0.1',args.port),Proxy).serve_forever()

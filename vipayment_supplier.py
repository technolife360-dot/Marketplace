"""Server-only, read-only VIPayment connection. No purchase or delivery calls.

VIPayment's public docs do not establish a sandbox. These checks access the
actual supplier account and catalogue, but cannot spend its balance.
"""
import hashlib
import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class SupplierError(RuntimeError):
    pass


def configuration():
    identifier=os.environ.get('VIPAYMENT_API_ID','').strip()
    key=os.environ.get('VIPAYMENT_API_KEY','').strip()
    return {'configured':bool(identifier and key),'identifier':identifier,'key':key}


def request(operation):
    if operation not in ('profile','services'):
        raise SupplierError('VIPayment adapter supports read-only connection checks only.')
    config=configuration()
    if not config['configured']:
        raise SupplierError('VIPayment API ID va API kaliti serverda sozlanmagan.')
    values={'key':config['key'],'sign':hashlib.md5((config['identifier']+config['key']).encode()).hexdigest()}
    path='/api/profile'
    if operation=='services':
        path='/api/game-feature';values['type']='services'
    req=Request('https://vip-reseller.co.id'+path,data=urlencode(values).encode(),
        headers={'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded'},method='POST')
    try:
        with urlopen(req,timeout=12) as response:
            raw=response.read(1000001)
    except HTTPError as error:
        raise SupplierError(f'VIPayment API HTTP {error.code}. Ulanish tasdiqlanmadi.') from None
    except (URLError,TimeoutError,OSError):
        raise SupplierError('VIPayment API bilan bog‘lanib bo‘lmadi.') from None
    if len(raw)>1000000:raise SupplierError('VIPayment katalog javobi hajmi juda katta.')
    try:payload=json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError,ValueError):raise SupplierError('VIPayment API JSON javob bermadi.') from None
    if not isinstance(payload,dict) or payload.get('result') is not True:
        raise SupplierError('VIPayment API autentifikatsiya yoki so‘rovni tasdiqlamadi.')
    return payload.get('data')


def account_status():
    account=request('profile')
    if not isinstance(account,dict) or not isinstance(account.get('username'),str) or not account['username'].strip():
        raise SupplierError('VIPayment akkaunti API javobida tasdiqlanmadi.')
    return {'provider':'VIPayment','configured':True,'connected':True,'access':'read_only',
            'orders_enabled':False,'sandbox_verified':False,'username':account['username'][:100],
            'level':str(account.get('level',''))[:50]}


def catalog_services():
    services=request('services')
    if not isinstance(services,list):raise SupplierError('VIPayment katalog formati noto‘g‘ri.')
    return [{key:row.get(key) for key in ('code','game','name','price','status','server')}
            for row in services if isinstance(row,dict) and row.get('code')]

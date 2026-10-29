"""Lightweight region preferences and shared, bounded public FX cache.

Region is a browsing suggestion, never proof of residence or payment eligibility.
No visitor IP is sent to an external service. FX requests contain only a USD base.
"""
import json
import math
import os
import re
import threading
import time
from urllib.request import Request, urlopen

from pathlib import Path
from asia_markets import COUNTRIES, COUNTRY_CURRENCIES, CURRENCIES, ASIA_MARKETS

LANGUAGE_DATA = json.loads((Path(__file__).resolve().parent / "static/regional-languages.json").read_text(encoding="utf-8"))
SUPPORTED_LANGUAGES = frozenset(item["code"] for item in LANGUAGE_DATA["languages"])
COUNTRY_LANGUAGES = {row["country"]: row.get("language", "en") for row in ASIA_MARKETS}

_lock = threading.Lock()
_rates = {}
_dates = {}
_expires = 0
_retry_after = 0
TTL = 21600
MAX_STALE = 172800
_updated = 0


def browser_preferences(header):
    """Honor language quality weights; do not infer residence from language alone."""
    choices = []
    for index, part in enumerate(str(header or '')[:1024].split(',')):
        tag, _, params = part.strip().partition(';')
        if not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', tag):
            continue
        try:
            quality = float(params.split('=', 1)[1]) if params.startswith('q=') else 1
        except (ValueError, IndexError):
            continue
        if not 0 < quality <= 1:
            continue
        choices.append((-quality, index, tag))
    choices.sort()
    language = 'en'
    if choices:
        primary = choices[0][2].split('-')[0].lower()
        language = primary if primary in SUPPORTED_LANGUAGES else 'en'
    country = ''
    for _, _, tag in choices:
        for part in tag.split('-')[1:]:
            if len(part) == 2 and part.upper() in COUNTRIES:
                country = part.upper()
                break
        if country:
            break
    return language, country


def resolve(headers, user=None):
    language, browser_country = browser_preferences(headers.get('Accept-Language', ''))
    # Vercel supplies this edge header. Do not trust it on a direct/local server.
    edge = headers.get('X-Vercel-IP-Country', '').upper() if os.environ.get('VERCEL') == '1' else ''
    country = edge if edge in COUNTRIES else browser_country
    source = 'edge' if edge in COUNTRIES else 'browser' if country else 'default'
    country = country or 'US'
    if user and user.get('country') in COUNTRIES:
        country, source = user['country'], 'profile'
    currency = COUNTRY_CURRENCIES[country]
    if user:
        language = user.get('language') if user.get('language') in SUPPORTED_LANGUAGES else language
        currency = user.get('currency') if user.get('currency') in CURRENCIES else currency
    return {'country': country, 'currency': currency, 'language': language, 'source': source,
            'supported_languages': sorted(SUPPORTED_LANGUAGES)}


def exchange_rates():
    """One upstream snapshot per warm process/6h; single flight and failure backoff.

    A last-good snapshot is usable for at most 48h, explicitly marked stale.
    Missing/invalid rates never become invented 1:1 conversions.
    """
    global _rates, _dates, _expires, _retry_after, _updated
    now = time.time()
    with _lock:
        if now >= _expires and now >= _retry_after:
            try:
                request = Request('https://api.frankfurter.dev/v2/rates?base=USD',
                                  headers={'Accept': 'application/json', 'User-Agent': 'SentryLoot/1.0'})
                with urlopen(request, timeout=3) as response:
                    payload = json.loads(response.read(131073))
                rates, dates = {'USD': 1.0}, {}
                for item in payload:
                    code, value = item['quote'], float(item['rate'])
                    if code in CURRENCIES and item['base'] == 'USD' and math.isfinite(value) and value > 0:
                        rates[code] = value
                        dates[code] = item['date']
                if len(rates) < 20:
                    raise ValueError('Incomplete FX snapshot')
                _rates, _dates, _updated, _expires = rates, dates, now, now + TTL
            except (OSError, ValueError, KeyError, TypeError):
                _retry_after = now + 300
        available = bool(_rates) and now - _updated < MAX_STALE
        return {'base': 'USD', 'rates': dict(_rates) if available else {},
                'dates': dict(_dates) if available else {}, 'stale': available and now >= _expires,
                'updated_at': int(_updated) if available else None,
                'expires_at': int(_expires) if available else None, 'estimate_only': True}

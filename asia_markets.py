"""Shared country/currency coverage used for user profile validation."""
import json
from pathlib import Path

ASIA_MARKETS = json.loads((Path(__file__).resolve().parent / 'static' / 'asia-markets.json').read_text(encoding='utf-8'))
ASIA_COUNTRY_CURRENCIES = {row['country']: row['currency'] for row in ASIA_MARKETS}
ASIA_COUNTRIES = frozenset(ASIA_COUNTRY_CURRENCIES)
ASIA_CURRENCIES = frozenset(ASIA_COUNTRY_CURRENCIES.values())

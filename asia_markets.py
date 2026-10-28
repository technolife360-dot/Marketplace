"""Global country/currency coverage (legacy module name retained for compatibility)."""
import json
from pathlib import Path

ASIA_MARKETS = json.loads((Path(__file__).resolve().parent / 'static' / 'asia-markets.json').read_text(encoding='utf-8'))
ASIA_COUNTRY_CURRENCIES = {row['country']: row['currency'] for row in ASIA_MARKETS}
ASIA_COUNTRIES = frozenset(ASIA_COUNTRY_CURRENCIES)
ASIA_CURRENCIES = frozenset(ASIA_COUNTRY_CURRENCIES.values())

# Source: Unicode CLDR currencyData, current legal tender; ISO 3166 territories.
# These are browsing preferences, not payment-provider eligibility.
MARKETS = ASIA_MARKETS
COUNTRY_CURRENCIES = ASIA_COUNTRY_CURRENCIES
COUNTRIES = ASIA_COUNTRIES
CURRENCIES = ASIA_CURRENCIES

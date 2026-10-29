"""Global preferences, spoofing isolation and FX outage/cache correctness."""
import json
import unittest
from unittest.mock import patch, MagicMock
import app
import regional_preferences as region
from asia_markets import COUNTRIES, COUNTRY_CURRENCIES
from tests import test_operations as fixtures


class RegionDetection(unittest.TestCase):
    def test_required_markets_and_global_coverage(self):
        self.assertEqual(len(COUNTRIES),249)
        for code,currency in {'US':'USD','GB':'GBP','DE':'EUR','CA':'CAD','MY':'MYR','SG':'SGD','SA':'SAR'}.items():
            with self.subTest(code=code),patch.dict('os.environ',{'VERCEL':'1'}):
                result=region.resolve({'X-Vercel-IP-Country':code,'Accept-Language':'en-US'})
                self.assertEqual((result['country'],result['currency'],result['source']),(code,currency,'edge'))
    def test_no_trust_in_direct_host_headers_and_no_country_from_language_only(self):
        with patch.dict('os.environ',{'VERCEL':''}):
            self.assertEqual(region.resolve({'X-Vercel-IP-Country':'GB','Accept-Language':'de-DE'})['country'],'DE')
            self.assertEqual(region.resolve({'Accept-Language':'de'})['source'],'default')
    def test_quality_fallback_unknown_and_language_safety(self):
        self.assertEqual(region.browser_preferences('ru-RU;q=0.2,en-GB;q=0.9'),('en','GB'))
        self.assertEqual(region.browser_preferences('de-DE,de;q=0.9,en;q=0.5'),('de','DE'))
        self.assertEqual(region.browser_preferences('ar-SA'),('ar','SA'))
        self.assertEqual(region.browser_preferences('ru;q=0,*;q=0.8,en-GB;q=bad'),('en',''))
        with patch.dict('os.environ',{'VERCEL':'1'}):
            self.assertEqual(region.resolve({'X-Vercel-IP-Country':'XX'})['country'],'US')
    def test_profile_wins_without_mutating_it_on_travel(self):
        user={'country':'GB','currency':'EUR','language':'uz'};before=dict(user)
        with patch.dict('os.environ',{'VERCEL':'1'}):result=region.resolve({'X-Vercel-IP-Country':'MY'},user)
        self.assertEqual((result['country'],result['currency'],result['language'],result['source']),('GB','EUR','uz','profile'))
        self.assertEqual(user,before)
    def test_fx_single_snapshot_cache_failure_backoff_and_expiry(self):
        payload=[{'base':'USD','quote':code,'rate':2,'date':'2026-10-28'} for code in list(set(COUNTRY_CURRENCIES.values()))[:25]]
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps(payload).encode()
        with patch.multiple(region,_rates={},_dates={},_expires=0,_retry_after=0,_updated=0),patch.object(region,'urlopen',return_value=response) as upstream,patch.object(region.time,'time',return_value=1000000):
            first=region.exchange_rates();second=region.exchange_rates()
            self.assertEqual(first,second);self.assertEqual(upstream.call_count,1)
            self.assertGreater(len(first['rates']),20)
            with patch.object(region.time,'time',return_value=1000000+region.TTL+1),patch.object(region,'urlopen',side_effect=OSError) as down:
                self.assertTrue(region.exchange_rates()['stale']);region.exchange_rates();self.assertEqual(down.call_count,1)
            with patch.object(region.time,'time',return_value=1000000+region.MAX_STALE+1),patch.object(region,'urlopen',side_effect=OSError):
                self.assertEqual(region.exchange_rates()['rates'],{})


class RegionFlows(unittest.TestCase):
    setUp=fixtures.OperationsFlows.setUp
    tearDown=fixtures.OperationsFlows.tearDown
    route=fixtures.OperationsFlows.route
    ctx=fixtures.OperationsFlows.ctx
    def test_global_profile_changes_default_currency_and_preserves_explicit_override(self):
        for code,currency in {'US':'USD','GB':'GBP','DE':'EUR','CA':'CAD','MY':'MYR','SG':'SGD','SA':'SAR'}.items():
            result=self.route(self.buyer,'POST','/api/profile',{'country':code})
            self.assertEqual((result['user']['country'],result['user']['currency']),(code,currency))
        result=self.route(self.buyer,'POST','/api/profile',{'country':'GB','currency':'USD'})
        self.assertEqual(result['user']['currency'],'USD')
        result=self.route(self.buyer,'GET','/api/me')
        self.assertEqual(result['region']['source'],'profile');self.assertEqual(result['region']['country'],'GB')
    def test_registration_accepts_global_countries(self):
        for code in ['US','GB','DE','CA','MY','SG','SA']:
            # Rate limits remain active in production; reset only this isolated fixture.
            self.db.execute('DELETE FROM rate_limits')
            self.route(None,'POST','/api/register',{'country':code,'email':code.lower()+'@test.invalid','name':'Region QA','password':'unique-test-password','accept_terms':True})
            row=self.db.execute('SELECT country,currency FROM users WHERE email=?',(code.lower()+'@test.invalid',)).fetchone()
            self.assertEqual((row['country'],row['currency']),(code,COUNTRY_CURRENCIES[code]))
    def test_invalid_region_does_not_write_profile(self):
        before=self.ctx(self.buyer)['user']
        with self.assertRaises(app.HttpError):self.route(self.buyer,'POST','/api/profile',{'country':'GB','currency':'XXX'})
        self.assertEqual(self.ctx(self.buyer)['user']['country'],before['country'])

class ExpandedLanguages(RegionFlows):
    def test_all_languages_save_through_profile_and_resolve_after_login(self):
        self.assertEqual(len(region.SUPPORTED_LANGUAGES),14)
        for language in region.SUPPORTED_LANGUAGES:
            result=self.route(self.buyer,'POST','/api/profile',{'country':'DE','currency':'EUR','language':language})
            self.assertEqual(result['user']['language'],language)
            self.assertEqual(self.route(self.buyer,'GET','/api/me')['region']['language'],language)
    def test_european_defaults_share_country_dataset(self):
        for country,expected in {'DE':('EUR','de'),'FR':('EUR','fr'),'IT':('EUR','it'),'ES':('EUR','es'),'NL':('EUR','nl'),'PL':('PLN','pl'),'PT':('EUR','pt'),'GB':('GBP','en'),'CH':('CHF','en')}.items():
            self.assertEqual((region.COUNTRY_CURRENCIES[country],region.COUNTRY_LANGUAGES[country]),expected)

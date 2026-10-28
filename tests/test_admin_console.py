"""Financial reporting correctness, authorization and expense audit regression tests."""
import unittest
from datetime import timedelta
from unittest.mock import patch
import app
import admin_console as console
from tests import test_operations as fixtures


class AdminConsole(unittest.TestCase):
    setUp = fixtures.OperationsFlows.setUp
    tearDown = fixtures.OperationsFlows.tearDown
    route = fixtures.OperationsFlows.route
    ctx = fixtures.OperationsFlows.ctx

    def expense(self, **extra):
        return {'id':'expense-test-id-00000001','amount_minor':2500,'currency':'UZS','book':'sandbox',
                'category':'infrastructure','description':'Local QA hosting expense','incurred_on':str(console.today()),**extra}

    def seed_order(self, key='one', mode='sandbox', currency='UZS', fee=500, status='completed'):
        self.db.execute('INSERT INTO orders(id,reference,buyer_id,currency,subtotal_minor,commission_minor,total_minor,status,payment_mode) VALUES(?,?,?,?,10000,500,10500,?,?)', (key,'SL-'+key,self.buyer,currency,status,mode))
        self.db.execute("INSERT INTO order_items(id,order_id,listing_id,seller_id,title,quantity,unit_price_minor,commission_minor,delivery_method) VALUES(?,?,?,?, 'QA product',1,10000,500,'manual')",('item-'+key,key,self.listing,self.seller))
        self.db.execute("INSERT INTO payments(id,order_id,provider,amount_minor,currency,status,idempotency_key) VALUES(?,?,?,10500,?,'succeeded',?)",('pay-'+key,key,mode,currency,'pay-'+key))
        kind='stripe_test_commission' if mode=='stripe_test' else 'platform_commission'
        self.db.execute("INSERT INTO ledger_entries(id,order_id,entry_type,amount_minor,currency,description) VALUES(?,?,?,?,?,'QA commission')",('fee-'+key,key,kind,fee,currency))

    def report(self, **qs):
        from urllib.parse import urlencode
        return self.route(self.admin,'GET','/api/admin/finance?'+urlencode({'book':'sandbox','currency':'UZS',**qs}))

    def test_ledger_revenue_is_not_gmv_and_books_currencies_do_not_mix(self):
        self.seed_order();self.seed_order('stripe','stripe_test');self.seed_order('live','live');self.seed_order('foreign','sandbox','MYR')
        self.db.execute("INSERT INTO ledger_entries(id,order_id,entry_type,amount_minor,currency,description) VALUES('hold','one','escrow_fee_hold',900000,'UZS','not income')")
        self.route(self.admin,'POST','/api/admin/expenses',self.expense())
        result=self.report()
        self.assertEqual((result['gmv_minor'],result['revenue_minor'],result['expense_minor'],result['profit_minor']),(10000,500,2500,-2000))
        self.assertEqual(sum(x['revenue_minor'] for x in result['daily']),500)
        self.assertEqual(sum(x['amount_minor'] for x in result['games']),500)
        self.assertEqual(self.report(book='live')['expense_minor'],0)
        self.assertEqual(self.report(book='stripe_test')['revenue_minor'],500)
        self.assertEqual(self.report(currency='MYR')['revenue_minor'],500)
        self.assertNotIn('buyer_email',str(result))

    def test_reversal_subtracts_commission_and_refunded_gmv_is_excluded(self):
        self.seed_order(mode='stripe_test')
        self.db.execute("INSERT INTO ledger_entries(id,order_id,entry_type,amount_minor,currency,description) VALUES('reversal','one','stripe_test_commission',-500,'UZS','Refund')")
        self.db.execute("UPDATE orders SET status='refunded' WHERE id='one'")
        result=self.report(book='stripe_test')
        self.assertEqual(result['revenue_minor'],0);self.assertEqual(result['gmv_minor'],0)

    def test_expense_idempotency_conflict_and_void_are_audited(self):
        expense=self.expense()
        for _ in range(2): self.route(self.admin,'POST','/api/admin/expenses',expense)
        self.assertEqual(self.report()['expense_minor'],2500)
        with self.assertRaises(app.HttpError) as error:
            self.route(self.admin,'POST','/api/admin/expenses',{**expense,'amount_minor':500})
        self.assertEqual(error.exception.status,409)
        for _ in range(2): self.route(self.admin,'POST','/api/admin/expenses/'+expense['id']+'/void',{'reason':'Duplicate local QA entry'})
        self.assertEqual(self.report()['expense_minor'],0)
        self.assertIsNotNone(self.report()['expenses'][0]['voided_at'])
        actions=[r['action'] for r in self.route(self.admin,'GET','/api/admin/audit')]
        self.assertEqual(actions.count('expense_recorded'),1);self.assertEqual(actions.count('expense_voided'),1)

    def test_admin_only_even_for_scoped_staff(self):
        import launch_readiness
        launch_readiness.put_config(self.db,'staff_capabilities:'+self.buyer,['content','moderation','support'])
        for uid in (self.buyer,self.seller,None):
            for method,path,data in [('GET','/api/admin/finance',{}),('GET','/api/admin/audit',{}),('POST','/api/admin/expenses',self.expense()),('POST','/api/admin/expenses/expense-test-id-00000001/void',{'reason':'Test reason'})]:
                with self.assertRaises(app.HttpError) as error:self.route(uid,method,path,data)
                self.assertIn(error.exception.status,(401,403))

    def test_dates_and_expense_payload_validation(self):
        for field,value in [('amount_minor',0),('amount_minor',-1),('amount_minor',True),('amount_minor',1.5),('amount_minor',10**12+1),('currency',[]),('currency','XXX'),('book',{}),('book','untrusted'),('category','unknown'),('description','x'),('id','short'),('incurred_on','2026-02-30'),('incurred_on',str(console.today()+timedelta(days=1)))]:
            with self.subTest(field=field,value=value),self.assertRaises(app.HttpError): self.route(self.admin,'POST','/api/admin/expenses',self.expense(**{field:value}))
        for qs in ({'start':'2026-02-30'}, {'start':'2000-01-01'},{'start':str(console.today()),'end':'2000-01-01'},{'end':str(console.today()+timedelta(days=1))},{'book':'anything'}):
            with self.assertRaises(app.HttpError):self.report(**qs)
        self.assertEqual(self.report()['expense_minor'],0)

    def test_range_boundaries_empty_zero_and_bounded_expense_list(self):
        result=self.report(start=str(console.today()),end=str(console.today()))
        self.assertEqual(len(result['daily']),1);self.assertEqual(result['profit_minor'],0)
        for n in range(105):self.route(self.admin,'POST','/api/admin/expenses',self.expense(id=f'expense-test-id-{n:08}'))
        result=self.report()
        self.assertEqual(result['expense_minor'],105*2500);self.assertEqual(result['expense_count'],105);self.assertEqual(len(result['expenses']),100)
        tomorrow=str(console.today()+timedelta(days=1))
        self.seed_order()
        self.db.execute('UPDATE ledger_entries SET created_at=?',(tomorrow,))
        self.assertEqual(self.report()['revenue_minor'],0)

    def test_audit_never_exposes_freeform_details(self):
        app.audit(self.db,self.admin,'qa_event','test','safe',{'private_secret':'SHOULD_NOT_LEAK'})
        rows=self.route(self.admin,'GET','/api/admin/audit')
        self.assertNotIn('SHOULD_NOT_LEAK',str(rows));self.assertNotIn('details_json',rows[0])

    def test_myr_minor_units_are_kept_as_integers(self):
        self.route(self.admin,'POST','/api/admin/expenses',self.expense(currency='MYR',amount_minor=1234))
        self.assertEqual(self.report(currency='MYR')['expense_minor'],1234)
        self.assertEqual(self.report()['expense_minor'],0)


if __name__=='__main__':unittest.main()

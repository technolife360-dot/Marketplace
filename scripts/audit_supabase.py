#!/usr/bin/env python3
"""Read-only Supabase schema audit. Requires DATABASE_URL in the process environment."""

import os
import re
import sys
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / 'supabase' / 'migrations'
PRIVILEGES = 'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER'
REQUIRED_COLUMNS = {
    'topup_packages': {'coming_soon', 'supplier_type_id', 'manual_enabled', 'supplier_enabled', 'stock_reserved'},
    'topup_orders': {'inventory_quantity', 'supplier_quantity', 'payment_reference'},
    'account_reviews': {'buyer_attested_at', 'reviewed_by', 'status'},
    'account_review_evidence': {'object_path', 'slot'},
    'listings': {'seller_account_terms_version', 'seller_account_terms_at', 'delivery_minutes'},
    'orders': {'accepted_account_sale_terms_version', 'accepted_account_sale_terms_at','completed_at','protection_until'},
    'sessions': {'mfa_verified','created_at','last_seen_at','user_agent','network_label'},
    'order_items': {'snapshot_json','delivery_due_at','delivered_quantity'},
    'reports': {'response_due_at','resolved_at'},
}


def expected_tables():
    names = set()
    for migration in sorted(MIGRATIONS.glob('*.sql')):
        names.update(re.findall(r'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+public\.([a-z_]+)', migration.read_text(), re.I))
    return names


def collect_findings(connection):
    errors, warnings = [], []
    expected = expected_tables()
    with connection.transaction():
        connection.execute('SET TRANSACTION READ ONLY')
        rows = connection.execute("""SELECT c.relname, c.relrowsecurity,
            has_table_privilege('anon', c.oid, %s) AS anon_access,
            has_table_privilege('authenticated', c.oid, %s) AS authenticated_access
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p')
            ORDER BY c.relname""", (PRIVILEGES, PRIVILEGES)).fetchall()
        actual = {row['relname'] for row in rows}
        for name in sorted(expected - actual):
            errors.append(f'Missing table: public.{name}')
        for row in rows:
            name = row['relname']
            if not row['relrowsecurity']:
                errors.append(f'RLS disabled: public.{name}')
            for role in ('anon', 'authenticated'):
                if row[f'{role}_access']:
                    errors.append(f'Browser role {role} has a table privilege: public.{name}')
            if name not in expected:
                warnings.append(f'Unexpected public table; review ownership and grants: public.{name}')

        columns = connection.execute("""SELECT c.relname AS table_name, a.attname AS column_name
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind IN ('r','p')
              AND a.attnum>0 AND NOT a.attisdropped""").fetchall()
        actual_columns = {}
        for row in columns:
            actual_columns.setdefault(row['table_name'], set()).add(row['column_name'])
        for table, required in REQUIRED_COLUMNS.items():
            for column in sorted(required - actual_columns.get(table, set())):
                errors.append(f'Missing column: public.{table}.{column}')

        default = connection.execute("""SELECT pg_get_expr(d.adbin,d.adrelid) AS column_default
            FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
            JOIN pg_namespace n ON n.oid=c.relnamespace
            LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
            WHERE n.nspname='public' AND c.relname='seller_profiles' AND a.attname='selling_enabled'""").fetchone()
        if default and default['column_default'] not in ('0', '0::smallint'):
            warnings.append('seller_profiles.selling_enabled default is not 0; apply latest migration')

        unvalidated = connection.execute("""SELECT c.conname, t.relname
            FROM pg_constraint c JOIN pg_class t ON t.oid=c.conrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
            WHERE n.nspname='public' AND c.contype='c' AND NOT c.convalidated""").fetchall()
        for row in unvalidated:
            warnings.append(f'Constraint awaits validation after legacy-data review: public.{row["relname"]}.{row["conname"]}')

        if 'seller_profiles' in actual:
            invalid = connection.execute("""SELECT count(*) AS n FROM public.seller_profiles
                WHERE selling_enabled=1 AND (verification_status!='verified' OR identity_status!='verified' OR identity_provider!='didit')""").fetchone()['n']
            if invalid:
                errors.append(f'{invalid} seller profiles are enabled without complete verification')
        if 'topup_packages' in actual and REQUIRED_COLUMNS['topup_packages'] <= actual_columns.get('topup_packages', set()):
            invalid = connection.execute("""SELECT count(*) AS n FROM public.topup_packages WHERE
                enabled NOT IN (0,1) OR coming_soon NOT IN (0,1) OR manual_enabled NOT IN (0,1) OR supplier_enabled NOT IN (0,1)""").fetchone()['n']
            if invalid:
                errors.append(f'{invalid} top-up packages contain invalid boolean flags')
        if 'topup_orders' in actual and REQUIRED_COLUMNS['topup_orders'] <= actual_columns.get('topup_orders', set()):
            invalid = connection.execute("""SELECT count(*) AS n FROM public.topup_orders
                WHERE inventory_quantity < 0 OR supplier_quantity < 0""").fetchone()['n']
            if invalid:
                errors.append(f'{invalid} top-up orders contain negative fulfillment counts')
    return errors, warnings, len(rows)


def main():
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        print('DATABASE_URL is required in the process environment; no dotenv file is loaded.', file=sys.stderr)
        return 2
    try:
        with psycopg.connect(url, connect_timeout=15, row_factory=dict_row, autocommit=False) as connection:
            errors, warnings, table_count = collect_findings(connection)
    except psycopg.Error as exc:
        # Connection exceptions can contain host names or DSNs. Never print them.
        print(f'Database audit failed: {type(exc).__name__}', file=sys.stderr)
        return 2
    print(f'Audited {table_count} public tables in a read-only transaction.')
    for message in errors:
        print('ERROR: ' + message)
    for message in warnings:
        print('WARN: ' + message)
    if not errors and not warnings:
        print('Schema checks passed.')
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Reviewed PostgreSQL shadow-column manifest. Generates SQL; never executes it.

Only apply the generated DDL to an independently restored STAGING database
AFTER verifying its complete backup and performance characteristics.

The existing NUMERIC columns remain untouched for a later exact backfill.
Do not automatically backfill using NUMERIC->TEXT SQL concatenation: canonical
integer encoding must be performed by a tested converter with row comparison.
"""
from pathlib import Path

SCHEMA='hare_factory'
# Ledger-relevant numeric data. Identifiers, timestamps, flags and rates
# are deliberately excluded; they must not become astronomical quantities.
ECONOMIC_COLUMNS={
    'factories':('cash',),
    'stock':('quantity','work'),
    'listings':('quantity','price'),
    'orders':('quantity','price'),
    'bank_accounts':('deposit','matures','debt','tax','taxable_sales'),
    'bank_contracts':('principal','amount','matures'),
    'sales':('sold_quantity','unit_price','unit_cost'),
    'market_ticks':('sold','revenue','inventory','cost'),
    'market_history':('offered','sold','revenue'),
    'factory_totals':('manufactured','purchases'),
    'auto_totals':('quantity',),
    'rare_collection':('quantity',),
    'admin_fund_transfers':('amount','before_cash','after_cash'),
    'admin_debt_cancellations':('debt',),
    'admin_overdraft_cancellations':('cash_restored',),
}

def q(identifier):
    if not identifier.replace('_','').isalnum() or not identifier[0].isalpha():
        raise ValueError('Unexpected SQL identifier')
    return '"'+identifier+'"'

def generate_staging_sql():
    lines=[
        '-- FOR RESTORED STAGING DATABASE ONLY. DO NOT RUN ON PRODUCTION.',
        '-- No production database modifications performed by this generator.',
        '-- These are nullable shadow columns: old NUMERIC remains authoritative.',
        '-- Post-cutover rollback needs a V2-compatible application.',
        'BEGIN;',
    ]
    for table,columns in ECONOMIC_COLUMNS.items():
        for column in columns:
            lines.append(
                f'ALTER TABLE {q(SCHEMA)}.{q(table)} '
                f'ADD COLUMN IF NOT EXISTS {q(column+"_v2")} TEXT;')
    lines.append('COMMIT;')
    return '\n'.join(lines)+'\n'

def verify_live_schema(readonly_columns):
    """No DB access; supplied items must come from a separate read-only query.

    readonly_columns is a {(table,column): type_name} dictionary from
    information_schema; SQL is not emitted if drift is detected.
    """
    missing=[]
    wrong=[]
    for table,columns in ECONOMIC_COLUMNS.items():
        for column in columns:
            kind=readonly_columns.get((table,column))
            if kind is None:
                missing.append(f'{table}.{column}')
            elif kind.lower()!='numeric':
                wrong.append(f'{table}.{column}: {kind}')
    if missing or wrong:
        raise ValueError('Schema drift. Missing '+repr(missing)+', unexpected '+repr(wrong))
    return True

if __name__=='__main__':
    print(generate_staging_sql(),end='')

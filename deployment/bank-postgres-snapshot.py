"""PostgreSQL connection for the existing game repository queries."""
from decimal import Decimal
from pathlib import Path
import os
from functools import lru_cache
from threading import Lock

from psycopg_pool import PoolTimeout

POOL_INIT = Lock()
AUTH_GATE = Lock()
GAME_GATE = Lock()
import re
import sqlite3

from exact import ExactRow


def row_factory(cursor):
    def make_row(values):
        converted = [
            int(value) if isinstance(value, Decimal) and value == value.to_integral_value()
            else (str(value) if value.adjusted() > 300 else float(value)) if isinstance(value, Decimal)
            else value
            for value in values
        ]
        return ExactRow(cursor, converted)
    return make_row


@lru_cache(maxsize=4)
def _shared_connection_pool(url):
    from psycopg_pool import ConnectionPool

    def configure(connection):
        connection.execute('SET search_path TO hare_factory, pg_catalog')
        connection.execute("SET statement_timeout = '20s'")

    # Share the pool between auth, admin and market, avoiding Supabase exhaustion.
    return ConnectionPool(
        url, min_size=0, max_size=(8 if os.environ.get("RENDER_SERVICE_NAME") == "hare-machi-factory-sg" else 1),
        timeout=12, max_idle=15, open=True,
        configure=configure,
        kwargs=dict(autocommit=True, row_factory=row_factory, connect_timeout=5,
                    sslmode='verify-full', sslrootcert=str(Path(__file__).with_name('supabase-ca.crt'))),
    )
 

def connection_pool(url, auth_only=False, admin_only=False):
    return _shared_connection_pool(url)


class Postgres:
    def __init__(self, url, *, auth_only=False, read_only=False, admin_only=False):
        import psycopg
        self.driver = psycopg
        with POOL_INIT:
            self.pool = connection_pool(url, auth_only, admin_only)
        self.connection = None
        self.gate = None
        if not read_only:
            gate = AUTH_GATE if auth_only else GAME_GATE
            if not gate.acquire(timeout=18):
                raise sqlite3.OperationalError('Database writer queue timed out')
            self.gate = gate
        try:
            self.connection = self.pool.getconn()
            # Keep login throttling serialized independently of market settlement.
            if not read_only:
                self.connection.execute('SELECT pg_advisory_lock(%s)', (1042120 if auth_only else 1042119,))
        except (psycopg.Error, PoolTimeout) as error:
            self.close()
            raise sqlite3.OperationalError('PostgreSQL initialization failed') from error

    def execute(self, query, params=()):
        sql = query.strip()
        if sql == 'BEGIN IMMEDIATE':
            return self.connection.execute('BEGIN')
        if sql.startswith('INSERT OR IGNORE INTO '):
            sql = sql.replace('INSERT OR IGNORE INTO ', 'INSERT INTO ', 1) + ' ON CONFLICT DO NOTHING'
        elif sql.startswith('INSERT OR REPLACE INTO market_history '):
            sql = sql.replace('INSERT OR REPLACE INTO ', 'INSERT INTO ', 1)
            sql += (' ON CONFLICT (round,product) DO UPDATE SET offered=excluded.offered,'
                    'sold=excluded.sold,revenue=excluded.revenue,sellers=excluded.sellers')
        sql = re.sub(r'\bbsum\(', 'SUM(', sql).replace('?', '%s')
        try:
            if sql.startswith(('INSERT ', 'UPDATE ', 'DELETE ')) and self.connection.info.transaction_status == self.driver.pq.TransactionStatus.IDLE:
                self.connection.execute('BEGIN')
            return self.connection.execute(sql, params)
        except self.driver.IntegrityError as error:
            raise sqlite3.IntegrityError('PostgreSQL constraint violation') from error
        except self.driver.Error as error:
            raise sqlite3.OperationalError('PostgreSQL query failed') from error

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def close(self):
        try:
            if self.connection is not None:
                try:
                    if self.gate is not None:
                        self.connection.rollback()
                        self.connection.execute('SELECT pg_advisory_unlock_all()')
                except self.driver.Error:
                    self.connection.close()
                finally:
                    self.pool.putconn(self.connection)
                    self.connection = None
        finally:
            if self.gate is not None:
                self.gate.release()
                self.gate = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()

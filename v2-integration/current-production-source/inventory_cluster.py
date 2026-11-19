"""Shared health and automatic inventory settlement for the three Render roles."""
import sqlite3
import time

from accounts import Accounts, CLOSE_MS
from market import Game

CLASSES = {'A': (8, 8), 'B': (1, 4), 'C': (5, 7)}
HEARTBEAT_TTL = 30
DUE_PLAYERS = """
    SELECT p.id FROM (
        SELECT player, helper_tick AS tick FROM factories
        WHERE helper_product IS NOT NULL AND helper_tick <= ?
          AND helper_tick + 1000 <= helper_until
        UNION ALL
        SELECT player, tick FROM helpers WHERE tick <= ? OR until <= ?
        UNION ALL
        SELECT player, tick FROM autolines WHERE tick <= ?
    ) AS due JOIN players p ON p.id = due.player
    WHERE p.class_number BETWEEN ? AND ?
    GROUP BY p.id ORDER BY MIN(due.tick), p.id LIMIT 16
"""


class InventoryCluster:
    def __init__(self, path, role):
        if role not in CLASSES or not path.startswith(('postgresql://', 'postgres://')):
            raise ValueError('Inventory cluster requires PostgreSQL and role A, B or C')
        self.path = path
        self.role = role
        self.ready_until = 0.0
        self.play_enabled = False

    @property
    def ready(self):
        return time.monotonic() < self.ready_until

    def pulse(self):
        started = time.monotonic()
        account = Accounts(self.path, read_only=True, admin_only=True)
        try:
            with account.db:
                account.db.execute("""
                    INSERT INTO inventory_nodes(role, seen_at) VALUES (?, clock_timestamp())
                    ON CONFLICT (role) DO UPDATE SET seen_at = excluded.seen_at
                """, (self.role,))
                age = account.db.execute("""
                    SELECT COUNT(*), EXTRACT(EPOCH FROM clock_timestamp() - MIN(seen_at))
                    FROM inventory_nodes
                """).fetchone()
                setting = account.db.execute('SELECT maintenance FROM site_settings WHERE id=1').fetchone()
            self.play_enabled = setting is not None and not setting[0]
            self.ready_until = started + max(0, HEARTBEAT_TTL - float(age[1])) if age[0] == 3 else 0
        finally:
            account.db.close()

    def sync(self, still_running):
        now = int(time.time() * 1000)
        end = min(now, CLOSE_MS)
        account = Accounts(self.path, read_only=True)
        try:
            due = end - (1000 if now >= CLOSE_MS else 30000)
            rows = account.db.execute(DUE_PLAYERS, (due, due, end, due, *CLASSES[self.role])).fetchall()
            deadline = time.monotonic() + 4
            game = Game(account, read_only=True)
            for row in rows:
                if time.monotonic() >= deadline or not self.ready or not still_running():
                    break
                with account.db:
                    account.db.execute('BEGIN IMMEDIATE')
                    player = account.db.execute(
                        'SELECT id FROM players WHERE id=? FOR NO KEY UPDATE SKIP LOCKED',
                        (row['id'],),
                    ).fetchone()
                    if player:
                        game._helper(player['id'], now, locked=True)
        finally:
            account.db.close()

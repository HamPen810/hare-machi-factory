"""Administrator authentication and a read-only operations dashboard."""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

class Admin:
    def __init__(self,accounts,credential=None):
        self.db=accounts.db
        self.postgres=accounts.postgres
        self.credential=credential
        if credential is None:
            path=Path(__file__).with_name('admin-credential.json')
            if not self.postgres and path.exists():
                self.credential=json.loads(path.read_text())

    def initialize(self, maintenance):
        with self.db:
            self.db.execute('CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,expires_at BIGINT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS admin_attempts(id INTEGER PRIMARY KEY,failures INTEGER NOT NULL,blocked_until BIGINT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS frozen_players(player_id TEXT PRIMARY KEY REFERENCES players(id))')
            self.db.execute('CREATE TABLE IF NOT EXISTS site_settings(id INTEGER PRIMARY KEY,maintenance INTEGER NOT NULL,announcement TEXT NOT NULL)')
            self.db.execute('INSERT INTO admin_attempts VALUES(1,0,0) ON CONFLICT DO NOTHING')
            if self.postgres:
                self.db.execute('ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS announcement_revision BIGINT NOT NULL DEFAULT 0')
            elif not any(row['name']=='announcement_revision' for row in self.db.execute('PRAGMA table_info(site_settings)')):
                self.db.execute('ALTER TABLE site_settings ADD COLUMN announcement_revision INTEGER NOT NULL DEFAULT 0')
            self.db.execute('CREATE TABLE IF NOT EXISTS site_announcements(revision BIGINT PRIMARY KEY, body TEXT NOT NULL)')
            self.db.execute('CREATE TABLE IF NOT EXISTS site_rulebook(id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
            self.db.execute("INSERT INTO site_settings(id,maintenance,announcement) VALUES(1,?,'') ON CONFLICT DO NOTHING",(int(maintenance),))
            self.db.execute("""INSERT INTO site_announcements(revision,body)
                SELECT announcement_revision,announcement FROM site_settings
                WHERE id=1 AND announcement<>'' ON CONFLICT DO NOTHING""")
        return self.settings()

    def settings(self):
        row=self.db.execute('SELECT maintenance,announcement,announcement_revision FROM site_settings WHERE id=1').fetchone()
        history = [dict(entry) for entry in self.db.execute(
            'SELECT revision,body FROM site_announcements ORDER BY revision DESC')]
        rulebook = self.db.execute('SELECT body FROM site_rulebook WHERE id=1').fetchone()
        return {'maintenance':bool(row['maintenance']), 'announcement':row['announcement'],
                'announcement_revision':row['announcement_revision'], 'announcements':history,
                'rulebook':rulebook[0] if rulebook else ''}

    def update_settings(self, field, value):
        with self.db:
            if field=='maintenance' and type(value) is bool:
                self.db.execute('UPDATE site_settings SET maintenance=? WHERE id=1',(int(value),))
            elif field=='announcement' and isinstance(value,str) and 1<=len(value.strip())<=500:
                row = self.db.execute(
                    'UPDATE site_settings SET announcement=?,announcement_revision=announcement_revision+1 WHERE id=1 RETURNING announcement_revision',
                    (value.strip(),)).fetchone()
                self.db.execute('INSERT INTO site_announcements VALUES(?,?)',(row[0],value.strip()))
            elif field=='rulebook' and isinstance(value,str) and len(value)<=12000:
                self.db.execute('INSERT INTO site_rulebook VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                                (value.strip(),))
            else:
                raise ValueError('設定値を確認してください。')
        return self.settings()

    def player(self,student_id,operation):
        from accounts import eligible
        if not eligible(student_id) or operation not in ('freeze','unfreeze','reset'):
            raise ValueError('学籍番号と操作を確認してください。')
        self.db.execute('BEGIN IMMEDIATE')
        with self.db:
            if self.postgres and operation=='reset':
                self.db.execute('SELECT pg_advisory_xact_lock(CAST(? AS bigint))',(1042120,))
                self.db.execute('SELECT pg_advisory_xact_lock(CAST(? AS bigint))',(1042119,))
            lock=' FOR NO KEY UPDATE' if self.postgres else ''
            player=self.db.execute('SELECT id,display_name FROM players WHERE student_id=?'+lock,(student_id,)).fetchone()
            if player is None:
                raise ValueError('この学籍番号のアカウントがありません。')
            player_id=player['id']
            if operation=='unfreeze':
                self.db.execute('DELETE FROM frozen_players WHERE player_id=?',(player_id,))
            else:
                self.db.execute('DELETE FROM sessions WHERE player_id=?',(player_id,))
                if operation=='freeze':
                    self.db.execute('INSERT INTO frozen_players VALUES(?) ON CONFLICT DO NOTHING',(player_id,))
                else:
                    self.db.execute('DELETE FROM sales WHERE player_id=?',(player_id,))
                    for table in ('stock','actions','orders','listings','factory_totals','helpers',
                                  'equipment','autolines','auto_totals','rare_collection','rare_firsts',
                                  'market_ticks','factories'):
                        self.db.execute(f'DELETE FROM {table} WHERE player=?',(player_id,))
                    self.db.execute('DELETE FROM frozen_players WHERE player_id=?',(player_id,))
                    self.db.execute('DELETE FROM auth_attempts WHERE student_id=?',(student_id,))
                    self.db.execute('DELETE FROM players WHERE id=?',(player_id,))
        return {'display_name':player['display_name'],'operation':operation}

    def login(self,password,now):
        if not isinstance(password,str) or not 1<=len(password)<=128: raise ValueError('パスワードを確認してください。')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            lock=' FOR UPDATE' if self.postgres else ''
            row=self.db.execute('SELECT * FROM admin_attempts WHERE id=1'+lock).fetchone()
            if row['blocked_until']>now: raise ValueError('ログインが一時制限されています。1分後に再度お試しください。')
            configured=os.environ.get('HARE_FACTORY_ADMIN_PASSWORD')
            if configured:
                valid=hmac.compare_digest(password.encode(),configured.encode())
            elif self.credential:
                digest=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(self.credential['salt']),600000).hex()
                valid=hmac.compare_digest(digest,self.credential['hash'])
            else:
                raise ValueError('管理者パスワードが設定されていません。')
            if not valid:
                failures=(0 if row['blocked_until'] else row['failures'])+1
                self.db.execute('UPDATE admin_attempts SET failures=?,blocked_until=? WHERE id=1',(failures,now+60 if failures>=5 else 0))
                self.db.commit()
                raise ValueError('パスワードを確認してください。')
            token=secrets.token_urlsafe(32)
            self.db.execute('UPDATE admin_attempts SET failures=0,blocked_until=0 WHERE id=1')
            self.db.execute('DELETE FROM admin_sessions WHERE expires_at<=?',(now,))
            self.db.execute('INSERT INTO admin_sessions VALUES(?,?)',(hashlib.sha256(token.encode()).hexdigest(),now+3600))
            self.db.commit();return token
        except Exception:
            self.db.rollback();raise

    def authorized(self,token,now):
        return isinstance(token,str) and bool(self.db.execute('SELECT 1 FROM admin_sessions WHERE token_hash=? AND expires_at>?',(hashlib.sha256(token.encode()).hexdigest(),now)).fetchone())

    def logout(self,token):
        with self.db:self.db.execute('DELETE FROM admin_sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def dashboard(self,game):
        rankings=game.accounts.rankings_many(('manufactured','net_profit','revenue'))
        scores={m:{r['id']:r[m] for r in board['individual']} for m,board in rankings.items()}
        players=[]
        for r in self.db.execute('''SELECT p.id,p.student_id,p.display_name,p.class_number,
                COALESCE(f.cash,500) cash,COALESCE(f.tier,0) tier
                FROM players p LEFT JOIN factories f ON f.player=p.id ORDER BY p.student_id'''):
            row=dict(r)
            for m in scores:row[m]=scores[m][row['id']]
            row['stock']=[dict(s) for s in self.db.execute('SELECT product,quantity FROM stock WHERE player=?',(row['id'],))]
            players.append(row)
        pending=[dict(r) for r in self.db.execute('''SELECT o.id,p.display_name,p.student_id,o.product,o.quantity,o.price,o.round
                FROM listings o JOIN players p ON p.id=o.player ORDER BY o.accepted''')]
        return {'now':game.clock(),'event':game.event(),'players':players,'pending':pending,'rankings':rankings,
                'market':game.history(),'summary':{'players':len(players),'manufactured':sum(p['manufactured'] for p in players),
                'revenue':sum(p['revenue'] for p in players),'net_profit':sum(p['net_profit'] for p in players),
                'pending_shipments':len(pending),'settled_rounds':self.db.execute('SELECT COUNT(*) FROM rounds').fetchone()[0]}}

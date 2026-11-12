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
            self.db.execute('CREATE TABLE IF NOT EXISTS admin_extra_slots('
                            'student_id TEXT PRIMARY KEY,class_number INTEGER NOT NULL '
                            'CHECK(class_number BETWEEN 1 AND 8),created_at BIGINT NOT NULL)')
            self.initialize_online(self.db)
            from admin_fund_ops import install
            install(self.db)
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
            self.db.execute("""CREATE TABLE IF NOT EXISTS admin_fund_transfers(
                key TEXT PRIMARY KEY,
                player_id TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                student_id TEXT NOT NULL, name TEXT NOT NULL,
                kind TEXT NOT NULL, amount NUMERIC NOT NULL,
                before_cash NUMERIC NOT NULL, after_cash NUMERIC NOT NULL,
                note TEXT NOT NULL, created_at BIGINT NOT NULL)""")
            self.db.execute("INSERT INTO site_settings(id,maintenance,announcement) VALUES(1,?,'') ON CONFLICT DO NOTHING",(int(maintenance),))
            self.db.execute("""INSERT INTO site_announcements(revision,body)
                SELECT announcement_revision,announcement FROM site_settings
                WHERE id=1 AND announcement<>'' ON CONFLICT DO NOTHING""")
        return self.settings()

    @staticmethod
    def initialize_online(db):
        db.execute('CREATE TABLE IF NOT EXISTS online_presence('
                   'player_id TEXT PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,'
                   'seen_at BIGINT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS online_samples('
                   'minute BIGINT PRIMARY KEY,online_count INTEGER NOT NULL)')

    @staticmethod
    def note_online(db,player_id,now):
        db.execute('INSERT INTO online_presence(player_id,seen_at) VALUES(?,?) '
                   'ON CONFLICT(player_id) DO UPDATE SET seen_at=excluded.seen_at',
                   (player_id,now))

    @staticmethod
    def sample_online(db,now):
        # One evenly spaced sample for each minute while service is active.
        # The query counts only unique accounts seen during the previous 120s.
        minute=now//60000
        count=db.execute(
            'SELECT COUNT(*) FROM online_presence WHERE seen_at>=? AND seen_at<=?',
            (now-120000,now)).fetchone()[0]
        db.execute('INSERT INTO online_samples(minute,online_count) VALUES(?,?) '
                   'ON CONFLICT(minute) DO UPDATE SET online_count=excluded.online_count',
                   (minute,count))
        # A bounded 24-hour chart with two days' retention to avoid DB growth.
        db.execute('DELETE FROM online_samples WHERE minute<?',(minute-2880,))
        db.execute('DELETE FROM online_presence WHERE seen_at<?',(now-86400000,))
        return count

    def online_stats(self,now):
        count=self.db.execute(
            'SELECT COUNT(*) FROM online_presence WHERE seen_at>=? AND seen_at<=?',
            (now-120000,now)).fetchone()[0]
        records=[{'minute':int(row['minute']),'count':int(row['online_count'])}
                 for row in self.db.execute(
                     'SELECT minute,online_count FROM online_samples '
                     'WHERE minute>=? ORDER BY minute', (now//60000-1440,))]
        return {'online':int(count),'sampled_at':now,'window_seconds':120,
                'samples':records}

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

    def extra_slots(self):
        return [dict(r) for r in self.db.execute(
            'SELECT s.student_id,s.class_number,s.created_at,'
            'p.display_name FROM admin_extra_slots s '
            'LEFT JOIN players p ON p.student_id=s.student_id '
            'ORDER BY s.student_id')]

    def manage_extra_slot(self,student_id,class_number,operation,now):
        from accounts import eligible
        if not isinstance(student_id,str) or len(student_id)!=4 or not student_id.isascii() or not student_id.isdigit():
            raise ValueError('学籍番号は数字4桁で指定してください。')
        if eligible(student_id):
            raise ValueError('通常の登録可能範囲にある番号は、追加枠には登録できません。')
        if operation not in ('add','remove'):
            raise ValueError('操作の種類を確認してください。')
        if operation=='add' and (type(class_number) is not int or not 1<=class_number<=8):
            raise ValueError('所属するクラスは1～8組を選択してください。')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.postgres:
                self.db.execute('SELECT pg_advisory_xact_lock(CAST(? AS bigint))',(1042119,))
            registered=self.db.execute(
                'SELECT 1 FROM players WHERE student_id=?',(student_id,)).fetchone()
            existing=self.db.execute(
                'SELECT class_number FROM admin_extra_slots WHERE student_id=?',
                (student_id,)).fetchone()
            if operation=='add':
                if existing:
                    raise ValueError('この番号は既に追加されています。')
                if registered:
                    raise ValueError('この学籍番号は既に使用されています。')
                self.db.execute(
                    'INSERT INTO admin_extra_slots(student_id,class_number,created_at) '
                    'VALUES(?,?,?)',(student_id,class_number,now))
            else:
                if not existing:
                    raise ValueError('追加枠に存在しない番号です。')
                if registered:
                    raise ValueError('登録済みアカウントがあるため削除できません。')
                self.db.execute('DELETE FROM admin_extra_slots WHERE student_id=?',
                                (student_id,))
            self.db.commit()
            return {'student_id':student_id,'operation':operation,
                    'class_number':class_number if operation=='add' else None}
        except Exception:
            self.db.rollback()
            raise

    def player(self,student_id,operation):
        from accounts import eligible
        if not eligible(student_id,self.db) or operation not in ('freeze','unfreeze','reset'):
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

    def fund_players(self):
        return [dict(row) for row in self.db.execute(
            'SELECT p.student_id,p.display_name,COALESCE(f.cash,500) cash '
            'FROM players p LEFT JOIN factories f ON f.player=p.id '
            'ORDER BY p.student_id')]

    def fund_history(self):
        self.db.execute("""CREATE TABLE IF NOT EXISTS admin_fund_transfers(
            key TEXT PRIMARY KEY,
            player_id TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            student_id TEXT NOT NULL, name TEXT NOT NULL,
            kind TEXT NOT NULL, amount NUMERIC NOT NULL,
            before_cash NUMERIC NOT NULL, after_cash NUMERIC NOT NULL,
            note TEXT NOT NULL, created_at BIGINT NOT NULL)""")
        return [dict(r) for r in self.db.execute(
            'SELECT key,student_id,name,kind,amount,before_cash,after_cash,note,created_at '
            'FROM admin_fund_transfers ORDER BY created_at DESC,key DESC LIMIT 50')]

    def fund_transfer(self, student_id, kind, amount, note, key, now):
        from accounts import eligible
        from bank import integer
        if not eligible(student_id,self.db):
            raise ValueError('正しい学籍番号を指定してください。')
        if kind not in ('collect','grant'):
            raise ValueError('資金操作の種類を指定してください。')
        amount=integer(amount,1)
        if not isinstance(key,str) or not 16<=len(key)<=80 or not key.isascii() or not all(
            ch.isalnum() or ch in '-_' for ch in key):
            raise ValueError('操作IDが不正です。')
        if not isinstance(note,str) or len(note.strip())>160:
            raise ValueError('理由は160文字以内で指定してください。')
        note=note.strip()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            # Serialize against all normal game transactions in Postgres.
            if self.postgres:
                self.db.execute('SELECT pg_advisory_xact_lock(CAST(? AS bigint))',(1042119,))
            self.db.execute("""CREATE TABLE IF NOT EXISTS admin_fund_transfers(
                key TEXT PRIMARY KEY,
                player_id TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                student_id TEXT NOT NULL, name TEXT NOT NULL,
                kind TEXT NOT NULL, amount NUMERIC NOT NULL,
                before_cash NUMERIC NOT NULL, after_cash NUMERIC NOT NULL,
                note TEXT NOT NULL, created_at BIGINT NOT NULL)""")
            previous=self.db.execute(
                'SELECT student_id,kind,amount,note,before_cash,after_cash,name '
                'FROM admin_fund_transfers WHERE key=?',(key,)).fetchone()
            if previous:
                if (previous['student_id'],previous['kind'],int(previous['amount']),previous['note']) != (
                    student_id,kind,amount,note):
                    raise ValueError('この操作IDは別の処理に使われています。')
                self.db.rollback()
                return {'display_name':previous['name'],'kind':kind,'amount':amount,
                        'before_cash':previous['before_cash'],'after_cash':previous['after_cash'],
                        'already_applied':True}
            lock=' FOR NO KEY UPDATE' if self.postgres else ''
            player=self.db.execute(
                'SELECT p.id,p.display_name,f.cash FROM players p '
                'JOIN factories f ON f.player=p.id WHERE p.student_id=?'+lock,
                (student_id,)).fetchone()
            if not player:
                raise ValueError('対象アカウントまたは工場が見つかりません。')
            previous_cash=int(player['cash'])
            new_cash=previous_cash + (amount if kind=='grant' else -amount)
            if kind=='grant':
                self.db.execute('UPDATE factories SET cash=badd(cash,?) WHERE player=?',
                                (amount,player['id']))
            else:
                # Admin collection is allowed to overdraw; one atomic debit.
                updated=self.db.execute(
                    'UPDATE factories SET cash=bsub(cash,?) WHERE player=?',
                    (amount,player['id']))
                if updated.rowcount!=1:
                    raise ValueError('対象工場が見つかりません。')
            self.db.execute(
                'INSERT INTO admin_fund_transfers(key,player_id,student_id,name,kind,amount,'
                'before_cash,after_cash,note,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (key,player['id'],student_id,player['display_name'],kind,
                 amount,previous_cash,new_cash,note,now))
            self.db.commit()
            return {'display_name':player['display_name'],'kind':kind,'amount':amount,
                    'before_cash':previous_cash,'after_cash':new_cash,'already_applied':False}
        except Exception:
            self.db.rollback()
            raise

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

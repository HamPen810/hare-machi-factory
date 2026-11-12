"""Local server-domain prototype. No public HTTP endpoints or production deployment."""
from exact import setup
import bank
import hashlib
import hmac
import secrets
import sqlite3
import time
from datetime import datetime

CLOSE_MS = int(datetime.fromisoformat('2026-11-19T20:00:00+09:00').timestamp()*1000)

def eligible(student_id):
    if not isinstance(student_id,str) or len(student_id)!=4 or not student_id.isascii() or not student_id.isdigit():
        return False
    return student_id[0]=='2' and student_id[1] in '12345678' and 1<=int(student_id[2:])<=(41 if student_id[1]=='8' else 40)

class Accounts:
    def __init__(self,path, *, auth_only=False, read_only=False, admin_only=False):
        self.dummy_salt=secrets.token_bytes(16)
        self.postgres=isinstance(path,str) and path.startswith(('postgresql://','postgres://'))
        if self.postgres:
            from postgres import Postgres
            self.db=Postgres(path, auth_only=auth_only, read_only=read_only, admin_only=admin_only)
            return
        self.db=sqlite3.connect(path)
        setup(self.db)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS players (
          id TEXT PRIMARY KEY, student_id TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL, class_number INTEGER NOT NULL CHECK(class_number BETWEEN 1 AND 8),
          salt BLOB NOT NULL, password_hash BLOB NOT NULL, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS frozen_players(player_id TEXT PRIMARY KEY REFERENCES players(id));
        CREATE TABLE IF NOT EXISTS sessions (
          token_hash TEXT PRIMARY KEY, player_id TEXT NOT NULL REFERENCES players(id), expires_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS auth_attempts (
          student_id TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0, blocked_until INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sales (
          settlement_id TEXT PRIMARY KEY, player_id TEXT NOT NULL REFERENCES players(id),
          product_id TEXT NOT NULL, sold_quantity INTEGER NOT NULL CHECK(sold_quantity>=0),
          unit_price INTEGER NOT NULL CHECK(unit_price>0), unit_cost INTEGER NOT NULL CHECK(unit_cost>=0),
          accepted_at INTEGER NOT NULL, settled_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS sales_player ON sales(player_id);
        CREATE TABLE IF NOT EXISTS factory_totals (
          player TEXT PRIMARY KEY REFERENCES players(id),
          manufactured INTEGER NOT NULL DEFAULT 0 CHECK(manufactured>=0),
          purchases INTEGER NOT NULL DEFAULT 0 CHECK(purchases>=0));
        ''')

        bank.initialize(self.db)

    @staticmethod
    def _hash(password,salt):
        return hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),salt,600000)

    def register(self,name,student_id,password,now=None):
        now=int(time.time()) if now is None else now
        if not eligible(student_id):raise ValueError('登録対象外の学籍番号です。')
        if not isinstance(name,str) or not 1<=len(name.strip())<=40:raise ValueError('名前は1〜40文字です。')
        if not isinstance(password,str) or not (len(password)==6 and password.isascii() and password.isdigit()):raise ValueError('パスワードは数字6桁で入力してください。')
        salt=secrets.token_bytes(16);digest=self._hash(password,salt);pid=secrets.token_hex(16)
        try:
            with self.db:
                self.db.execute('INSERT INTO players VALUES(?,?,?,?,?,?,?)',(pid,student_id,name.strip(),int(student_id[1]),salt,digest,now))
        except sqlite3.IntegrityError as exc:
            raise ValueError('この学籍番号では登録できません。') from exc
        return pid

    def login(self,student_id,password,now=None):
        now=int(time.time()) if now is None else now
        if not isinstance(password,str) or not (len(password)==6 and password.isascii() and password.isdigit()) or not eligible(student_id):raise ValueError('ログイン情報を確認してください。')
        user=self.db.execute('''SELECT p.id,p.salt,p.password_hash,a.failures,a.blocked_until
            FROM (SELECT CAST(? AS TEXT) AS student_id) requested
            LEFT JOIN players p ON p.student_id=requested.student_id
                AND NOT EXISTS (SELECT 1 FROM frozen_players f WHERE f.player_id=p.id)
            LEFT JOIN auth_attempts a ON a.student_id=requested.student_id''',(student_id,)).fetchone()
        if (user['blocked_until'] or 0)>now:raise ValueError('時間をおいて再度お試しください。')
        digest=self._hash(password,user['salt'] if user['id'] else self.dummy_salt)
        valid=user['id'] is not None and hmac.compare_digest(digest,user['password_hash'])
        if not valid:
            failures=(user['failures'] or 0)+1
            with self.db:
                self.db.execute('INSERT INTO auth_attempts VALUES(?,?,?) ON CONFLICT(student_id) DO UPDATE SET failures=excluded.failures,blocked_until=excluded.blocked_until',(student_id,failures,now+60 if failures>=5 else 0))
            raise ValueError('ログイン情報を確認してください。')
        token=secrets.token_urlsafe(32)
        with self.db:
            if user['failures'] is not None:
                self.db.execute('DELETE FROM auth_attempts WHERE student_id=?',(student_id,))
            self.db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],now+86400))
        return token

    def identity(self,token,now=None):
        now=int(time.time()) if now is None else now
        if not isinstance(token,str):raise ValueError('ログインが必要です。')
        row=self.db.execute('SELECT p.id,p.display_name,p.class_number FROM players p JOIN sessions s ON s.player_id=p.id WHERE s.token_hash=? AND s.expires_at>? AND NOT EXISTS (SELECT 1 FROM frozen_players f WHERE f.player_id=p.id)',(hashlib.sha256(token.encode()).hexdigest(),now)).fetchone()
        if not row:raise ValueError('ログインが必要です。')
        return dict(row)

    def logout(self,token):
        with self.db:self.db.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(token.encode()).hexdigest(),))

    def record_server_settlement(self,settlement_id,player_id,product_id,quantity,price,cost,accepted_at,settled_at):
        """Trusted market-engine input ONLY. Must never be exposed as a client write API."""
        if any(type(x) is not int for x in [quantity,price,cost,accepted_at,settled_at]):raise ValueError('整数が必要です。')
        if not quantity>=0 or not 1<=price<=99999 or not 0<=cost<=99999:raise ValueError('金額または数量が範囲外です。')
        if accepted_at>=CLOSE_MS or accepted_at>settled_at:raise ValueError('受付時刻が対象外です。')
        values=(settlement_id,player_id,product_id,quantity,price,cost,accepted_at,settled_at)
        with self.db:
            existing=self.db.execute('SELECT * FROM sales WHERE settlement_id=?',(settlement_id,)).fetchone()
            if existing:
                if tuple(existing)!=values:raise ValueError('同じ精算IDの内容が一致しません。')
                return False
            self.db.execute('INSERT INTO sales VALUES(?,?,?,?,?,?,?,?)',values)
        return True

    def rankings(self,metric='revenue'):
        return self.rankings_many((metric,))[metric]

    def rankings_many(self,metrics):
        people={row['id']:dict(row) for row in self.db.execute('SELECT id,display_name,class_number FROM players')}
        for person in people.values():
            person.update(revenue=0,manufactured=0,net_profit=0)
        for row in self.db.execute('SELECT player,manufactured,purchases FROM factory_totals'):
            if row['player'] in people:
                person=people[row['player']]
                person['manufactured']=row['manufactured']
                person['net_profit']=-row['purchases']
        if self.postgres:
            sales = self.db.execute('''SELECT player_id, SUM(sold_quantity*unit_price) revenue,
                SUM(sold_quantity*(unit_price-unit_cost)) profit FROM sales GROUP BY player_id''')
            for row in sales:
                if row['player_id'] in people:
                    people[row['player_id']]['revenue'] = row['revenue']
                    people[row['player_id']]['net_profit'] += row['profit']
            return {metric:self._rank(people.values(),metric) for metric in metrics}
        for row in self.db.execute('SELECT player_id,sold_quantity,unit_price,unit_cost FROM sales'):
            if row['player_id'] in people:
                person=people[row['player_id']]
                person['revenue']+=row['sold_quantity']*row['unit_price']
                person['net_profit']+=row['sold_quantity']*(row['unit_price']-row['unit_cost'])
        return {metric:self._rank(people.values(),metric) for metric in metrics}

    def _rank(self,people,metric):
        if metric not in ('revenue','manufactured','net_profit'):
            raise ValueError('ランキング指標が不正です。')
        # Public cumulative profit is requested; per-shipment margins stay private.
        people=[{k:p[k] for k in ('id','display_name','class_number',metric)} for p in people]
        people.sort(key=lambda p:(-p[metric],p['id']))
        classes=[{'class_number':i,metric:sum(p[metric] for p in people if p['class_number']==i)} for i in range(1,9)]
        classes.sort(key=lambda x:(-x[metric],x['class_number']))
        for rows in [people,classes]:
            previous=None;rank=0
            for position,row in enumerate(rows,1):
                if row[metric]!=previous:rank=position
                previous=row[metric];row['rank']=rank
        return {'metric':metric,'individual':people,'classes':classes}

    def own_history(self,token,now=None):
        player=self.identity(token,now)
        if not self.postgres:
            return [{**dict(row), 'revenue': row['sold_quantity']*row['unit_price'],
                     'material_cost':row['sold_quantity']*row['unit_cost'],
                     'margin':(row['unit_price']-row['unit_cost'])/row['unit_price']}
                    for row in self.db.execute('''SELECT product_id,sold_quantity,unit_price,unit_cost,
                      accepted_at,settled_at FROM sales WHERE player_id=? ORDER BY settled_at DESC''',(player['id'],))]
        return [dict(row) for row in self.db.execute('''SELECT product_id,sold_quantity,unit_price,
          sold_quantity*unit_price revenue,sold_quantity*unit_cost material_cost,
          CASE WHEN sold_quantity=0 THEN NULL ELSE (unit_price-unit_cost)*1.0/unit_price END margin,
          accepted_at,settled_at FROM sales WHERE player_id=? ORDER BY settled_at DESC''',(player['id'],))]

"""Audited administrator debt forgiveness and wealth-filtered batch operations.

Only callable from the authenticated administrator API. All transfers and
cancellations are atomic, signed cash amounts remain exact, previews bind
to a current-state digest, and repeated keys never apply twice.
"""
import hashlib
import json
from bank import integer
from market import PRODUCTS

def install(db):
    db.execute("""CREATE TABLE IF NOT EXISTS admin_fund_batches(
        key TEXT PRIMARY KEY,
        payload TEXT NOT NULL,
        result TEXT NOT NULL,
        created_at BIGINT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS admin_debt_cancellations(
        key TEXT PRIMARY KEY,
        player_id TEXT NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        student_id TEXT NOT NULL,
        name TEXT NOT NULL,
        debt NUMERIC NOT NULL,
        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""")

def _digits(value, *, optional=False):
    if optional and (value is None or value==''):
        return None
    if isinstance(value,str) and value.startswith('-'):
        return -integer(value[1:],0)
    return integer(value,0)

def validate(data):
    if not isinstance(data,dict):
        raise ValueError('資金操作の形式が不正です。')
    kind=data.get('kind')
    scope=data.get('scope')
    if kind not in ('grant','collect','forgive') or scope not in ('single','bulk'):
        raise ValueError('操作方法を指定してください。')
    note=data.get('note','')
    if not isinstance(note,str) or len(note.strip())>160:
        raise ValueError('理由は160文字以内にしてください。')
    result={'scope':scope,'kind':kind,'note':note.strip()}
    if scope=='single':
        from accounts import eligible
        student=data.get('student_id')
        # Extra slots are resolved in plan() against the current database.
        if not isinstance(student,str) or len(student)!=4 or not student.isascii() or not student.isdigit():
            raise ValueError('正しい学籍番号4桁を入力してください。')
        if kind!='forgive':
            raise ValueError('個人の補助金・徴収は従来の操作画面から実行してください。')
        result['student_id']=student
    else:
        lo=_digits(data.get('min_assets'),optional=True)
        hi=_digits(data.get('max_assets'),optional=True)
        if lo is not None and hi is not None and lo>hi:
            raise ValueError('財産の下限は上限以下にしてください。')
        result['min_assets']=str(lo) if lo is not None else ''
        result['max_assets']=str(hi) if hi is not None else ''
        if kind!='forgive':
            mode=data.get('amount_mode','fixed')
            if mode not in ('fixed','percent'):
                raise ValueError('金額の指定方法が不正です。')
            result['amount_mode']=mode
            if mode=='fixed':
                result['amount']=str(integer(data.get('amount'),1))
            else:
                # Percentage is expressed in 1/100ths of a percent.
                result['percentage_bps']=integer(data.get('percentage_bps'),1,10000)
    return result

def _players(db,postgres):
    # Match bank.asset_tax valuation: cash + scheduled deposit payout +
    # stock and offered listings at their normal catalog prices.
    rows=[dict(row) for row in db.execute(
        """SELECT p.id,p.student_id,p.display_name,f.cash,
                  COALESCE(b.deposit,0) AS deposit, COALESCE(b.debt,0) AS debt
           FROM players p JOIN factories f ON f.player=p.id
           LEFT JOIN bank_accounts b ON b.player=p.id
           ORDER BY p.id""")]
    people={p['id']:{
        'player_id':p['id'],'student_id':p['student_id'],
        'name':p['display_name'],'cash':int(p['cash']),
        'deposit':int(p['deposit']),'debt':int(p['debt']),
        'assets':int(p['cash'])+int(p['deposit'])
    } for p in rows}
    for r in db.execute(
        """SELECT player,product,quantity FROM stock
           UNION ALL SELECT player,product,quantity FROM listings WHERE player<>?""",
        ('@bank',)):
        p=people.get(r['player'])
        if p and r['product'] in PRODUCTS:
            p['assets']+=int(r['quantity'])*PRODUCTS[r['product']][1]
    return list(people.values())

def plan(db,postgres,payload):
    players=_players(db,postgres)
    if payload['scope']=='single':
        players=[p for p in players if p['student_id']==payload['student_id']]
        if not players: raise ValueError('対象のアカウントがありません。')
    else:
        lo=_digits(payload['min_assets'],optional=True)
        hi=_digits(payload['max_assets'],optional=True)
        players=[p for p in players if
                 (lo is None or p['assets']>=lo) and
                 (hi is None or p['assets']<=hi)]
    entries=[]
    for p in players:
        if payload['kind']=='forgive':
            amt=p['debt']
        elif payload['amount_mode']=='fixed':
            amt=int(payload['amount'])
        else:
            amt=max(0,p['assets'])*payload['percentage_bps']//10000
        if amt<=0:continue
        # Prevent ambiguous zero-amount audit records.
        entries.append({'player_id':p['player_id'],'student_id':p['student_id'],
                        'name':p['name'],'assets':p['assets'],'cash':p['cash'],
                        'debt':p['debt'],'amount':amt,
                        'after_cash':p['cash'] + (
                            amt if payload['kind']=='grant' else
                            -amt if payload['kind']=='collect' else 0)})
    if len(entries)>400:
        raise ValueError('対象が400人を超えています。対象条件を絞ってください。')
    if not entries:
        raise ValueError('条件に合う操作対象者がいません。')
    snapshot=json.dumps(entries,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    digest=hashlib.sha256(
        (json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':'))+
         ':'+snapshot).encode()).hexdigest()
    return {'count':len(entries),'total':sum(p['amount'] for p in entries),
            'people':entries,'digest':digest}

def _key(value):
    return (isinstance(value,str) and 16<=len(value)<=60 and value.isascii()
            and all(c.isalnum() or c in '-_' for c in value))

def perform(admin,data,now):
    db=admin.db
    postgres=admin.postgres
    action=data.get('action')
    if action not in ('preview','apply'):
        raise ValueError('操作を指定してください。')
    payload=validate(data)
    if action=='preview':
        result=plan(db,postgres,payload)
        # JSON exact values use strings at the API boundary through wire().
        return {'ok':True,'scope':payload['scope'],'kind':payload['kind'],**result}
    key=data.get('key')
    digest=data.get('preview_digest')
    if not _key(key) or not isinstance(digest,str) or len(digest)!=64:
        raise ValueError('操作IDまたは事前確認情報が不正です。')
    encoded=json.dumps({'request':payload,'digest':digest},
                       ensure_ascii=False,sort_keys=True,separators=(',',':'))
    db.execute('BEGIN IMMEDIATE')
    try:
        if postgres:
            db.execute('SELECT pg_advisory_xact_lock(CAST(? AS bigint))',(1042119,))
        previous=db.execute('SELECT payload,result FROM admin_fund_batches WHERE key=?',
                            (key,)).fetchone()
        if previous:
            if previous['payload']!=encoded:
                raise ValueError('この操作IDは別の処理に使用されています。')
            db.rollback()
            return {**json.loads(previous['result']),'already_applied':True}
        # Lock all player rows before asset snapshot and writes, in canonical
        # order (and serialize normal bank/game action writers).
        if postgres:
            db.execute('SELECT id FROM players ORDER BY id FOR NO KEY UPDATE').fetchall()
        try:
            snapshot=plan(db,postgres,payload)
        except ValueError as error:
            if '条件に合う操作対象者がいません' in str(error):
                raise ValueError('確認後に対象者が変わりました。もう一度試算してください。') from error
            raise
        if snapshot['digest']!=digest:
            raise ValueError('確認後に資産や対象者が変わりました。もう一度試算してください。')
        if payload['kind']=='forgive':
            import bank
            bank._ensure_contracts(db)
        for i,p in enumerate(snapshot['people']):
            player=p['player_id']
            amount=p['amount']
            if payload['kind']=='grant':
                db.execute('UPDATE factories SET cash=badd(cash,?) WHERE player=?',
                           (amount,player))
            elif payload['kind']=='collect':
                db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=?',
                           (amount,player))
            else:
                # All borrowing contracts are cancelled; deposits remain intact.
                db.execute("DELETE FROM bank_contracts WHERE player=? AND kind='borrow'",
                           (player,))
                db.execute('UPDATE bank_accounts SET debt=0 WHERE player=?',(player,))
            if payload['kind']=='forgive':
                db.execute('INSERT INTO admin_debt_cancellations'
                           '(key,player_id,student_id,name,debt,note,created_at)'
                           ' VALUES(?,?,?,?,?,?,?)',
                           (key+'-'+str(i),player,p['student_id'],p['name'],amount,
                            payload['note'],now))
            else:
                # Same audit ledger as individual transactions, so collection
                # enters expense and net-profit exactly once.
                db.execute('INSERT INTO admin_fund_transfers'
                           '(key,player_id,student_id,name,kind,amount,'
                           'before_cash,after_cash,note,created_at)'
                           ' VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (key+'-'+str(i),player,p['student_id'],p['name'],
                            payload['kind'],amount,p['cash'],p['after_cash'],
                            payload['note'],now))
        result={'ok':True,'count':snapshot['count'],'total':snapshot['total'],
                'kind':payload['kind'],'scope':payload['scope'],
                'people':snapshot['people'],'already_applied':False}
        db.execute('INSERT INTO admin_fund_batches(key,payload,result,created_at)'
                   ' VALUES(?,?,?,?)',
                   (key,encoded,json.dumps(result,ensure_ascii=False),now))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise

def history(db):
    return [dict(r) for r in db.execute(
        'SELECT student_id,name,debt,note,created_at FROM '
        'admin_debt_cancellations ORDER BY created_at DESC,key DESC LIMIT 50')]

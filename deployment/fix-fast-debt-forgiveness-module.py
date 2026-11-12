"""Fast, transaction-safe admin debt forgiveness.

No global advisory lock and no full-player FOR UPDATE scan. For a single
player, both the preview and the actual operation touch only that player.
The actual bank/cash amounts are recalculated under the row lock at COMMIT
time; the preview digest is never used to reject a changed amount.
"""
import hashlib
import json
from admin_fund_ops import plan

def _digest(payload, entries):
    raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    raw+=':'+json.dumps(entries,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    return hashlib.sha256(raw.encode('utf8')).hexdigest()

def _entry(row, debt):
    cash=int(row['cash'])
    recovered=max(0,-cash)
    return dict(
        player_id=row['id'],student_id=row['student_id'],
        name=row['display_name'],assets=cash+int(row['deposit']),
        cash=cash,debt=debt,amount=debt,cash_restored=recovered,
        after_cash=max(0,cash))

def _single(db,payload, allow_empty=False):
    row=db.execute(
        'SELECT p.id,p.student_id,p.display_name,f.cash,'
        'COALESCE(b.deposit,0) AS deposit, COALESCE(b.debt,0) AS debt '
        'FROM players p JOIN factories f ON f.player=p.id '
        'LEFT JOIN bank_accounts b ON b.player=p.id '
        'WHERE p.student_id=?',(payload['student_id'],)).fetchone()
    if row is None:raise ValueError('対象のアカウントがありません。')
    contract_debt=db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM bank_contracts "
        "WHERE player=? AND kind='borrow'",(row['id'],)).fetchone()[0]
    debt=max(int(row['debt']),int(contract_debt))
    entry=_entry(row,debt)
    entries=[entry] if debt>0 or entry['cash_restored']>0 else []
    if not entries and not allow_empty:
        raise ValueError('このアカウントには銀行借入もマイナス残高もありません。')
    return _summary(payload,entries)

def _summary(payload,entries):
    return dict(
        count=len(entries),
        total=sum(x['amount'] for x in entries),
        cash_restored_total=sum(x['cash_restored'] for x in entries),
        people=entries,
        digest=_digest(payload,entries))

def _bulk(db,postgres,payload,allow_empty=False):
    # In a batch, maintain the original valuation/filtering behavior.
    try:
        result=plan(db,postgres,payload)
    except ValueError as error:
        if allow_empty and '条件に合う操作対象者がいません' in str(error):
            return _summary(payload,[])
        raise
    return result

def _snapshot(db,postgres,payload,allow_empty=False):
    if payload['scope']=='single':
        return _single(db,payload,allow_empty)
    return _bulk(db,postgres,payload,allow_empty)

def _get_existing(db,key,encoded):
    prior=db.execute(
        'SELECT payload,result FROM admin_fund_batches WHERE key=?',
        (key,)).fetchone()
    if prior is None:return None
    if prior['payload']!=encoded:
        raise ValueError('この操作IDは別の処理に使用されています。')
    return {**json.loads(prior['result']),'already_applied':True}

def _lock(db,ids,postgres):
    # Acquire only affected factory rows in stable order.
    if postgres:
        for player in sorted(set(ids)):
            db.execute('SELECT player FROM factories WHERE player=? FOR UPDATE',
                       (player,)).fetchone()

def execute(admin,payload,data,now):
    from admin_fund_ops import _key
    db=admin.db
    postgres=admin.postgres
    action=data.get('action')
    if action=='preview':
        snap=_snapshot(db,postgres,payload)
        return {'ok':True,'scope':payload['scope'],'kind':'forgive',**snap}
    if action!='apply':
        raise ValueError('操作を指定してください。')
    key=data.get('key')
    digest=data.get('preview_digest')
    if not _key(key) or not isinstance(digest,str) or len(digest)!=64:
        raise ValueError('操作IDまたは事前確認情報が不正です。')
    encoded=json.dumps({'request':payload,'digest':digest},
                       sort_keys=True,ensure_ascii=False,separators=(',',':'))
    db.execute('BEGIN IMMEDIATE')
    try:
        result=_get_existing(db,key,encoded)
        if result:
            db.rollback()
            return result

        # Do NOT acquire the game-wide PostgreSQL advisory lock (1042119)
        # and DO NOT lock all players. These previously stalled when gameplay
        # and bank operations were active.
        if payload['scope']=='single':
            player=db.execute(
                'SELECT id FROM players WHERE student_id=?',
                (payload['student_id'],)).fetchone()
            if player is None:
                raise ValueError('対象のアカウントがありません。')
            _lock(db,[player['id']],postgres)
        else:
            early=_snapshot(db,postgres,payload,allow_empty=True)
            _lock(db,[p['player_id'] for p in early['people']],postgres)

        # Snapshot is deliberately refreshed after locking. A change since
        # preview is expected, not an error, for forgiveness.
        actual=_snapshot(db,postgres,payload,allow_empty=True)
        if payload['scope']=='bulk' and postgres:
            # If eligibility changed, lock the newly included rows as well.
            locked={p['player_id'] for p in early['people']}
            for _ in range(3):
                added={p['player_id'] for p in actual['people']} - locked
                if not added:break
                _lock(db,added,postgres)
                locked.update(added)
                actual=_snapshot(db,postgres,payload,allow_empty=True)
            if {p['player_id'] for p in actual['people']}-locked:
                raise ValueError('対象者が変更されました。一括操作をやり直してください。')

        for index,entry in enumerate(actual['people']):
            player=entry['player_id']
            db.execute(
                "DELETE FROM bank_contracts WHERE player=? AND kind='borrow'",
                (player,))
            db.execute('UPDATE bank_accounts SET debt=0 WHERE player=?',
                       (player,))
            # Compare in DB as well as in preview; a positive balance is
            # never reduced to zero. Includes balances beyond 64-bit integer.
            db.execute('UPDATE factories SET cash=0 '
                       'WHERE player=? AND bge(0,cash)',(player,))
            item_key=key+'-'+str(index)
            db.execute(
                'INSERT INTO admin_debt_cancellations'
                '(key,player_id,student_id,name,debt,note,created_at)'
                ' VALUES(?,?,?,?,?,?,?)',
                (item_key,player,entry['student_id'],entry['name'],
                 entry['amount'],payload['note'],now))
            db.execute(
                'INSERT INTO admin_overdraft_cancellations'
                '(key,cash_restored,created_at) VALUES(?,?,?)',
                (item_key,entry['cash_restored'],now))

        out={'ok':True,'kind':'forgive','scope':payload['scope'],
             'count':actual['count'],'total':actual['total'],
             'cash_restored_total':actual['cash_restored_total'],
             'people':actual['people'],'already_applied':False}
        db.execute(
            'INSERT INTO admin_fund_batches(key,payload,result,created_at)'
            ' VALUES(?,?,?,?)',
            (key,encoded,json.dumps(out,ensure_ascii=False),now))
        db.commit()
        return out
    except Exception:
        db.rollback()
        raise

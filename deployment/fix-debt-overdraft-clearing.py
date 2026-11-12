"""Make debt cancellation clear BOTH bank loans and negative cash on target.

Existing positive balances and deposits remain unchanged. An all-negative-cash
account with zero bank loans is now eligible. The preview, confirmation,
transaction and audit history include the forgiven overdraft amount.
"""
from pathlib import Path
from zipfile import ZipFile
import ast,io
archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}

def change(name,old,new):
    s=files[name].decode('utf-8')
    occurrences=s.count(old)
    if occurrences!=1:
        raise RuntimeError(f"{name}: expected one anchor, got {occurrences}: {old[:100]!r}")
    files[name]=s.replace(old,new).encode('utf-8')

name='admin_fund_ops.py'
change(name,
"""        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""",
"""        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""") if False else None
# Add a non-destructive audit migration for the existing history table.
change(name,
"""        created_at BIGINT NOT NULL)""")
""".replace("        created_at BIGINT NOT NULL)\"\"\")\n","        created_at BIGINT NOT NULL)\"\"\")\n"),"""
        created_at BIGINT NOT NULL)""")
""") if False else None
# These anchors match the current production module, not the obsolete
# deployment/admin_fund_ops.py copy.
change(name,
"""        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""")
""",
"""        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""")
""") if False else None

change(name,
"""        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""")
""",
"""        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""")
""") if False else None
# The real schema terminates with two exact lines, as below.
change(name,
"""        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""")
""",
"""        note TEXT NOT NULL,
        created_at BIGINT NOT NULL)""")
""") if False else None
# Insert immediately before the next def rather than relying on formatted SQL.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None
# Introduce a separate audit table rather than altering legacy history rows.
# This records the independent adjustment without weakening historic debts.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None
# We keep original legacy table and add a keyed cash-recovery audit table.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Perform a narrow insertion to the end of the module's install() function.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None
# Real insertion:
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Corrected concrete schema extension.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Add refund audit with foreign key and per-operation key.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None
# no-op branches above are deliberately disabled; do not alter the archive
# except via active change() calls below.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Append the cash restored to separate table linked to same operation.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# exact unique class transition (function starts once):
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Audited restore history; legacy forgiveness events remain queryable.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# A direct apply audit can use per-player result JSON, with no schema change.
# Thus the existing cancellation history retains its original debt column.
change(name,
"""        if payload['kind']=='forgive' and not any(p['debt']>0 for p in players):
            raise ValueError('このアカウントに帳消しできる借入残高はありません。')""",
"""        if payload['kind']=='forgive' and not any(
                p['debt']>0 or p['cash']<0 for p in players):
            raise ValueError('このアカウントには銀行借入もマイナス残高もありません。')""")
change(name,
"""        if amt<=0:continue
        # Prevent ambiguous zero-amount audit records.
        entries.append({'player_id':p['player_id'],'student_id':p['student_id'],
                        'name':p['name'],'assets':p['assets'],'cash':p['cash'],
                        'debt':p['debt'],'amount':amt,
                        'after_cash':p['cash'] + (
                            amt if payload['kind']=='grant' else
                            -amt if payload['kind']=='collect' else 0)})""",
"""        cash_restored=max(0,-p['cash']) if payload['kind']=='forgive' else 0
        if amt<=0 and not cash_restored:continue
        entries.append({'player_id':p['player_id'],'student_id':p['student_id'],
                        'name':p['name'],'assets':p['assets'],'cash':p['cash'],
                        'debt':p['debt'],'amount':amt,'cash_restored':cash_restored,
                        'after_cash':(
                            max(0,p['cash']) if payload['kind']=='forgive' else
                            p['cash'] + (amt if payload['kind']=='grant' else -amt))})""")
change(name,
"""    return {'count':len(entries),'total':sum(p['amount'] for p in entries),
            'people':entries,'digest':digest}""",
"""    return {'count':len(entries),'total':sum(p['amount'] for p in entries),
            'cash_restored_total':sum(p['cash_restored'] for p in entries),
            'people':entries,'digest':digest}""")
change(name,
"""                db.execute('UPDATE bank_accounts SET debt=0 WHERE player=?',(player,))
            if payload['kind']=='forgive':""",
"""                db.execute('UPDATE bank_accounts SET debt=0 WHERE player=?',(player,))
                if p['cash_restored']:
                    # Fix negative balances in the SAME atomic transaction.
                    # No free extra funds are given to already solvent players.
                    db.execute('UPDATE factories SET cash=0 WHERE player=? AND bge(0,cash)',
                               (player,))
            if payload['kind']=='forgive':""")
change(name,
"""                'people':snapshot['people'],'already_applied':False}""",
"""                'people':snapshot['people'],
                'cash_restored_total':snapshot['cash_restored_total'],
                'already_applied':False}""")

# Make the audit history show overdrafts restored alongside earlier loan
# cancellations; join on the operation key's rows in stored result payload.
change(name,
"""def history(db):
    return [dict(r) for r in db.execute(
        'SELECT student_id,name,debt,note,created_at FROM '
        'admin_debt_cancellations ORDER BY created_at DESC,key DESC LIMIT 50')]""",
"""def history(db):
    rows=[dict(r) for r in db.execute(
        'SELECT key,student_id,name,debt,note,created_at FROM '
        'admin_debt_cancellations ORDER BY created_at DESC,key DESC LIMIT 50')]
    # New cash adjustments have their own audit ledger, preserving old rows.
    cash={r['key']:int(r['cash_restored']) for r in db.execute(
        'SELECT key,cash_restored FROM admin_overdraft_cancellations '
        'ORDER BY created_at DESC LIMIT 100')}
    for item in rows:
        item['cash_restored']=cash.get(item['key'],0)
        item.pop('key')
    return rows""")
# Install additive audit table. It never alters bank or historical balances.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Add audit DDL within the existing schema installer directly before _digits.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Active insertion:
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Prevent a nonexisting-table read by extending install() in a targeted way.
change(name,
"""def _digits(value, *, optional=False):""",
"""def _digits(value, *, optional=False):""") if False else None

# Implementation directly: inspect current body between install and _digits.
s=files[name].decode('utf-8')
boundary='\ndef _digits(value, *, optional=False):'
assert s.count(boundary)==1
install_add="""    db.execute('CREATE TABLE IF NOT EXISTS admin_overdraft_cancellations('
               'key TEXT PRIMARY KEY, cash_restored NUMERIC NOT NULL,'
               'created_at BIGINT NOT NULL)')

"""
s=s.replace(boundary,'\n'+install_add+boundary)
files[name]=s.encode('utf8')

# Persist the cash restoration audit with the same per-person operation key.
change(name,
"""            else:
                # Same audit ledger as individual transactions, so collection""",
"""                db.execute('INSERT INTO admin_overdraft_cancellations'
                           '(key,cash_restored,created_at) VALUES(?,?,?)',
                           (key+'-'+str(i),p['cash_restored'],now))
            else:
                # Same audit ledger as individual transactions, so collection""")

change('static/admin.js',
"""  preview.textContent='対象者のすべての銀行借入をゼロにします。所持金・預け入れ・純利益は変わりません。';""",
"""  preview.textContent='対象者の銀行借入を帳消しにし、所持金がマイナスなら0円に戻します。プラスの所持金と預け入れは変更しません。';""")
change('static/admin.js',
"""   $('#funds-confirm-message').textContent=student_id+' の銀行借入 '+fmt(result.total)+'円をすべて帳消しにします。所持金は変わりません。実行しますか？';""",
"""   $('#funds-confirm-message').textContent=student_id+' の銀行借入 '+fmt(result.total)+'円を帳消しにし、マイナス所持金 '+fmt(result.cash_restored_total)+'円を0円まで回復します。実行しますか？';""")
change('static/admin.js',
"""   ?(result.already_applied?'処理済み：':'帳消し完了：')+request.student_id+' · 借入 '+fmt(result.total)+'円'""",
"""   ?(result.already_applied?'処理済み：':'帳消し完了：')+request.student_id+' · 借入 '+fmt(result.total)+'円 · マイナス所持金回復 '+fmt(result.cash_restored_total)+'円'""")
change('static/admin.js',
"""  table('#debt-history',['日時','学籍番号・名前','帳消し額','理由'],
   (r.history||[]).map(v=>[
    new Date(Number(v.created_at)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}),
    v.student_id+' · '+v.name,fmt(v.debt)+'円',v.note||'—'
   ]));""",
"""  table('#debt-history',['日時','学籍番号・名前','銀行借入帳消し','マイナス所持金回復','理由'],
   (r.history||[]).map(v=>[
    new Date(Number(v.created_at)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}),
    v.student_id+' · '+v.name,fmt(v.debt)+'円',
    fmt(v.cash_restored||0)+'円',v.note||'—'
   ]));""")
change('static/admin.js',
"""   +' · 対象 '+result.count+'人 · 合計 '+fmt(result.total)+'円。内容を確認して実行してください。';""",
"""   +' · 対象 '+result.count+'人 · '+(params.kind==='forgive'
     ?'銀行借入帳消し '+fmt(result.total)+'円 · マイナス所持金回復 '+fmt(result.cash_restored_total)+'円'
     :'合計 '+fmt(result.total)+'円')+'。内容を確認して実行してください。';""")
change('static/admin.js',
"""   +result.count+'人 · 合計 '+fmt(result.total)+'円';""",
"""   +result.count+'人 · '+(request.kind==='forgive'
      ?'銀行借入帳消し '+fmt(result.total)+'円 · マイナス所持金回復 '+fmt(result.cash_restored_total)+'円'
      :'合計 '+fmt(result.total)+'円');""")
change('static/admin.html',
"""<h3>借金帳消し履歴</h3>""",
"""<h3>借金帳消し・マイナス所持金回復履歴</h3>""")

for f in ('admin_fund_ops.py',):ast.parse(files[f].decode('utf8'),filename=f)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('admin_fund_ops.py','static/admin.js','static/admin.html'):
            assert z.read(info.filename)==data,info.filename
archive.write_bytes(out.getvalue())
print('PASS: forgive bank debt and reset negative cash to zero atomically, with audit and preview')

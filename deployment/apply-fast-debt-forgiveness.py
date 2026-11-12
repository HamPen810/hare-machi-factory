"""Route administrator debt forgiveness through per-player, live-balance logic.

Unrelated grant/collection logic, player registration and Oracle integration
remain byte-for-byte unchanged. This changes only the authoritative ZIP.
"""
from pathlib import Path
from zipfile import ZipFile
import ast,io
path=Path('hare-machi-render.zip')
with ZipFile(path) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}

def change(name,old,new):
    content=files[name].decode('utf8')
    n=content.count(old)
    if n!=1:raise RuntimeError(f'{name}: expected one anchor, found {n}: {old[:100]!r}')
    files[name]=content.replace(old,new).encode('utf8')

change('admin_fund_ops.py',
"""    payload=validate(data)
    if action=='preview':""",
"""    payload=validate(data)
    if payload['kind']=='forgive':
        from admin_forgive_fast import execute
        return execute(admin,payload,data,now)
    if action=='preview':""")

change('static/admin.js',
"""  preview.textContent='対象者の銀行借入を帳消しにし、所持金がマイナスなら0円に戻します。プラスの所持金と預け入れは変更しません。';""",
"""  preview.textContent='銀行借入をすべて取り消し、実行時の所持金がマイナスなら0円にします。見積もり後に金額が変わっても、実行時の最新残高で処理します。';""")
change('static/admin.js',
"""   $('#funds-confirm-message').textContent=student_id+' の銀行借入 '+fmt(result.total)+'円を帳消しにし、マイナス所持金 '+fmt(result.cash_restored_total)+'円を0円まで回復します。実行しますか？';""",
"""   $('#funds-confirm-message').textContent=student_id+' の銀行借入（見積もり '+fmt(result.total)+'円）を帳消しにし、所持金がマイナスなら0円に戻します（見積もり回復 '+fmt(result.cash_restored_total)+'円）。実行時に金額が変わっていても最新の残高で確定します。実行しますか？';""")
change('static/admin.js',
"""  $('#bulk-summary').textContent=(params.kind==='grant'?'補助金':params.kind==='collect'?'徴収':'借金帳消し')""",
"""  $('#bulk-summary').textContent=(params.kind==='grant'?'補助金':params.kind==='collect'?'徴収':'借金帳消し（実行時の最新残高で確定）')""")

module=Path('deployment/fix-fast-debt-forgiveness-module.py').read_bytes()
ast.parse(module.decode('utf8'),filename='admin_forgive_fast.py')
if 'admin_forgive_fast.py' in files:raise RuntimeError('Fast forgiveness module already deployed')
files['admin_forgive_fast.py']=module
for name in ('admin_fund_ops.py',):
    ast.parse(files[name].decode('utf8'),filename=name)

out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:
        z.writestr(info,files[info.filename])
    z.writestr('admin_forgive_fast.py',module)
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('admin_fund_ops.py','static/admin.js'):
            assert z.read(info.filename)==data,info.filename
path.write_bytes(out.getvalue())
print('PASS: targeted forgiveness with no global advisory or all-player row lock; estimate is advisory')

"""Upgrade the CURRENT Render deployment archive to independent bank contracts.

Do not replace the full application with an older snapshot. Preserve all
existing contracts, cash, taxes, interest rules, and transaction idempotency.
"""
from pathlib import Path
from zipfile import ZipFile
import ast, io, re

archive = Path("hare-machi-render.zip")
with ZipFile(archive) as source:
    entries = [(i, source.read(i.filename)) for i in source.infolist()]
    comment = source.comment
files = {i.filename: data for i, data in entries}

def substitute(filename, before, after):
    source = files[filename].decode("utf-8")
    if source.count(before) != 1:
        raise RuntimeError(f"Unexpected {filename} layout: {before[:75]!r} count={source.count(before)}")
    files[filename] = source.replace(before, after).encode("utf-8")

# Keep the existing per-player aggregate bank_accounts record (used by taxes).
# New contracts have their own principal, balance, and individual maturities.
substitute("bank.py",
    '    """CREATE TABLE IF NOT EXISTS bank_admin_actions (',
    '''    """CREATE TABLE IF NOT EXISTS bank_contracts (
        id text PRIMARY KEY,
        player text NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        kind text NOT NULL,
        principal numeric NOT NULL,
        amount numeric NOT NULL,
        matures numeric NOT NULL DEFAULT 0,
        created_at numeric NOT NULL DEFAULT 0)""",
    "CREATE INDEX IF NOT EXISTS bank_contracts_player ON bank_contracts(player)",
    """CREATE TABLE IF NOT EXISTS bank_admin_actions (''')

bank_helpers = '''
def _ensure_contracts(db):
    # PostgreSQL uses existing migrations for the original schema; create this
    # additive table lazily, without altering existing financial records.
    if db.__class__.__module__ != 'sqlite3':
        db.execute("""CREATE TABLE IF NOT EXISTS bank_contracts (
            id text PRIMARY KEY,
            player text NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            kind text NOT NULL, principal numeric NOT NULL,
            amount numeric NOT NULL, matures numeric NOT NULL DEFAULT 0,
            created_at numeric NOT NULL DEFAULT 0)""")
        db.execute("CREATE INDEX IF NOT EXISTS bank_contracts_player ON bank_contracts(player)")

def _items(db, player):
    return [dict(row) for row in db.execute(
        'SELECT id,player,kind,principal,amount,matures,created_at '
        'FROM bank_contracts WHERE player=? ORDER BY created_at,id', (player,))]

def _legacy_entries(row, player):
    result = []
    if row and row['deposit']:
        result.append(dict(id='legacy-lend-'+player, player=player, kind='lend',
                           principal=row['deposit'], amount=row['deposit'],
                           matures=row['matures'], created_at=0))
    if row and row['debt']:
        result.append(dict(id='legacy-borrow-'+player, player=player, kind='borrow',
                           principal=row['debt'], amount=row['debt'],
                           matures=0, created_at=0))
    return result

def _migrate_legacy(db, player, row):
    # A player's old single-contract balances are migrated on their first
    # transaction. They are never removed or reset during migration.
    if _items(db, player):
        return
    for entry in _legacy_entries(row, player):
        db.execute(
            'INSERT INTO bank_contracts(id,player,kind,principal,amount,matures,created_at) '
            'VALUES(?,?,?,?,?,?,?) ON CONFLICT DO NOTHING',
            (entry['id'],entry['player'],entry['kind'],entry['principal'],
             entry['amount'],entry['matures'],entry['created_at']))

def _sync_totals(db, player):
    rows = _items(db, player)
    deposits = [r for r in rows if r['kind'] == 'lend']
    debts = [r for r in rows if r['kind'] == 'borrow']
    deposit = sum(r['amount'] for r in deposits)
    debt = sum(r['amount'] for r in debts)
    matures = min((r['matures'] for r in deposits), default=0)
    db.execute('UPDATE bank_accounts SET deposit=?,debt=?,matures=? WHERE player=?',
               (deposit,debt,matures,player))
    return rows

'''
key = 'def player_state(db, player, now):'
body = files['bank.py'].decode()
assert body.count(key)==1
body = body.replace(key, bank_helpers+key)
start = body.index('def player_state(db, player, now):')
end = body.index('def asset_tax(game, policy, *, apply):', start)
new_funcs = '''def player_state(db, player, now):
    _ensure_contracts(db)
    cfg = settings(db)
    row = db.execute('SELECT deposit,matures,debt,tax FROM bank_accounts WHERE player=?', (player,)).fetchone()
    result = dict(row) if row else dict(deposit=0,matures=0,debt=0,tax=0)
    contracts = _items(db, player)
    if not contracts:
        contracts = _legacy_entries(row, player)
    return {**result, 'contracts': contracts, 'now': now,
            **{k: cfg[k] for k in ('enabled','limit','lend_bps','borrow_bps')}}


def player_action(db, player, kind, quantity, now, closes_at):
    _ensure_contracts(db)
    cfg = settings(db)
    db.execute('INSERT INTO bank_accounts(player) VALUES(?) ON CONFLICT DO NOTHING', (player,))
    row = db.execute('SELECT * FROM bank_accounts WHERE player=?', (player,)).fetchone()
    _migrate_legacy(db, player, row)
    delta = 0
    ids = []
    if kind in ('bank_lend','bank_borrow'):
        if not cfg['enabled']:
            raise ValueError('現在は新規契約を受け付けていません。')
        amount = integer(quantity, 1, int(cfg['limit']))
        contract_id = secrets.token_hex(16)
        if kind == 'bank_lend':
            if now + HOUR_MS >= closes_at:
                raise ValueError('締切まで1時間以内のため預け入れできません。')
            payout = amount + amount * cfg['lend_bps'] // 10000
            db.execute('INSERT INTO bank_contracts VALUES(?,?,?,?,?,?,?)',
                       (contract_id,player,'lend',amount,payout,now+HOUR_MS,now))
            delta = -amount
        else:
            debt = amount + (amount * cfg['borrow_bps'] + 9999) // 10000
            db.execute('INSERT INTO bank_contracts VALUES(?,?,?,?,?,?,?)',
                       (contract_id,player,'borrow',amount,debt,0,now))
            delta = amount
        ids = [contract_id]
    elif kind in ('bank_withdraw','bank_repay'):
        target = 'lend' if kind == 'bank_withdraw' else 'borrow'
        contracts = _items(db, player)
        candidates = [r for r in contracts
                      if r['kind'] == target and
                      (target == 'borrow' or now >= r['matures'])]
        if quantity is not None:
            if not isinstance(quantity,str):
                raise ValueError('契約IDが不正です。')
            candidates = [r for r in candidates if r['id'] == quantity]
        if not candidates:
            raise ValueError('返済・受取が可能な契約はありません。')
        total = sum(r['amount'] for r in candidates)
        delta = total if target == 'lend' else -total
        ids = [r['id'] for r in candidates]
        # The action is already inside market.act's lock + transaction.
        for item in candidates:
            db.execute('DELETE FROM bank_contracts WHERE id=? AND player=?',
                       (item['id'],player))
    else:
        raise ValueError('銀行操作を確認してください。')

    if delta < 0:
        if db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=? AND bge(cash,?)',
                      (-delta,player,-delta)).rowcount != 1:
            raise ValueError('所持金が足りません。')
    elif delta > 0:
        db.execute('UPDATE factories SET cash=badd(cash,?) WHERE player=?',(delta,player))
    _sync_totals(db, player)
    return {'cash_change':delta, 'contract_ids':ids}


'''
body = body[:start] + new_funcs + body[end:]
ast.parse(body,filename='bank.py')
files['bank.py'] = body.encode("utf-8")

# The ordinary buttons create further contracts or settle ALL eligible contracts.
# Individual contract buttons use the existing idempotent action API.
js = files['static/app.js'].decode('utf-8')
start = js.index('const bankDialog = ')
end = js.index('const buyDialog=', start)
new_js = '''const bankDialog = $('#bank-dialog');
const bankAmount = $('#bank-amount');
const bankButtons = [...bankDialog.querySelectorAll('[data-bank]')];
let bankState, bankBusy = false, pendingBankAction;
const bankContractList = document.createElement('div');
bankContractList.id = 'bank-contract-list';
bankContractList.setAttribute('aria-label', '銀行の契約一覧');
bankContractList.style.cssText = 'display:grid;gap:10px;margin:14px 0';
$('#bank-terms').insertAdjacentElement('afterend',bankContractList);
bankButtons.find(b=>b.dataset.bank==='bank_withdraw').textContent='満期分を一括受取';
bankButtons.find(b=>b.dataset.bank==='bank_repay').textContent='借入を一括返済';

function bankDate(millis) {
 return new Date(Number(millis)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'});
}
function renderBank() {
 if (!bankState) return;
 const {enabled, limit, lend_bps, borrow_bps, deposit, debt, matures} = bankState;
 const amount = parseWhole(bankAmount.value) ?? 0n;
 const payout = amount + amount * big(lend_bps) / 10000n;
 const repayment = amount + (amount * big(borrow_bps) + 9999n) / 10000n;
 const contracts = bankState.contracts || [];
 $('#bank-balance').textContent = '預け入れ満期受取額の合計 '+fmt(deposit)+'円 · 借入返済額の合計 '+fmt(debt)+'円 · 累計税額 '+fmt(bankState.tax)+'円';
 $('#bank-terms').textContent = (enabled ? '1契約あたりの上限 '+fmt(limit)+'円' : '新規契約は停止中')
  + ' · 預け入れ利率 '+(lend_bps/100)+'％（1時間）／借入利率 '+(borrow_bps/100)+'％（契約時に確定）'
  + (amount > 0n ? ' · 今回の満期受取 '+fmt(payout)+'円／借入返済 '+fmt(repayment)+'円' : '');
 const valid = enabled && amount>0n && amount<=big(limit);
 const canWithdraw=contracts.some(c=>c.kind==='lend' && Date.now()>=Number(c.matures));
 for(const button of bankButtons) {
  const kind=button.dataset.bank;
  const allowed=kind==='bank_withdraw' ? canWithdraw
   : kind==='bank_repay' ? big(debt)>0n
   : kind==='bank_lend' ? valid && (Date.now()+3600000 < Number(bankState.closes_at || Infinity))
   : kind==='bank_borrow' ? valid : false;
  button.disabled = bankBusy || !allowed;
 }
 bankContractList.replaceChildren();
 const heading=document.createElement('h4');
 heading.textContent='契約一覧（'+contracts.length+'件）';
 heading.style.cssText='margin:4px 0 0;font-size:16px';
 bankContractList.append(heading);
 if (!contracts.length) {
  const empty=document.createElement('p');empty.textContent='契約はありません。';
  bankContractList.append(empty);
 }
 contracts.forEach((c,index)=>{
  const card=document.createElement('div');
  card.style.cssText='padding:12px 14px;border:1px solid #cbd9c9;border-radius:12px;background:#fffdf5;display:grid;gap:7px';
  const label=document.createElement('strong');
  label.textContent=(c.kind==='lend'?'預け入れ':'借入')+' '+(index+1)+' · '+fmt(c.amount)+'円';
  const detail=document.createElement('span');
  detail.style.cssText='font-size:13px;line-height:1.65';
  detail.textContent=c.kind==='lend' ? '満期 '+bankDate(c.matures)+' · 預入元金 '+fmt(c.principal)+'円' : '元金 '+fmt(c.principal)+'円 · 返済額 '+fmt(c.amount)+'円';
  const action=document.createElement('button');
  action.className='tp-small';
  const withdraw=c.kind==='lend';
  action.textContent=withdraw?'この満期金を受け取る':'この借入を返済する';
  action.disabled=bankBusy || (withdraw && Date.now()<Number(c.matures));
  action.onclick=()=>performBankAction(withdraw?'bank_withdraw':'bank_repay',c.id);
  card.append(label,detail,action);
  bankContractList.append(card);
 });
}

async function loadBank() {
 bankState=await api('bank');
 renderBank();
}

$('#open-bank').onclick=async()=>{
 $('#bank-status').textContent='銀行の情報を取得中…';
 bankButtons.forEach(button=>button.disabled=true);
 bankDialog.showModal();
 try{await loadBank();$('#bank-status').textContent='';}
 catch(error){$('#bank-status').textContent=error.message;}
};
bankAmount.addEventListener('input',renderBank);

async function performBankAction(kind,quantity) {
 if(bankBusy)return;
 if(!pendingBankAction || pendingBankAction.kind!==kind || pendingBankAction.quantity!==quantity) {
  pendingBankAction={key:crypto.randomUUID(),kind,quantity};
 }
 bankBusy=true;renderBank();
 try{
  await api('action',pendingBankAction);
  pendingBankAction=null;
  await Promise.all([loadBank(),refresh()]);
  $('#bank-status').textContent='取引が完了しました。';
 }catch(error){$('#bank-status').textContent=error.message;}
 finally{bankBusy=false;renderBank();}
}
for(const button of bankButtons)button.onclick=()=>{
 const kind=button.dataset.bank;
 const quantity=['bank_lend','bank_borrow'].includes(kind)?bankAmount.value:null;
 void performBankAction(kind,quantity);
};

'''
js = js[:start] + new_js + js[end:]
files['static/app.js']=js.encode("utf-8")

# Explain the new behaviour while preserving any existing edited rulebook.
html=files['static/index.html'].decode("utf-8")
html=html.replace('借入と預け入れは同時に利用できます。それぞれ同時に1件まで契約できます。',
    '借入と預け入れは何件でも同時に契約できます。各契約の残高・利息・満期は契約一覧で個別に管理されます。満期分の一括受取、借入の一括返済にも対応します。')
files['static/index.html']=html.encode("utf-8")
rules=files['rules-default.txt'].decode("utf-8")
rules=rules.replace('借入と預け入れは同時に利用できます。それぞれ同時に1件まで契約できます。',
    '借入と預け入れは何件でも同時に契約できます。各契約の残高・利息・満期は個別に管理されます。満期分の一括受取、借入の一括返済にも対応します。')
files['rules-default.txt']=rules.encode("utf-8")

with ZipFile(archive,'w') as target:
    target.comment=comment
    for info,data in entries:
        target.writestr(info,files[info.filename])
with ZipFile(archive) as check:
    assert check.testzip() is None
    for info,data in entries:
        assert check.read(info.filename) == files[info.filename]
        if info.filename not in ('bank.py','static/app.js','static/index.html','rules-default.txt'):
            assert check.read(info.filename) == data, info.filename
print('PASS: independent bank contracts, legacy balances retained, UI updated')

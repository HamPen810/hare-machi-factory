"""Game-currency banking. Market and player changes use existing transaction locks."""
import json
import re
import secrets

BANK = '@bank'
HOUR_MS = 3600000
DEFAULT = {'enabled': False, 'demand_bps': 2500, 'lend_bps': 100, 'borrow_bps': 300,
           'limit': '10000', 'brackets': [], 'exponential': None}

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS bank_settings (id integer PRIMARY KEY, config text NOT NULL)",
    """CREATE TABLE IF NOT EXISTS bank_accounts (
        player text PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
        deposit numeric NOT NULL DEFAULT 0, matures numeric NOT NULL DEFAULT 0,
        debt numeric NOT NULL DEFAULT 0, tax numeric NOT NULL DEFAULT 0,
        taxable_sales numeric NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS bank_admin_actions (
        key text PRIMARY KEY, payload text NOT NULL, result text NOT NULL)""",
)

def initialize(db):
    for statement in SCHEMA:
        db.execute(statement)

def integer(value, low=0, high=None):
    if isinstance(value, str) and len(value) <= 10010:
        match = re.fullmatch(r'([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]{1,4}))?', value.strip())
        if match:
            whole, fraction, exponent = match.groups()
            fraction = fraction or ''
            digits = (whole + fraction).lstrip('0') or '0'
            shift = int(exponent or 0) - len(fraction)
            if digits == '0':
                value = 0
            elif shift >= 0 and len(digits) + shift <= 10000:
                value = int(digits + '0' * shift)
            elif shift < 0 and -shift < len(digits) and not digits[shift:].strip('0'):
                value = int(digits[:shift])
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError('指定した数値が範囲外です。')
    return value

def settings(db):
    row = db.execute('SELECT config FROM bank_settings WHERE id=1').fetchone()
    return json.loads(row[0]) if row else dict(DEFAULT)

def configure(data):
    if type(data.get('enabled')) is not bool:
        raise ValueError('銀行の有効・無効を指定してください。')
    result = {'enabled': data['enabled'], 'limit': str(integer(data.get('limit'), 1))}
    for name in ('demand_bps', 'lend_bps', 'borrow_bps'):
        result[name] = integer(data.get(name), 0, 10000)
    brackets = data.get('brackets')
    if not isinstance(brackets, list) or len(brackets) > 10:
        raise ValueError('税率の区分は10段階までです。')
    result['brackets'] = []
    prior_threshold, prior_rate = -1, 0
    for row in brackets:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError('各税率は売上の下限と税率を指定してください。')
        threshold, rate = integer(row[0]), integer(row[1], prior_rate, 10000)
        if threshold <= prior_threshold:
            raise ValueError('売上下限を小さい順に入力してください。')
        result['brackets'].append([str(threshold), rate])
        prior_threshold, prior_rate = threshold, rate
    exponential = data.get('exponential')
    result['exponential'] = None
    if exponential is not None:
        if not isinstance(exponential, dict):
            raise ValueError('指数課税の設定を確認してください。')
        base = integer(exponential.get('base_bps'), 1, 9999)
        result['exponential'] = {
            'threshold': str(integer(exponential.get('threshold'))),
            'step': str(integer(exponential.get('step'), 1)),
            'base_bps': base,
        }
    if result['lend_bps'] > result['borrow_bps']:
        raise ValueError('預け入れ利率は借入利率以下にしてください。')
    return result

def tax_due(revenue, brackets):
    total = 0
    for i, (threshold, rate) in enumerate(brackets):
        end = min(revenue, int(brackets[i+1][0])) if i+1 < len(brackets) else revenue
        total += max(0, end - int(threshold)) * rate
    return total // 10000

def exponential_tax_due(revenue, policy):
    """Double both band width and marginal rate, with no rate cap."""
    taxable = max(0, revenue - int(policy['threshold']))
    step = int(policy['step'])
    completed = (taxable // step + 1).bit_length() - 1
    multiplier = 1 << completed
    used = step * (multiplier - 1)
    # The fully taxed bands contribute a geometric series with ratio 4.
    weighted = step * (multiplier * multiplier - 1) // 3
    weighted += (taxable - used) * multiplier
    return weighted * policy['base_bps'] // 10000


def record_tax(db, player, revenue, config):
    exponential = config.get('exponential')
    if not config['enabled'] or not (config['brackets'] or exponential):
        return 0
    db.execute('INSERT INTO bank_accounts(player) VALUES(?) ON CONFLICT DO NOTHING', (player,))
    if exponential:
        if db.__class__.__module__ == 'sqlite3':
            before = sum(row[0] * row[1] for row in db.execute(
                'SELECT sold_quantity,unit_price FROM sales WHERE player_id=?', (player,)))
        else:
            before = db.execute(
                'SELECT COALESCE(SUM(sold_quantity*unit_price),0) FROM sales WHERE player_id=?',
                (player,)).fetchone()[0]
        tax = exponential_tax_due(before + revenue, exponential) - exponential_tax_due(before, exponential)
    else:
        before = db.execute('SELECT taxable_sales FROM bank_accounts WHERE player=?', (player,)).fetchone()[0]
        tax = tax_due(before + revenue, config['brackets']) - tax_due(before, config['brackets'])
    db.execute('UPDATE bank_accounts SET taxable_sales=badd(taxable_sales,?),tax=badd(tax,?) WHERE player=?',
               (revenue,tax,player))
    return tax

def player_state(db, player, now):
    cfg = settings(db)
    row = db.execute('SELECT deposit,matures,debt,tax FROM bank_accounts WHERE player=?', (player,)).fetchone()
    result = dict(row) if row else dict(deposit=0,matures=0,debt=0,tax=0)
    return {**result, 'now': now, **{k: cfg[k] for k in ('enabled','limit','lend_bps','borrow_bps')}}

def player_action(db, player, kind, quantity, now, closes_at):
    cfg = settings(db)
    db.execute('INSERT INTO bank_accounts(player) VALUES(?) ON CONFLICT DO NOTHING', (player,))
    row = db.execute('SELECT * FROM bank_accounts WHERE player=?', (player,)).fetchone()
    delta = 0
    if kind in ('bank_lend','bank_borrow'):
        if not cfg['enabled']:
            raise ValueError('現在は新規契約を受け付けていません。')
        amount = integer(quantity, 1, int(cfg['limit']))
        if kind == 'bank_lend':
            if row['deposit'] or now + HOUR_MS >= closes_at:
                raise ValueError('預け入れ中、または締切まで1時間以内です。')
            payout = amount + amount * cfg['lend_bps'] // 10000
            db.execute('UPDATE bank_accounts SET deposit=?,matures=? WHERE player=?',
                       (payout,now+HOUR_MS,player))
            delta = -amount
        else:
            if row['debt']:
                raise ValueError('借入残高がある間は新たに借りられません。')
            debt = amount + (amount * cfg['borrow_bps'] + 9999) // 10000
            db.execute('UPDATE bank_accounts SET debt=? WHERE player=?',(debt,player))
            delta = amount
    elif kind == 'bank_withdraw':
        if not row['deposit'] or now < row['matures']:
            raise ValueError('引き出せる預け入れはありません。')
        delta = row['deposit']
        db.execute('UPDATE bank_accounts SET deposit=0,matures=0 WHERE player=?',(player,))
    elif kind == 'bank_repay':
        if not row['debt']:
            raise ValueError('返済する借り入れはありません。')
        delta = -row['debt']
        db.execute('UPDATE bank_accounts SET debt=0 WHERE player=?',(player,))
    if delta < 0:
        if db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=? AND bge(cash,?)',
                      (-delta,player,-delta)).rowcount != 1:
            raise ValueError('所持金が足りません。')
    else:
        db.execute('UPDATE factories SET cash=badd(cash,?) WHERE player=?',(delta,player))
    return {'cash_change':delta}

def asset_tax(game, policy, *, apply):
    from market import PRODUCTS
    db = game.db
    if apply and game.accounts.postgres:
        db.execute('SELECT id FROM players ORDER BY id FOR NO KEY UPDATE').fetchall()
    assets = {row['player']: row['cash'] + row['deposit'] for row in db.execute(
        """SELECT f.player,f.cash,COALESCE(b.deposit,0) AS deposit
           FROM factories f LEFT JOIN bank_accounts b ON b.player=f.player""")}
    for row in db.execute("""SELECT player,product,quantity FROM stock
                             UNION ALL SELECT player,product,quantity FROM listings WHERE player<>?""",(BANK,)):
        if row['player'] in assets:
            assets[row['player']] += row['quantity'] * PRODUCTS[row['product']][1]
    taxes = [(player,exponential_tax_due(max(0,value),policy)) for player,value in assets.items()]
    taxes = [(player,tax) for player,tax in taxes if tax]
    if apply:
        for player, tax in taxes:
            db.execute("""INSERT INTO bank_accounts(player,tax) VALUES(?,?)
                ON CONFLICT(player) DO UPDATE SET tax=badd(bank_accounts.tax,excluded.tax)""",(player,tax))
            db.execute('UPDATE factories SET cash=bsub(cash,?) WHERE player=?',(tax,player))
    return {'asset_tax':sum(tax for _,tax in taxes), 'players':len(taxes), 'applied':apply}

def admin_action(game, data):
    db = game.db
    key = data.get('key')
    if not isinstance(key,str) or not 1 <= len(key) <= 80:
        raise ValueError('操作IDが必要です。')
    payload = json.dumps(data,sort_keys=True)
    db.execute('BEGIN IMMEDIATE')
    try:
        if game.accounts.postgres:
            db.execute('SELECT pg_advisory_xact_lock(CAST(? AS bigint))',(1042119,))
        existing = db.execute('SELECT payload,result FROM bank_admin_actions WHERE key=?',(key,)).fetchone()
        if existing:
            if existing[0] != payload:
                raise ValueError('操作IDが重複しています。')
            db.rollback()
            return json.loads(existing[1])
        kind = data.get('kind')
        if kind == 'configure':
            cfg = configure(data)
            db.execute('INSERT INTO bank_settings VALUES(1,?) ON CONFLICT(id) DO UPDATE SET config=excluded.config',
                       (json.dumps(cfg),))
            result = cfg
        elif kind in ('asset_tax_preview','asset_tax_apply'):
            policy = settings(db).get('exponential')
            if not policy:
                raise ValueError('先に銀行設定で指数課税の条件を保存してください。')
            result = asset_tax(game, policy, apply=kind=='asset_tax_apply')
        else:
            from market import PRODUCTS
            product = data.get('product')
            if product not in PRODUCTS:
                raise ValueError('商品を選んでください。')
            if game.event()['phase'] != 'open':
                raise ValueError('買い取り・出品は開催中のみ実行できます。')
            now = game.clock()
            amount = integer(data.get('quantity'),0 if kind == 'offer' else 1)
            if kind == 'offer':
                price = integer(data.get('price'),1,99999)
                db.execute('DELETE FROM listings WHERE player=? AND product=?',(BANK,product))
                if amount:
                    db.execute('INSERT INTO listings VALUES(?,?,?,?,?,?,?)',
                               (secrets.token_hex(16),BANK,product,amount,price,now,now//60000))
                result = {'quantity':amount}
            elif kind == 'buyout':
                rows = db.execute('SELECT * FROM listings WHERE product=? AND player<>? ORDER BY price,accepted,id',
                                  (product,BANK)).fetchall()
                if sum(r['quantity'] for r in rows) < amount:
                    raise ValueError('買い取れる出品数が不足しています。')
                remaining, spent = amount, 0
                cfg = settings(db)
                for row in rows:
                    count = min(remaining,row['quantity'])
                    game._credit_sale(row, count, PRODUCTS[product][2], now, secrets.token_hex(16), cfg)
                    if count == row['quantity']:
                        db.execute('DELETE FROM listings WHERE id=?',(row['id'],))
                    else:
                        db.execute('UPDATE listings SET quantity=bsub(quantity,?) WHERE id=?',(count,row['id']))
                    remaining -= count
                    spent += count * row['price']
                    if not remaining:
                        break
                result = {'quantity':amount,'spent':spent}
            else:
                raise ValueError('銀行操作を確認してください。')
        db.execute('INSERT INTO bank_admin_actions VALUES(?,?,?)',(key,payload,json.dumps(result)))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise

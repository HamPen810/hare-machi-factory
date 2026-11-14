"""Install stage-1/2 tap monitoring into existing production ZIP.
No game economics, balances, purchases, or tap limits are changed.
Requires hare_factory.tap_monitor_state from pre-deploy migration.
"""
from pathlib import Path
from zipfile import ZipFile
import io, ast, json

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    members=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:d for i,d in members}
monitor=Path('deployment/tap_monitor_v1.py').read_bytes()
ast.parse(monitor.decode('utf8'),filename='tap_monitor_v1.py')
files['tap_monitor_v1.py']=monitor

def modify(name,old,new):
    s=files[name].decode('utf8')
    if s.count(old)!=1:
        if new in s and old not in s:
            return
        raise AssertionError(f'{name}: expected unique anchor ({s.count(old)}): {old[:120]!r}')
    files[name]=s.replace(old,new).encode('utf8')

modify('market.py',
"""import bank""",
"""import bank
import tap_monitor_v1""")
modify('market.py',
"""                self.db.execute('UPDATE factories SET last_tap=? WHERE player=?',(now,p))""",
"""                self.db.execute('UPDATE factories SET last_tap=? WHERE player=?',(now,p))
                # A monitoring failure cannot roll back a legitimate tap or alter rewards.
                tap_monitor_v1.record(self.db,p,now,count)""")
modify('server.py',
"""                    if not write and self.path=='/api/admin/dashboard':
                        return self.reply(200,admin.dashboard(Game(a,clock,opens_at=0 if practice else OPEN_MS,read_only=True)))""",
"""                    if not write and self.path=='/api/admin/tap-monitor':
                        rows=a.db.execute(
                            '''SELECT p.student_id,p.display_name,p.class_number,
                               t.started_at,t.last_at,t.request_count,t.tap_count,
                               t.score,t.reasons,t.flagged_at,t.avg_interval_ms,t.cv,t.rate
                               FROM tap_monitor_state t JOIN players p ON p.id=t.player
                               WHERE t.score>0 OR t.flagged_at IS NOT NULL
                               ORDER BY t.score DESC,t.last_at DESC LIMIT 150'''
                        ).fetchall()
                        return self.reply(200,{'players':[dict(r) for r in rows], 'now':now,
                                               'note':'参考指標です。自動操作の確定証拠ではありません。'})
                    if not write and self.path=='/api/admin/dashboard':
                        return self.reply(200,admin.dashboard(Game(a,clock,opens_at=0 if practice else OPEN_MS,read_only=True)))""")
modify('static/admin.html',
"""<button role="tab" id="tab-funds" data-panel="funds" aria-controls="panel-funds" aria-selected="false">資金調整</button></nav>""",
"""<button role="tab" id="tab-funds" data-panel="funds" aria-controls="panel-funds" aria-selected="false">資金調整</button><button role="tab" id="tab-tap-monitor" data-panel="tap-monitor" aria-controls="panel-tap-monitor" aria-selected="false">不正操作検知</button></nav>""")
modify('static/admin.html',
"""<section id="panel-players" role="tabpanel" aria-labelledby="tab-players">""",
"""<section id="panel-tap-monitor" role="tabpanel" aria-labelledby="tab-tap-monitor" hidden>
<h2>不正操作検知</h2>
<p class="muted">サーバー側で受信したタップ操作の傾向を参考表示します。通信状態やまとめ送りに左右されるため、不正の断定には利用しないでください。自動BAN・操作制限はありません。</p>
<div class="toolbar"><button type="button" id="tap-monitor-refresh">検知情報を更新</button></div>
<p id="tap-monitor-status" role="status"></p>
<div id="tap-monitor-table" class="table-wrap"></div>
</section>
<section id="panel-players" role="tabpanel" aria-labelledby="tab-players">""")
modify('static/admin.js',
"""for(const b of document.querySelectorAll('[data-panel]'))b.onclick=()=>{""",
"""async function refreshTapMonitor(){
 const status=$('#tap-monitor-status');
 status.textContent='確認中…';
 try{
  const result=await api('tap-monitor');
  const items=result.players||[];
  table('#tap-monitor-table',
   ['学籍番号・名前','クラス','最高疑惑スコア','検知理由','最終検知日時','最終タップ日時','連続処理回数','合計タップ数','平均通信間隔','通信間隔CV','タップ処理速度'],
   items.map(p=>[
     String(p.student_id)+' · '+String(p.display_name||''),
     String(p.class_number||'')+'組',
     String(p.score)+'/100',
     p.reasons||'—',
     p.flagged_at?new Date(Number(p.flagged_at)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}):'未確定',
     new Date(Number(p.last_at)).toLocaleString('ja-JP',{timeZone:'Asia/Tokyo'}),
     String(p.request_count),String(p.tap_count),
     p.avg_interval_ms==null?'—':String(p.avg_interval_ms)+'ms',
     p.cv==null?'—':String(p.cv),
     p.rate==null?'—':String(p.rate)+'/秒'
   ]));
  status.textContent='監視開始後の記録 '+items.length+'人 · 自動操作の確定証拠ではありません。';
 }catch(e){
  status.textContent='取得できませんでした：'+e.message;
 }
}
$('#tab-tap-monitor').addEventListener('click',()=>{void refreshTapMonitor();});
$('#tap-monitor-refresh').addEventListener('click',()=>{void refreshTapMonitor();});
for(const b of document.querySelectorAll('[data-panel]'))b.onclick=()=>{""")

for f in ('market.py','server.py','tap_monitor_v1.py'):
    ast.parse(files[f].decode('utf8'),filename=f)
assert 'tap_monitor_v1.record(self.db,p,now,count)' in files['market.py'].decode()
assert "not write and self.path=='/api/admin/tap-monitor'" in files['server.py'].decode()
assert 'id="panel-tap-monitor"' in files['static/admin.html'].decode()
assert "refreshTapMonitor()" in files['static/admin.js'].decode()
assert 'tap_monitor_v1.record' not in files['server.py'].decode()
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,d in members:z.writestr(info,files[info.filename])
    if 'tap_monitor_v1.py' not in {i.filename for i,d in members}:
        z.writestr('tap_monitor_v1.py',monitor)
with ZipFile(io.BytesIO(out.getvalue())) as check:
    assert check.testzip() is None
    for info,d in members:
        if info.filename not in ('market.py','server.py','static/admin.html','static/admin.js','tap_monitor_v1.py'):
            assert check.read(info.filename)==d,info.filename
if archive.read_bytes()!=out.getvalue():archive.write_bytes(out.getvalue())
print('PASS: tap monitoring + admin-only read UI; game data and unrelated ZIP members untouched')

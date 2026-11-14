"""Install bandwidth-capped anti-autoclicker v2 into production game archive.
No added HTTP endpoints for players, no raw tap logs, no moderation actions.
"""
from pathlib import Path
from zipfile import ZipFile
import io,ast

path=Path('hare-machi-render.zip')
with ZipFile(path) as z:
    rows=[(x,z.read(x.filename)) for x in z.infolist()]
    comment=z.comment
f={x.filename:v for x,v in rows}

def change(name,a,b):
    s=f[name].decode('utf8')
    if s.count(a)!=1:
        if a not in s and b in s:return
        raise RuntimeError(f'{name}: expected one anchor, got {s.count(a)}: {a[:110]!r}')
    f[name]=s.replace(a,b).encode('utf8')

change('market.py','import tap_monitor_v1','import tap_monitor_v2')
change('market.py',
"    def act(self,token,key,kind,product='white',quantity=None,price=None,target_id=None):",
"    def act(self,token,key,kind,product='white',quantity=None,price=None,target_id=None,tap_meta=None):")
change('market.py',
"tap_monitor_v1.record(self.db,p,now,count)",
"tap_monitor_v2.record(self.db,p,now,count,tap_meta)")

change('server.py',
"result=g.act(token,data.get('key'),data.get('kind'),data.get('product','white'),data.get('quantity'),data.get('price'),data.get('target_id'))",
"result=g.act(token,data.get('key'),data.get('kind'),data.get('product','white'),data.get('quantity'),data.get('price'),data.get('target_id'),data.get('tap_meta') if data.get('kind')=='tap_batch' else None)")
change('server.py',
"""                    if not write and self.path=='/api/admin/tap-monitor':""",
"""                    if not write and self.path=='/api/admin/tap-monitor-events':
                        events=a.db.execute(
                            '''SELECT p.student_id,p.display_name,e.detected_at,e.score,
                               e.reasons,e.taps_1m,e.taps_5m,e.taps_30m,
                               e.rate_5m,e.rate_30m,e.client_samples
                               FROM tap_monitor_events e JOIN players p ON p.id=e.player
                               ORDER BY e.detected_at DESC LIMIT 100'''
                        ).fetchall()
                        return self.reply(200,{'events':[dict(v) for v in events],
                                               'note':'検知履歴は参考情報です。本人の不正を証明しません。'})
                    if not write and self.path=='/api/admin/tap-monitor':""")
change('server.py',
"t.score,t.reasons,t.flagged_at,t.avg_interval_ms,t.cv,t.rate",
"t.score,t.reasons,t.flagged_at,t.avg_interval_ms,t.cv,t.rate,"
"t.client_samples,t.client_regular_samples")

change('static/app.js',
"const tapQueue=[];",
"""const tapQueue=[];
let tapTelemetrySeq=0;
function tapMeta(batch){
 if(batch.count<5||!batch.times||batch.times.length<5)return null;
 const gaps=[];
 for(let i=1;i<batch.times.length;i++){
  const dt=batch.times[i]-batch.times[i-1];
  if(dt>=0&&dt<=30000)gaps.push(dt);
 }
 if(gaps.length<4)return null;
 const mean=gaps.reduce((a,b)=>a+b,0)/gaps.length;
 const variance=gaps.reduce((a,b)=>a+(b-mean)**2,0)/gaps.length;
 const cv=mean>0?Math.sqrt(variance)/mean:10;
 return [batch.count,Math.min(30000,Math.round(mean)),
         Math.min(10000,Math.round(cv*1000)),batch.trusted||0];
}""")
change('static/app.js',
""" batch.key??=crypto.randomUUID();
 sendingTaps=true;""",
""" batch.key??=crypto.randomUUID();
 // Sample at most one in 16 existing tap requests; never send a new request.
 if(batch.telemetry===undefined){
  tapTelemetrySeq++;
  batch.telemetry=tapTelemetrySeq%16===0?tapMeta(batch):null;
 }
 sendingTaps=true;""")
change('static/app.js',
"const response=await api('action',{kind:'tap_batch',product:batch.product,quantity:batch.count,key:batch.key});",
"const response=await api('action',{kind:'tap_batch',product:batch.product,quantity:batch.count,key:batch.key,...(batch.telemetry?{tap_meta:batch.telemetry}:{})});")
change('static/app.js',
"act('tap').onclick=()=>{",
"act('tap').onclick=(event)=>{")
change('static/app.js',
"""if(tail&&!tail.key&&tail.product===product&&tail.generation===generation&&tail.count<20)tail.count++;
 else tapQueue.push({product,count:1,generation,attempts:0});""",
"""if(tail&&!tail.key&&tail.product===product&&tail.generation===generation&&tail.count<20){
  tail.count++;
  tail.times.push(performance.now());
  if(event?.isTrusted)tail.trusted=(tail.trusted||0)+1;
 }else tapQueue.push({product,count:1,generation,attempts:0,times:[performance.now()],trusted:event?.isTrusted?1:0});""")
change('static/admin.html',
'<div id="tap-monitor-table" class="table-wrap"></div>',
"""<div id="tap-monitor-table" class="table-wrap"></div>
<h3>最近の高リスク検知履歴</h3>
<p class="muted">詳細履歴はこの画面を開いた場合のみ取得します。記録は高リスク時のみ、同一プレイヤーにつき6時間に最大1件です。</p>
<div id="tap-monitor-events" class="table-wrap"></div>""")
change('static/admin.js',
"""  status.textContent='監視開始後の記録 '+items.length+'人 · 自動操作の確定証拠ではありません。';""",
"""  status.textContent='監視開始後の記録 '+items.length+'人 · 自動操作の確定証拠ではありません。';
  const history=await api('tap-monitor-events');
  table('#tap-monitor-events',
   ['日時','プレイヤー','スコア','検知理由','直近1/5/30分のタップ','5分/30分平均(回/秒)'],
   (history.events||[]).map(e=>[
    new Date(Number(e.detected_at)).toLocaleString('ja-J',{timeZone:'Asia/Tokyo'}),
    String(e.student_id)+' · '+String(e.display_name||''),
    String(e.score)+'/100',e.reasons||'—',
    [e.taps_1m,e.taps_5m,e.taps_30m].join(' / '),
    [e.rate_5m,e.rate_30m].join(' / ')
   ]));""")

for name in ('market.py','server.py'):
    ast.parse(f[name].decode('utf8'),filename=name)
v2=Path('deployment/tap_monitor_v2.py').read_bytes()
ast.parse(v2.decode('utf8'),filename='tap_monitor_v2.py')
f['tap_monitor_v2.py']=v2
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,_ in rows:z.writestr(info,f[info.filename])
    if 'tap_monitor_v2.py' not in {info.filename for info,_ in rows}:
        z.writestr('tap_monitor_v2.py',v2)
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,raw in rows:
        if info.filename not in ('market.py','server.py','static/app.js','static/admin.js','static/admin.html','tap_monitor_v2.py'):
            assert z.read(info.filename)==raw,info.filename
    server=z.read('server.py').decode()
    assert server.index("if not admin.authorized")<server.index("if not write and self.path=='/api/admin/tap-monitor-events'")
    assert "tap_monitor_v2.record(self.db,p,now,count,tap_meta)" in z.read('market.py').decode()
    assert "tapTelemetrySeq%16===0" in z.read('static/app.js').decode()
path.write_bytes(out.getvalue())
print('PASS v2 monitor; no player polling, no moderation, unrelated files unchanged')

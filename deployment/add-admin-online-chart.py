"""Add low-bandwidth online player count charts to production archive.

On normal gameplay requests, deduplicated account presence is tracked at most
once per 45 seconds per running server. One sample per minute is persisted
for historical charts. No new client heartbeat requests.
"""
from pathlib import Path
from zipfile import ZipFile
import io,ast

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
def replace(name,old,new):
    s=files[name].decode('utf-8')
    if s.count(old)!=1:raise RuntimeError(f'Unexpected {name} anchor: {s.count(old)} / {old[:95]!r}')
    files[name]=s.replace(old,new).encode('utf-8')

# Server explicitly tracks one session per account, with no tracking of IP,
# device identifiers, page paths, or individual behavior.
replace('admin.py',"""    def settings(self):
""","""    @staticmethod
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
""")
replace('admin.py',
"""            self.db.execute('CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,expires_at BIGINT NOT NULL)')
""",
"""            self.db.execute('CREATE TABLE IF NOT EXISTS admin_sessions(token_hash TEXT PRIMARY KEY,expires_at BIGINT NOT NULL)')
            self.initialize_online(self.db)
""")
replace('server.py',"""    settings_lock=threading.Lock()
""","""    # Only one presence write per player per 45 seconds, reusing gameplay HTTP
    # requests rather than adding periodic client-to-server heartbeat traffic.
    presence_lock=threading.Lock()
    presence_seen={}
    def record_online(db,player_id,now):
        with presence_lock:
            previous=presence_seen.get(player_id,0)
            if now-previous<45000:return
            presence_seen[player_id]=now
            # Prune the small in-memory throttle table periodically.
            if len(presence_seen)>2000:
                stale=[key for key,t in presence_seen.items() if now-t>120000]
                for key in stale:presence_seen.pop(key,None)
        try:
            with db:Admin.note_online(db,player_id,now)
        except sqlite3.Error as error:
            with presence_lock:presence_seen.pop(player_id,None)
            logging.warning('Online presence update skipped (%s)',type(error).__name__)

    settings_lock=threading.Lock()
""")
replace('server.py',
"""                    if not write and self.path=='/api/admin/dashboard':
""",
"""                    if not write and self.path=='/api/admin/online':
                        return self.reply(200,admin.online_stats(now))
                    if not write and self.path=='/api/admin/dashboard':
""")
replace('server.py',
"""                try: identity=a.identity(token,now//1000)
                except ValueError: return self.reply(401,{'error':'ログインしてください。'})
""",
"""                try: identity=a.identity(token,now//1000)
                except ValueError: return self.reply(401,{'error':'ログインしてください。'})
                if self.path in ('/api/factory','/api/action','/api/snapshot'):
                    record_online(a.db,identity['id'],now)
""")
# Create an independent sampler thread for the main game instance, so samples
# continue while the admin UI is closed; no reads need the heavy game dashboard.
replace('server.py',
"""    if not cluster or role == 'A':
        threading.Thread(target=timer,daemon=True).start()
""",
"""    if not cluster or role == 'A':
        threading.Thread(target=timer,daemon=True).start()

        def online_sampler():
            # Avoid DB traffic when there are no user requests or when the
            # Render instance is suspended; absent samples are gaps, not zeros.
            while not stop.wait(60):
                a=None
                try:
                    a=Accounts(args.db,read_only=True,admin_only=True)
                    with a.db:
                        Admin.sample_online(a.db,int(time.time()*1000))
                except sqlite3.Error as error:
                    logging.warning('Online sample skipped (%s)',type(error).__name__)
                finally:
                    if a:a.db.close()
        threading.Thread(target=online_sampler,daemon=True).start()
""")

# Place new view alongside participant stats; keep existing financial tabs.
replace('static/admin.html',
"""<button role="tab" id="tab-players" data-panel="players" aria-controls="panel-players" aria-selected="true">参加者</button>""",
"""<button role="tab" id="tab-players" data-panel="players" aria-controls="panel-players" aria-selected="true">参加者</button><button role="tab" id="tab-online" data-panel="online" aria-controls="panel-online" aria-selected="false">オンライン人数</button>""")
replace('static/admin.html',
"""<section id="panel-rankings" role="tabpanel" aria-labelledby="tab-rankings" hidden>""",
"""<section id="panel-online" role="tabpanel" aria-labelledby="tab-online" hidden>
<h2>オンライン人数の推移</h2>
<p class="muted">直近2分以内にゲームと通信したアカウントを1人として集計。同じアカウントの複数操作は重複しません。</p>
<div class="stats">
<div class="stat"><span>現在のオンライン人数</span><strong id="online-count">—</strong></div>
<div class="stat"><span>表示期間の最大人数</span><strong id="online-peak">—</strong></div>
<div class="stat"><span>最後の計測</span><strong id="online-updated" style="font-size:16px">—</strong></div>
</div>
<div class="toolbar">
<label>表示期間<select id="online-range"><option value="60">過去1時間</option><option value="360">過去6時間</option><option value="1440" selected>過去24時間</option></select></label>
<button type="button" id="online-refresh">人数を更新</button>
</div>
<div id="online-graph" role="img" aria-label="オンライン人数の時系列グラフ" style="max-width:100%;overflow-x:auto"></div>
<p id="online-description" class="muted" role="status" aria-live="polite">計測データを読み込みます。</p>
<p class="muted">1分ごとに計測します。記録がない時間帯は0人とみなさず、グラフに空白として表示します。管理者画面を閉じていてもゲームが稼働している間は記録します。</p>
</section>
<section id="panel-rankings" role="tabpanel" aria-labelledby="tab-rankings" hidden>""")

admin_js=r'''let onlinePoints=[],onlineFetchedAt=0,onlineActive=false,onlineTimer=null,onlineBusy=false;
function renderOnlineGraph(){
 const range=Number($('#online-range').value);
 const last=Math.floor(onlineFetchedAt/60000);
 const first=last-range;
 const points=onlinePoints.filter(p=>p.minute>=first&&p.minute<=last);
 const maximum=points.reduce((m,p)=>Math.max(m,p.count),0);
 $('#online-peak').textContent=points.length?maximum+'人':'—';
 const graph=$('#online-graph');
 graph.replaceChildren();
 const ns='http://www.w3.org/2000/svg';
 const svg=document.createElementNS(ns,'svg');
 svg.setAttribute('viewBox','0 0 760 250');
 svg.setAttribute('width','100%');
 svg.setAttribute('role','img');
 svg.setAttribute('aria-label','過去'+(range===60?'1':range===360?'6':'24')+'時間のオンライン人数');
 svg.style.minWidth='320px';
 const add=(tag,attrs,text)=>{
  const node=document.createElementNS(ns,tag);
  for(const [k,v] of Object.entries(attrs))node.setAttribute(k,String(v));
  if(text!==undefined)node.textContent=text;
  svg.append(node);return node;
 };
 const left=46,right=744,top=18,bottom=211;
 const height=Math.max(1,maximum);
 const x=m=>left+(m-first)/range*(right-left);
 const y=count=>bottom-count/height*(bottom-top);
 for(let i=0;i<=4;i++){
  const count=Math.ceil(maximum*i/4);
  const yy=y(count);
  add('line',{x1:left,y1:yy,x2:right,y2:yy,stroke:'#d2ddd1','stroke-width':1});
  add('text',{x:left-7,y:yy+4,'text-anchor':'end','font-size':12,fill:'#526e68'},count);
 }
 for(let i=0;i<=4;i++){
  const tick=first+range*i/4;
  add('text',{x:x(tick),y:236,'text-anchor':i===0?'start':i===4?'end':'middle','font-size':11,fill:'#526e68'},
   new Date(tick*60000).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'}));
 }
 let segment=[];
 const drawSegment=()=>{
  if(!segment.length)return;
  if(segment.length>1)add('polyline',{points:segment.map(p=>x(p.minute)+','+y(p.count)).join(' '),
   fill:'none',stroke:'#167464','stroke-width':2.5,'stroke-linejoin':'round','stroke-linecap':'round'});
  else add('circle',{cx:x(segment[0].minute),cy:y(segment[0].count),r:3,fill:'#167464'});
  segment=[];
 };
 for(let i=0;i<points.length;i++){
  if(i>0&&points[i].minute-points[i-1].minute>1)drawSegment();
  segment.push(points[i]);
 }
 drawSegment();
 graph.append(svg);
 $('#online-description').textContent=points.length?
  '計測 '+points.length+'点 · 最大 '+maximum+'人 · '+new Date(onlineFetchedAt).toLocaleString('ja-JP')+' 時点'
  :'この期間にはまだ計測記録がありません。';
}
async function loadOnline(){
 if(onlineBusy)return;
 onlineBusy=true;
 try{
  const result=await api('online');
  onlinePoints=(result.samples||[]).map(p=>({minute:Number(p.minute),count:Number(p.count)}));
  onlineFetchedAt=Number(result.sampled_at)||Date.now();
  $('#online-count').textContent=Number(result.online)+'人';
  $('#online-updated').textContent=new Date(onlineFetchedAt).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit'});
  renderOnlineGraph();
 }catch(error){
  $('#online-description').textContent='人数の取得に失敗しました：'+error.message;
 }finally{onlineBusy=false;}
}
$('#online-range').onchange=renderOnlineGraph;
$('#online-refresh').onclick=()=>void loadOnline();
$('#tab-online').addEventListener('click',()=>{
 onlineActive=true;
 void loadOnline();
});
for(const tab of document.querySelectorAll('[data-panel]')){
 if(tab.id!=='tab-online')tab.addEventListener('click',()=>{onlineActive=false;});
}
onlineTimer=setInterval(()=>{
 if(onlineActive&&!document.hidden&&$('#dashboard')&&!$('#dashboard').hidden)void loadOnline();
},60000);
'''
replace('static/admin.js',
"""for(const b of document.querySelectorAll('[data-panel]'))b.onclick=""",
admin_js+"""for(const b of document.querySelectorAll('[data-panel]'))b.onclick=""")

for f in ('admin.py','server.py'):
    ast.parse(files[f].decode('utf-8'),filename=f)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('admin.py','server.py','static/admin.html','static/admin.js'):
            assert z.read(info.filename)==data
archive.write_bytes(out.getvalue())
print("PASS: track unique active accounts from existing requests, periodic samples, authenticated online graph")

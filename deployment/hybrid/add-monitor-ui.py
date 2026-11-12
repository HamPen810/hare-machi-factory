"""Add authenticated hybrid-router diagnostics to the existing admin page."""
from zipfile import ZipFile
from pathlib import Path
import io
archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
def change(path,old,new):
    s=files[path].decode('utf8')
    if s.count(old)!=1:
        raise RuntimeError(f'{path}: anchor count {s.count(old)}: {old[:100]}')
    files[path]=s.replace(old,new).encode('utf8')

change('static/admin.html',
"""<button role="tab" id="tab-online" data-panel="online" aria-controls="panel-online" aria-selected="false">オンライン人数</button>""",
"""<button role="tab" id="tab-online" data-panel="online" aria-controls="panel-online" aria-selected="false">オンライン人数</button><button role="tab" id="tab-hybrid" data-panel="hybrid" aria-controls="panel-hybrid" aria-selected="false">サーバー負荷</button>""")
change('static/admin.html',
"""<section id="panel-online" role="tabpanel" aria-labelledby="tab-online" hidden>""",
"""<section id="panel-hybrid" role="tabpanel" aria-labelledby="tab-hybrid" hidden>
<h2>Render / Oracle ハイブリッド処理</h2>
<p class="muted">Oracleが未設定の場合はRenderのみで処理します。数字はこのRenderプロセスの起動以降の累積です。</p>
<div class="stats">
<div class="stat"><span>Oracle接続</span><strong id="hybrid-connected">—</strong></div>
<div class="stat"><span>処理モード設定</span><strong id="hybrid-mode">—</strong></div>
<div class="stat"><span>処理中のHTTPリクエスト</span><strong id="hybrid-active">—</strong></div>
<div class="stat"><span>平均API応答時間（近似）</span><strong id="hybrid-latency">—</strong></div>
</div>
<p id="hybrid-notice" class="muted" role="status">サーバー状況を読み込みます。</p>
<button id="hybrid-refresh" type="button">最新状況に更新</button>
<h3>ルーティング実績</h3>
<div id="hybrid-metrics" class="table-wrap"></div>
<p class="muted">計測対象はアプリの通信遅延と同時処理数です。Oracle VMのCPU・メモリ使用率ではありません。</p>
</section>
<section id="panel-online" role="tabpanel" aria-labelledby="tab-online" hidden>""")

constjs=r"""let hybridBusy=false;
async function loadHybridStatus(){
 if(hybridBusy)return;
 hybridBusy=true;
 try{
  const data=await api('hybrid');
  $('#hybrid-connected').textContent=data.enabled?'接続設定済み':'Render単独';
  $('#hybrid-mode').textContent=data.mode==='auto'?'自動':data.mode||'—';
  $('#hybrid-active').textContent=String(data.active||0)+'件';
  $('#hybrid-latency').textContent=String(data.latency_ewma_ms||0)+' ms';
  $('#hybrid-notice').textContent=data.circuit_open
   ?'Oracleが不調のため、一時的にRenderへ切り戻しています。'
   :data.enabled?'Oracleへ振り分け可能です。実績は下の表を確認してください。'
   :'Oracleは未接続です。ゲームはRender単独で動作しています。';
  const labels={
   mode_normal:'Render通常処理',mode_speculative:'推測並列処理',
   mode_offload:'Oracle処理委託',forwarded:'Oracleへの送信',
   oracle_won:'Oracleの結果採用',render_won:'Renderの結果採用',
   fallback:'Renderへの自動切り戻し',oracle_errors:'Oracleエラー',
   circuit_opened:'遮断回数',speculative_limit:'並列処理数制限'
  };
  table('#hybrid-metrics',['指標','累計回数'],
   Object.entries(labels).map(([key,label])=>[label,String(data.metrics?.[key]||0)]));
 }catch(error){
  $('#hybrid-notice').textContent='サーバー負荷の取得に失敗しました：'+error.message;
 }finally{hybridBusy=false;}
}
$('#tab-hybrid').addEventListener('click',()=>void loadHybridStatus());
$('#hybrid-refresh').onclick=()=>void loadHybridStatus();
setInterval(()=>{
 if(!document.hidden&&!$('#panel-hybrid').hidden)void loadHybridStatus();
},30000);
"""
change('static/admin.js',
"""for(const b of document.querySelectorAll('[data-panel]'))b.onclick=""",
constjs+"""for(const b of document.querySelectorAll('[data-panel]'))b.onclick=""")

out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('static/admin.html','static/admin.js'):
            assert z.read(info.filename)==data
archive.write_bytes(out.getvalue())
print('PASS: hybrid router admin-only status UI added without touching game/business logic')

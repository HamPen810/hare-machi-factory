"""Admin UI-only restructuring. Preserve existing forms and transaction handlers.

Changes restricted to admin HTML/CSS, a one-line dashboard ready event,
static routing for a cacheable analytics script. No game calculations or
account/bank/tax/funds endpoints are modified.
"""
from pathlib import Path
from zipfile import ZipFile
import io,re,ast
archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:b for i,b in entries}
def once(name,old,new):
    s=files[name].decode('utf8')
    count=s.count(old)
    if count!=1:
        raise AssertionError(f'{name}: expected one anchor; found {count}: {old[:110]!r}')
    files[name]=s.replace(old,new,1).encode('utf8')

html=files['static/admin.html'].decode('utf8')
assert 'id="tab-tap-monitor"' in html
assert 'id="funds-form"' in html and 'id="bank-market"' in html
assert 'id="announcement-form"' in html and 'id="player-form"' in html
assert 'id="tab-overview"' not in html

# Extract operation controls wholesale; their IDs, attributes, and
# nested forms retain their exact bytes.
ops=re.search(r'(<section aria-labelledby="operations-title">.*?</section>)(?=<div class="toolbar"><div id="event")',html,re.S)
assert ops, 'Operations container not found'
operations=ops.group(1)
html=html[:ops.start()]+html[ops.end():]

# KPI cards belong on the overview tab, not above every tab.
stats='<div id="stats" class="stats"></div>'
assert html.count(stats)==1
html=html.replace(stats,'',1)

# Set up navigation first, and make Overview the only initially visible panel.
nav_match=re.search(r'<nav class="tabs" role="tablist" aria-label="管理画面">.*?</nav>',html,re.S)
assert nav_match
old_nav=nav_match.group(0)
assert 'id="tab-players"' in old_nav
new_nav=old_nav.replace('<nav class="tabs" role="tablist" aria-label="管理画面">',
    '<nav class="tabs" role="tablist" aria-label="管理画面">'
    '<button role="tab" id="tab-overview" data-panel="overview" aria-controls="panel-overview" aria-selected="true">分析・概要</button>',1)
new_nav=new_nav.replace('id="tab-players" data-panel="players" aria-controls="panel-players" aria-selected="true"',
    'id="tab-players" data-panel="players" aria-controls="panel-players" aria-selected="false"',1)
new_nav=new_nav.replace('</nav>',
    '<button role="tab" id="tab-operations" data-panel="operations" aria-controls="panel-operations" aria-selected="false">運用・設定</button></nav>',1)
html=html.replace(old_nav,new_nav,1)
before='<section id="panel-players" role="tabpanel" aria-labelledby="tab-players">'
assert html.count(before)==1
overview='''<section id="panel-overview" role="tabpanel" aria-labelledby="tab-overview">
<div class="an-title"><div><small class="muted">OPERATIONS ANALYTICS</small><h2>ゲーム分析ダッシュボード</h2></div><p id="analytics-stamp" class="muted">集計データを読み込み中</p></div>
<div id="stats" class="stats"></div>
<div class="an-section-title"><h3>詳細分析</h3><p class="muted">既存の管理者データを再利用します。追加の定期通信は行いません。</p></div>
<div class="an-toolbar">
<div class="an-subtabs" role="group" aria-label="分析内容">
<button type="button" class="an-subtab" data-group="players" aria-pressed="true">資産・クラス</button>
<button type="button" class="an-subtab" data-group="market" aria-pressed="false">市場の推移</button>
<button type="button" class="an-subtab" data-group="performance" aria-pressed="false">製造・経営成績</button>
</div>
<label class="an-market-range">市場の表示期間 <select id="an-market-window"><option value="30">直近30記録</option><option value="60" selected>直近60記録</option><option value="180">最大180記録</option></select></label>
</div>
<div id="analytics-content" aria-live="polite"></div>
<p class="an-note">グラフは分析用の参考値です。巨大な所持金や製造数は桁数に変換して比較します。通常の取引・資金調整は既存の専用タブで操作できます。</p>
</section>
<section id="panel-operations" role="tabpanel" aria-labelledby="tab-operations" hidden>
'''+operations+'''
</section>
'''
html=html.replace(before,overview+before.replace('>',' hidden>',1),1)

# Long operations blocks get collapsible subsections, without editing any
# controls or submitting forms. Defaults keep primary form visible.
bank=re.search(r'(<section id="panel-bank" role="tabpanel".*?</section>)',html,re.S)
assert bank, 'Bank tab missing'
bankbody=bank.group(1)
assert '<h3>総資産への指数課税</h3>' in bankbody
assert '<h3>市場の買い取り・出品</h3>' in bankbody
bankbody=bankbody.replace('<h3>総資産への指数課税</h3>',
   '</details><details class="an-fold"><summary>総資産への指数課税</summary><h3>総資産への指数課税</h3>',1)
bankbody=bankbody.replace('<h3>市場の買い取り・出品</h3>',
   '</details><details class="an-fold"><summary>市場の買い取り・出品</summary><h3>市場の買い取り・出品</h3>',1)
bankbody=bankbody.replace('<section id="panel-bank" role="tabpanel" aria-labelledby="tab-bank" hidden>',
   '<section id="panel-bank" role="tabpanel" aria-labelledby="tab-bank" hidden>'
   '<details class="an-fold" open><summary>銀行・税率の設定</summary>',1)
assert bankbody.endswith('</section>')
bankbody=bankbody[:-len('</section>')]+'</details></section>'
html=html[:bank.start()]+bankbody+html[bank.end():]

# Optional: collapse lower-priority operation settings with no handler changes.
operations_section=re.search(r'(<section id="panel-operations".*?</section>\s*</section>)',html,re.S)
assert operations_section
oldops=operations_section.group(1)
modified=oldops.replace('<form id="announcement-form">',
    '<details class="an-fold" open><summary>全体へのお知らせ</summary><form id="announcement-form">',1)
modified=modified.replace('</form>\n<details><summary>ルールブックを編集',
    '</form></details>\n<details class="an-fold"><summary>ルールブックを編集',1)
assert '<details class="an-fold" open><summary>全体へのお知らせ</summary>' in modified
html=html.replace(oldops,modified,1)

# Simplify typography for numeric review. Keep no content/script control logic.
css='''\n/* Administrative usability upgrade. Original form names and submission semantics preserved. */
body{font-family:system-ui,-apple-system,"Yu Gothic",Meiryo,sans-serif;background:#f0f4f3;color:#1c3535}
button,input,select,textarea{font-family:inherit}
main{max-width:1440px;padding:18px 24px 32px}
header{padding:5px 2px 12px}
header h1{font-size:clamp(20px,2.4vw,28px);letter-spacing:.01em}
#dashboard>section{background:#fff;border-color:#dbe6e3;box-shadow:0 2px 14px rgba(17,66,59,.045)}
#dashboard>.tabs{position:sticky;top:0;z-index:25;flex-wrap:nowrap;overflow-x:auto;white-space:nowrap;padding:9px;background:rgba(246,250,249,.97);border:1px solid #dbe6e3;border-radius:14px;box-shadow:0 4px 22px rgba(24,62,59,.085);scrollbar-width:thin;overscroll-behavior-x:contain}
.tabs button{flex:0 0 auto;border-color:transparent;background:transparent;font-weight:700;min-height:44px;transition:background .16s,color .16s}
.tabs button[aria-selected="true"]{background:#116f68;color:#fff;box-shadow:0 2px 8px rgba(17,111,104,.2)}
#event{font-weight:700}
#dashboard>.toolbar{flex-wrap:wrap;padding:0 2px}
#dashboard>.toolbar #account{margin-left:auto;flex-wrap:wrap}
#updated{display:block;margin:4px 0 12px;font-variant-numeric:tabular-nums}
#panel-operations>section{border:0;padding:0;background:transparent;margin:0}
#panel-operations .toolbar{align-items:end}
#panel-operations .an-fold{max-width:980px}
#panel-overview .stats{grid-template-columns:repeat(3,minmax(0,1fr));margin:12px 0 22px}
#panel-overview .stat{background:#f6faf8;border-color:#e2ebe8;min-width:0}
#panel-overview .stat span{font-size:12px;color:#526e68}
#panel-overview .stat strong{font-family:system-ui,sans-serif;font-size:clamp(16px,2.0vw,24px);line-height:1.4;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
.an-title{display:flex;justify-content:space-between;align-items:start;flex-wrap:wrap;gap:10px}
.an-title h2{font-size:clamp(19px,2.2vw,24px);margin:3px 0}
.an-title p{margin:0;font-size:12px}
.an-section-title{display:flex;align-items:baseline;gap:15px;flex-wrap:wrap;margin-top:10px}
.an-section-title h3{font-size:17px;margin:0}
.an-section-title p{margin:0}
.an-toolbar{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin:14px 0}
.an-subtabs{display:flex;gap:6px;flex-wrap:wrap}
.an-subtabs button[aria-pressed="true"]{background:#116f68;color:#fff;border-color:#116f68}
.an-market-range{display:flex;align-items:center;gap:8px;font-size:12px;color:#526e68}
.an-market-range select{font-size:14px}
.an-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.an-chart{border:1px solid #dfebe6;border-radius:14px;background:#fbfdfc;padding:16px;min-width:0}
.an-chart h3{font-size:16px;margin:0 0 3px}
.an-chart-caption{margin:0;color:#55716c;font-size:12px}
.an-chart-foot{color:#5f736e;font-size:11px;margin:7px 0 0}
.an-svg{display:block;width:100%;height:auto;min-height:185px;max-height:270px}
.an-kpis{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:0 0 12px}
.an-kpi{padding:12px;background:#eef7f3;border-radius:12px}
.an-kpi span{display:block;font-size:11px;color:#57716b}
.an-kpi strong{display:block;font-size:21px;line-height:1.4;font-variant-numeric:tabular-nums}
.an-note{color:#657b75;font-size:12px;margin:16px 0 0}
.an-fold{border:1px solid #dce9e5;border-radius:12px;padding:0 15px;margin:12px 0;background:#fafdfb}
.an-fold>summary{cursor:pointer;list-style:none;font-weight:700;padding:14px 2px;position:relative}
.an-fold>summary::after{content:"＋";position:absolute;right:6px;font-size:18px;color:#32776c}
.an-fold[open]>summary::after{content:"−"}
.an-fold>summary::-webkit-details-marker{display:none}
.an-fold[open]{padding-bottom:16px}
.an-fold form{margin-top:10px}
.table-wrap{max-height:min(60vh,560px);border-radius:10px;border:1px solid #e0e9e6;overflow:auto}
table{font-family:system-ui,"Yu Gothic",Meiryo,sans-serif}
th{z-index:2;background:#eff5f1;font-size:12px}
td{font-size:13px}
button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #f0ac53;outline-offset:2px}
@media(max-width:900px){.an-grid{grid-template-columns:1fr}.an-svg{max-height:300px}}
@media(max-width:600px){
 main{padding:10px}
 header{align-items:start}
 #dashboard>.tabs{border-radius:10px;padding:5px;margin:9px 0}
 .tabs button{padding:9px 12px;font-size:13px}
 section{padding:14px}
 #panel-overview .stats,.an-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}
 .an-chart{padding:12px}
 .an-svg{min-height:160px}
 #dashboard>.toolbar #account{margin-left:0}
 .toolbar>*{max-width:none}
 .an-market-range{width:100%;justify-content:flex-start}
}
'''
assert html.count('</style>')==1
html=html.replace('</style>',css+'</style>',1)
# Chart code is a separate static asset cached by the existing static mechanism.
assert html.count('<script src="/admin.js" defer></script>')==1
html=html.replace('<script src="/admin.js" defer></script>',
                  '<script src="/admin.js" defer></script><script src="/admin-ux.js" defer></script>',1)

# Earlier monitored-history patches appended the same read-only area twice.
# Remove only the exact duplicate, retaining the original UI and all handlers.
old_history='''<h3>最近の高リスク検知履歴</h3>
<p class="muted">詳細履歴はこの画面を開いた場合のみ取得します。記録は高リスク時のみ、同一プレイヤーにつき6時間に最大1件です。</p>
<div id="tap-monitor-events" class="table-wrap"></div>'''
assert html.count(old_history)==2, ('unexpected monitor panel',html.count(old_history))
html=html.replace(old_history,'',1)

# Every existing form and input ID must be unchanged and unique.
orig=files['static/admin.html'].decode('utf8')
old_ids=re.findall(r'\bid="([^"]+)"',orig)
new_ids=re.findall(r'\bid="([^"]+)"',html)
for id in set(old_ids):
    assert new_ids.count(id)==old_ids.count(id)-(1 if id=='tap-monitor-events' else 0), ('ID count changed',id,old_ids.count(id),new_ids.count(id))
for id in ('tab-overview','tab-operations','panel-overview','panel-operations','analytics-content','analytics-stamp','an-market-window'):
    assert new_ids.count(id)==1, ('New UI ID missing/duplicate',id,new_ids.count(id))
for form in ('announcement-form','rulebook-form','player-form','bank-config','bank-market','funds-form'):
    assert html.count('id="'+form+'"')==1,form
for control in ('funds-amount','funds-target','bank-config','asset-tax-preview','asset-tax-apply','funds-apply','funds-cancel','admin-bank-status','tab-tap-monitor'):
    assert html.count('id="'+control+'"')==1,control
assert html.count('aria-selected="true"')>=1
files['static/admin.html']=html.encode('utf8')

# Only a one-line notification added to existing admin render; do not alter any
# handlers for money, banking, player resets, notifications or moderation.
js=files['static/admin.js'].decode('utf8')
old="function render(){const s=data.summary;"
assert js.count(old)==1
js=js.replace(old,
    "function render(){window.__adminDashboardSnapshot=data;document.dispatchEvent(new CustomEvent('admin-dashboard-ready',{detail:data}));const s=data.summary;",1)
# Correct a duplicated read-only monitor-history renderer left by a prior
# repeated deploy. No finance, settings or moderation handler is modified.
needle="  const history=await api('tap-monitor-events');"
assert js.count(needle)==2, ('Unexpected existing history render count',js.count(needle))
start1=js.index(needle)
start2=js.index(needle,start1+len(needle))
terminator="   ]));"
end1=js.index(terminator,start1)+len(terminator)
end2=js.index(terminator,start2)+len(terminator)
assert js[start1:end1]==js[start2:end2], 'History render blocks diverged'
js=js[:start2]+js[end2:]
files['static/admin.js']=js.encode('utf8')

# Serve one extra cacheable JS file. No new API endpoints or database queries.
name='server.py'
server=files[name].decode('utf8')
anchor="'/admin','/admin/','/admin.js'):"
assert server.count(anchor)==1
server=server.replace(anchor,"'/admin','/admin/','/admin.js','/admin-ux.js'):",1)
mapping="'/admin.js':'admin.js'}[self.path]"
assert server.count(mapping)==1
server=server.replace(mapping,"'/admin.js':'admin.js','/admin-ux.js':'admin-ux.js'}[self.path]",1)
ast.parse(server,filename='server.py')
files[name]=server.encode('utf8')

files['static/admin-ux.js']=Path('deployment/admin-ux-20261114.js').read_bytes()

out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    existing=set()
    for info,d in entries:
        z.writestr(info,files[info.filename]);existing.add(info.filename)
    if 'static/admin-ux.js' not in existing:z.writestr('static/admin-ux.js',files['static/admin-ux.js'])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,d in entries:
        if info.filename not in ('static/admin.html','static/admin.js','server.py','static/admin-ux.js'):
            assert z.read(info.filename)==d,('unintended file change',info.filename)
assert 'id="tab-overview"' in html and 'id="tab-operations"' in html
assert 'id="panel-tap-monitor"' in html
assert 'window.__adminDashboardSnapshot=data' in js
assert "'/admin-ux.js':'admin-ux.js'" in server
archive.write_bytes(out.getvalue())
print('PASS: moved operations and KPIs into tabs, preserved every existing control, added client-side analytics')

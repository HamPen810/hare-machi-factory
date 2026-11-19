"""Add a mobile-accessible exact V2 leaderboard and sales history graph.

Only the V2 laboratory page and its client script are updated. Existing real
game/app.js, market, bank, admins and transaction writers remain unchanged.
"""
from pathlib import Path
from zipfile import ZipFile
import os,tempfile
archive=Path('hare-machi-render.zip')
extension=Path('deployment/v2_reports_ui_extension.js').read_text('utf-8')
marker='/* V2 rankings and historical chart rendering: authenticated, read-only. */'
with ZipFile(archive) as z:
    if z.testzip():raise RuntimeError('Invalid archive')
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    original={i.filename:data for i,data in entries}
for file in ('v2_read_reports.py','static/v2.js','static/v2.html'):
    if file not in original:raise RuntimeError('Missing V2 report API or UI: '+file)
js=original['static/v2.js'].decode('utf-8')
if marker not in js:js=js+'\n'+extension
html=original['static/v2.html'].decode('utf-8')
markup="""<section class="card" aria-label="V2ランキング">
<h2>V2ランキング</h2>
<p class="muted">従来のゲーム結果を無損失でV2数値に変換して表示します。ランキングの集計元は従来のデータです。</p>
<form id="v2-rank-form">
<label for="v2-rank-metric">指標</label>
<select id="v2-rank-metric"><option value="manufactured">製造数</option>
<option value="revenue">売上</option><option value="net_profit">純利益</option></select>
<label for="v2-rank-scope">対象</label>
<select id="v2-rank-scope"><option value="individual">個人</option><option value="classes">クラス</option></select>
<button type="submit">ランキングを表示</button>
</form><div id="v2-rank-result" aria-live="polite"></div>
</section>
<section class="card" aria-label="V2データグラフ">
<h2>V2売上推移グラフ</h2>
<p class="muted">市場履歴の金額をV2の桁数で表示する対数グラフです。確定取引を変更しません。</p>
<button type="button" id="v2-data-load">グラフを表示</button>
<div id="v2-data-result" aria-live="polite"></div>
</section>
"""
if 'id="v2-rank-form"' not in html:
    anchor='<script src="/v2.js" defer></script>'
    if html.count(anchor)!=1:raise RuntimeError('V2 script anchor changed')
    html=html.replace(anchor,markup+anchor,1)
updated={'static/v2.js':js.encode(),'static/v2.html':html.encode()}
fd,tmp=tempfile.mkstemp(dir='.',suffix='.zip');os.close(fd)
try:
    with ZipFile(tmp,'w') as z:
        for item,data in entries:z.writestr(item,updated.get(item.filename,data))
    with ZipFile(tmp) as z:
        if z.testzip():raise RuntimeError('Modified archive failed CRC')
        for name,data in original.items():
            if z.read(name)!=updated.get(name,data):raise RuntimeError('Unexpected ZIP alteration')
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.remove(tmp)
print('V2_RANKING_AND_GRAPH_MOBILE_UI_INSTALLED')
print('ALL_ECONOMY_WRITERS_UNCHANGED')

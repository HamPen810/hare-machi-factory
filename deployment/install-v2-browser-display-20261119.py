"""Install exact S1 number formatting and bounded exponent charts in ZIP UI.

Preserve server logic, all economic writers, existing assets, and SQL byte-for-byte.
"""
from pathlib import Path
from zipfile import ZipFile
import os,tempfile
archive=Path('hare-machi-render.zip')
helper=Path('deployment/v2-browser-numbers.js').read_text('utf-8')
with ZipFile(archive) as original:
    if original.testzip():raise RuntimeError('ZIP damaged')
    entries=[(i,original.read(i.filename)) for i in original.infolist()]
    files={i.filename:v for i,v in entries}
marker='/* Installed exact V2 browser formatter */'
legacy=files['static/numbers.js'].decode()
if marker not in legacy:
    if 'window.TeruNumber' not in legacy:raise RuntimeError('Unknown existing formatter')
    ext="""(function(){
      const old=window.TeruNumber.fmt;
      window.TeruNumber.fmt=function(value){
       return typeof value==='string'&&value.startsWith('S1:')
        ? window.TeruV2Number.compact(value):old(value);
      };
      window.TeruNumber.v2=window.TeruV2Number;
    })();"""
    files['static/numbers.js']=(legacy+'\n'+marker+'\n'+helper+'\n'+ext).encode()
v2js=files['static/v2.js'].decode()
if marker not in v2js:
    v2js=marker+'\n'+helper+'\n'+v2js
old="  state=next;$('cash').textContent=next.cash;$('balance').hidden=false;"
new="""  state=next;$('cash').textContent=window.TeruV2Number.compact(next.cash)+' ('+next.cash+')';$('balance').hidden=false;
  const chart=$('v2-stock-chart');chart.replaceChildren();
  for(const item of next.stock){
   const entry=document.createElement('div');entry.className='v2-stock-entry';
   const desc=document.createElement('span');desc.textContent=item.product+': '+window.TeruV2Number.compact(item.quantity);
   const bar=document.createElement('div');bar.className='v2-stock-bar';
   const fill=document.createElement('div');fill.className='v2-stock-fill';
   fill.style.width=(window.TeruV2Number.chartMagnitude(item.quantity,300)/3)+'%';
   bar.appendChild(fill);entry.append(desc,bar);chart.appendChild(entry);
  }"""
if new not in v2js:
    if v2js.count(old)!=1:raise RuntimeError('V2 UI anchor changed')
    v2js=v2js.replace(old,new)
files['static/v2.js']=v2js.encode()
html=files['static/v2.html'].decode()
if 'id="v2-stock-chart"' not in html:
    old='<button type="button" id="refresh">資産を再取得</button>'
    if html.count(old)!=1:raise RuntimeError('V2 refresh anchor changed')
    html=html.replace(old,'<p class="muted">在庫の規模（対数目盛。300桁以上は同じ長さで表示）</p><div id="v2-stock-chart"></div>'+old)
    html=html.replace('</style>','.v2-stock-entry{margin:10px 0;display:grid;gap:4px;font-size:.84rem}.v2-stock-bar{height:9px;background:#0e182a;border-radius:6px;overflow:hidden}.v2-stock-fill{height:100%;background:#80cbb0}</style>')
files['static/v2.html']=html.encode()
fd,tmp=tempfile.mkstemp(dir='.',suffix='.zip');os.close(fd)
try:
    with ZipFile(tmp,'w') as out:
        for info,_ in entries:out.writestr(info,files[info.filename])
    with ZipFile(tmp) as z:
        if z.testzip():raise RuntimeError('Result ZIP damaged')
        for name,raw in files.items():
            if z.read(name)!=raw:raise RuntimeError('ZIP verification failed')
        for info,raw in entries:
            if info.filename not in ('static/numbers.js','static/v2.js','static/v2.html') and z.read(info.filename)!=raw:
                raise RuntimeError('Unexpected modification '+info.filename)
    os.replace(tmp,archive)
finally:
    if os.path.exists(tmp):os.unlink(tmp)
print('V2_EXACT_NUMBER_DISPLAY_PATCH_OK')
print('LIVE_ECONOMY_CODE_UNCHANGED')

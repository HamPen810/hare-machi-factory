"""Publish visual-only game-wide Yomogi and read-only multi-chart admin lab.

Changes limited to CSS, admin HTML, one cacheable static JS route and the new
static JS file. The game's database, gameplay, and all financial operations
are not modified. Fails closed if the current source differs.
"""
from zipfile import ZipFile
from pathlib import Path
import io,ast
p=Path('hare-machi-render.zip')
with ZipFile(p) as z:
    rows=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:v for i,v in rows}
def replace(name,old,new):
    s=files[name].decode('utf8')
    if s.count(old)!=1:raise RuntimeError('Unexpected '+name+' anchor, count '+str(s.count(old)))
    files[name]=s.replace(old,new,1).encode('utf8')

css=files['static/island.css'].decode('utf8')
assert "@font-face{font-family:IslandHand;src:url('/fonts/Yomogi-Regular.ttf')" in css
marker='/* UNIVERSAL_YOMOGI_GAME_FONT_20261114 */'
font_rule=marker+'''
html body #teru-playtest,
html body #teru-playtest *,
html body #teru-playtest *::before,
html body #teru-playtest *::after,
html body #teru-playtest svg text,
html body #teru-playtest svg tspan,
html body #teru-playtest svg foreignObject *,
html body button,
html body input,
html body textarea,
html body select,
html body option,
html body dialog,
html body label {
 font-family:IslandHand,'Yomogi',cursive !important;
}
'''
if marker in css:css=css[:css.index(marker)]+font_rule
else:css+='\\n'+font_rule
files['static/island.css']=css.encode('utf8')

html=files['static/admin.html'].decode('utf8')
assert 'id="panel-analysis"' in html
assert "id=\"insight-lab\"" not in html
style=Path('deployment/admin-insight-lab-20261114.css').read_text('utf8')
html=html.replace('</style>',style+'\\n</style>',1)
src='<script src="/admin-cockpit.js" defer></script>'
assert html.count(src)==1
html=html.replace(src,src+'<script src="/admin-insight-lab.js" defer></script>',1)
files['static/admin.html']=html.encode('utf8')

s=files['server.py'].decode('utf8')
old="'/admin.js','/admin-ux.js','/admin-cockpit.js'):"
new="'/admin.js','/admin-ux.js','/admin-cockpit.js','/admin-insight-lab.js'):"
assert s.count(old)==1,('static route',s.count(old))
s=s.replace(old,new,1)
old="'/admin-cockpit.js':'admin-cockpit.js'}[self.path]"
new="'/admin-cockpit.js':'admin-cockpit.js','/admin-insight-lab.js':'admin-insight-lab.js'}[self.path]"
assert s.count(old)==1,('static map',s.count(old))
s=s.replace(old,new,1)
files['server.py']=s.encode('utf8')
files['static/admin-insight-lab.js']=Path('deployment/admin-insight-lab-20261114.js').read_bytes()

for name in ('server.py','market.py','bank.py','exact.py'):
    ast.parse(files[name].decode('utf8'),filename=name)
assert "tap_monitor_v2.record" in files['market.py'].decode()
assert "sunpress_price(level,self._sunpress_anchor(p))" in files['market.py'].decode()
assert files['static/admin-insight-lab.js'].count(b'admin-dashboard-ready')==1
for id in ('funds-amount','funds-form','bank-config','bank-market','announcement-form','panel-analysis','panel-messages','panel-notices','admin-mobile-nav'):
    assert html.count('id="'+id+'"')==1,id
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    names=set()
    for info,_ in rows:z.writestr(info,files[info.filename]);names.add(info.filename)
    if 'static/admin-insight-lab.js' not in names:z.writestr('static/admin-insight-lab.js',files['static/admin-insight-lab.js'])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,d in rows:
        if info.filename not in ('static/island.css','static/admin.html','server.py','static/admin-insight-lab.js'):
            assert z.read(info.filename)==d,('unexpected business logic change',info.filename)
if out.getvalue()!=p.read_bytes():p.write_bytes(out.getvalue())
print('PASS: game Yomogi across widgets; 16-chart on-demand admin lab, original money logic unchanged')

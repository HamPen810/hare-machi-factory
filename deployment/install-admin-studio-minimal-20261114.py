"""Visual-only refresh of the existing manager cockpit.
Append a single CSS override block; preserve exact original JS, forms,
server routes, accounts, transaction arithmetic, and every other ZIP member.
"""
from zipfile import ZipFile
from pathlib import Path
import io, re, ast

archive=Path("hare-machi-render.zip")
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
html=files['static/admin.html'].decode('utf-8')
assert 'id="tab-analysis"' in html and 'id="panel-messages"' in html
assert 'id="admin-mobile-nav"' in html and 'id="console-record-dialog"' in html
assert '@font-face{font-family:IslandHand;' in html
style=Path("deployment/admin-studio-minimal-20261114.css").read_text(encoding="utf-8")
marker="/* HARE-MACHI / STUDIO CONSOLE"
assert style.count(marker)==1
assert "font-family:IslandRound" in style
assert "font-family:var(--hm-round)" in style
assert "var(--hm-hand)" in style
if marker in html:
    # If redeployed after the initial styling, replace only the preceding
    # visual override, not any behavioral JS or financial element.
    start=html.index("@font-face {\n font-family:IslandRound;\n")
    end=html.index("</style>",start)
    html=html[:start]+style+"\n"+html[end:]
else:
    assert html.count("</style>")==1
    html=html.replace("</style>",style+"\n</style>",1)
files['static/admin.html']=html.encode('utf-8')
for name in ('market.py','server.py','bank.py','exact.py'):
    ast.parse(files[name].decode('utf-8'),filename=name)
assert html.count('id="funds-amount"')==1
assert html.count('id="announcement-form"')==1
assert html.count('id="bank-config"')==1
assert html.count('id="bank-market"')==1
assert html.count('id="rulebook-form"')==1
assert html.count('id="panel-analysis"')==1
assert html.count('id="panel-notices"')==1
assert html.count('id="panel-messages"')==1
assert html.count('font-family:IslandRound')>=1
assert html.count('var(--hm-hand)')>=1
out=io.BytesIO()
with ZipFile(out,"w") as z:
    z.comment=comment
    for info,_ in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename!='static/admin.html':
            assert z.read(info.filename)==data,('Unexpected code changed',info.filename)
if out.getvalue()!=archive.read_bytes():archive.write_bytes(out.getvalue())
print('PASS: matching game fonts; visual override only; all game and admin behavior byte-for-byte unchanged')

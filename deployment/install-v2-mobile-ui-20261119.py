"""Expose the existing V2 calculator to mobile users while preserving all writers.

Only the production ZIP static pages and server's static GET routing change.
Never connects to DB, changes currency, changes any API or V2 cutover flag.
"""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
import ast,os,tempfile

zipfile=Path("hare-machi-render.zip")
html=Path("deployment/v2_ui.html").read_bytes()
js=Path("deployment/v2_ui.js").read_bytes()
if b'/api/v2/balances' not in js or b'/api/v2/preview' not in js:
    raise RuntimeError("V2 client must call existing authenticated endpoints")
with ZipFile(zipfile) as z:
    if z.testzip() is not None:raise RuntimeError("Original archive corrupt")
    entries=[(info,z.read(info.filename)) for info in z.infolist()]
    files={info.filename:data for info,data in entries}
server=files["server.py"].decode("utf-8")
old="""            a=None
            try:
"""
new="""            if not write and self.path in ('/v2', '/v2.js'):
                asset='v2.html' if self.path=='/v2' else 'v2.js'
                kind='text/html; charset=utf-8' if asset.endswith('.html') else 'text/javascript; charset=utf-8'
                return self.static_reply(asset,kind,STATIC_CODE_CACHE)
            a=None
            try:
"""
if new not in server:
    if server.count(old)!=1:raise RuntimeError("Static GET route insertion anchor changed")
    server=server.replace(old,new,1)
ast.parse(server,filename="server.py")

index=files["static/index.html"].decode("utf-8")
link='<a href="/v2" id="v2-lab-link" style="display:block;max-width:220px;margin:8px auto 22px;text-align:center;font-size:12px;opacity:.78">V2 超巨大数シミュレーター（試算専用）</a>'
if link not in index:
    if index.count("</body>")!=1:raise RuntimeError("Main page body ending changed")
    index=index.replace("</body>",link+"</body>",1)
files["server.py"]=server.encode("utf-8")
files["static/index.html"]=index.encode("utf-8")
for name,data in {"static/v2.html":html,"static/v2.js":js}.items():
    if name in files and files[name]!=data:raise RuntimeError("Existing UI asset differs: "+name)
    files[name]=data

fd,tmp=tempfile.mkstemp(dir=".",suffix=".zip")
os.close(fd)
try:
    with ZipFile(tmp,"w") as z:
        for info,_ in entries:
            z.writestr(info,files[info.filename])
        for name in ("static/v2.html","static/v2.js"):
            if name not in dict((info.filename,None) for info,_ in entries):
                z.writestr(name,files[name],compress_type=ZIP_DEFLATED)
    with ZipFile(tmp) as check:
        if check.testzip() is not None:raise RuntimeError("Patched ZIP corrupt")
        for name,data in files.items():
            if check.read(name)!=data:raise RuntimeError("ZIP entry mismatch "+name)
        for name,data in dict((info.filename,data) for info,data in entries).items():
            if name not in ("server.py","static/index.html") and check.read(name)!=data:
                raise RuntimeError("Unexpected modification to live economy: "+name)
    os.replace(tmp,zipfile)
finally:
    if os.path.exists(tmp):os.unlink(tmp)

print("V2_MOBILE_UI_INSTALLED")
print("ALL_GAME_API_AND_ECONOMY_WRITERS_UNCHANGED")

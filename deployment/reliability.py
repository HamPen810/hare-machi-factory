"""Patch the deployed archive to improve request reliability without changing the schema."""
import ast
import io
import zipfile
from pathlib import Path

archive = Path("hare-machi-render.zip")
with zipfile.ZipFile(archive) as z:
    postgres = z.read("postgres.py").decode("utf-8").replace("\r\n", "\n")
    js = z.read("static/app.js").decode("utf-8").replace("\r\n", "\n")

def patch_once(source, needle, replacement, label):
    if source.count(needle) != 1:
        raise ValueError(f"{label}: expected one match, found {source.count(needle)}")
    return source.replace(needle, replacement)

postgres = patch_once(
    postgres,
    "if not gate.acquire(timeout=5):",
    "if not gate.acquire(timeout=18):",
    "writer gate",
)
postgres = patch_once(
    postgres,
    """connection.execute("SET statement_timeout = '8s'")""",
    """connection.execute("SET statement_timeout = '20s'")""",
    "statement timeout",
)
# Each user action has a UUID key, so retries can safely reuse the same key
# and return the originally committed action result.
start = js.index("async function api(path,data){")
end = js.index("\nfunction choosePage(", start)
old = js[start:end]
assert "const timer=setTimeout(()=>controller.abort(),15000);" in old
assert "const response=await fetch('/api/'+path," in old
assert "clearTimeout(timer)" in old
js = js[:start] + """async function api(path,data){
 const requestGeneration=generation;
 const transactional=path==='action' && typeof data?.key==='string' && data.key.length>0;
 const attempts=transactional?2:1;
 for(let attempt=0;attempt<attempts;attempt++){
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),transactional?35000:15000);
  try{
   const response=await fetch('/api/'+path,{method:data?'POST':'GET',headers:data?{'Content-Type':'application/json'}:{},body:data?JSON.stringify(data):undefined,credentials:'same-origin',signal:controller.signal});
   const body=await response.json().catch(()=>{throw Error('サーバーから応答がありません。少し待ってお試しください。');});
   if(!response.ok){
    if(body.maintenance){
     generation++;snapshot=null;pendingAction=null;tapQueue.length=0;
     $('#game').hidden=true;$('#auth').hidden=false;$('#auth-form').hidden=true;$('#maintenance-note').hidden=false;
    }
    if(response.status===401&&requestGeneration===generation){$('#game').hidden=true;$('#auth').hidden=false;snapshot=null;}
    if(transactional&&attempt+1<attempts&&[502,503,504].includes(response.status)&&!body.maintenance)continue;
    throw Object.assign(Error(body.error||'通信に失敗しました。'),{status:response.status});
   }
   return body;
  }catch(error){
   if(transactional&&attempt+1<attempts&&(!error.status||[502,503,504].includes(error.status)))continue;
   if(controller.signal.aborted)throw Error('応答に時間がかかっています。画面を確認してから再度お試しください。');
   throw error;
  }finally{clearTimeout(timer);}
 }
 throw Error('通信に失敗しました。');
}""" + js[end:]
ast.parse(postgres, filename="postgres.py")
out = io.BytesIO()
with zipfile.ZipFile(archive) as source, zipfile.ZipFile(out, "w") as dest:
    dest.comment = source.comment
    for entry in source.infolist():
        payload = (
            postgres.encode("utf-8") if entry.filename == "postgres.py" else
            js.encode("utf-8") if entry.filename == "static/app.js" else
            source.read(entry)
        )
        dest.writestr(entry, payload)
with zipfile.ZipFile(io.BytesIO(out.getvalue())) as check:
    assert check.testzip() is None
    assert check.read("postgres.py") == postgres.encode("utf-8")
    assert check.read("static/app.js") == js.encode("utf-8")
archive.write_bytes(out.getvalue())
print("Reliability patch applied")

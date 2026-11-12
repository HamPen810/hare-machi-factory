"""Fix administrator fund target select, independent of slow dashboard.

Admin-only /api/admin/funds GET returns minimal player options alongside
history. All financial write logic, ranking accounting and server auth remain
unchanged.
"""
from pathlib import Path
from zipfile import ZipFile
import ast,io
path=Path("hare-machi-render.zip")
with ZipFile(path) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}
def change(name,old,new):
    s=files[name].decode()
    if s.count(old)!=1:
        raise RuntimeError(f"{name}: old anchor occurrences {s.count(old)}: {old[:100]!r}")
    files[name]=s.replace(old,new).encode()
change('admin.py',"""    def fund_history(self):
""","""    def fund_players(self):
        return [dict(row) for row in self.db.execute(
            'SELECT p.student_id,p.display_name,COALESCE(f.cash,500) cash '
            'FROM players p LEFT JOIN factories f ON f.player=p.id '
            'ORDER BY p.student_id')]

    def fund_history(self):
""")
change('server.py',"""                        return self.reply(200,{'history':admin.fund_history()})
""","""                        return self.reply(200,{'players':admin.fund_players(),
                                               'history':admin.fund_history()})
""")
change('static/admin.js',"""let fundsPending=null, fundsBusy=false;
function populateFundsTargets(){
""","""let fundsPending=null, fundsBusy=false, fundsPlayers=[];
function populateFundsTargets(){
""")
change('static/admin.js',""" if(data?.players){
  for(const person of data.players){
""",""" if(fundsPlayers.length){
  for(const person of fundsPlayers){
""")
change('static/admin.js',""" const player=data?.players?.find(p=>p.student_id===student_id);
""",""" const player=fundsPlayers.find(p=>p.student_id===student_id);
""")
change('static/admin.js',"""  +(remaining<0n?'（残高不足のため実行不可）':'');
""","""  +(remaining<0n?'（マイナス残高）':'');
""")
change('static/admin.js',"""$('#tab-funds').addEventListener('click',()=>{
 void refresh().then(()=>{
  populateFundsTargets();
  void loadFundsHistory();
 });
});
""","""$('#tab-funds').addEventListener('click',()=>{
 void loadFundsHistory();
});
""")
change('static/admin.js',"""  const result=await api('funds');
  const rows=(result.history||[]).map(x=>[
""","""  fundsStatus.textContent='アカウントを読み込み中…';
  const result=await api('funds');
  fundsPlayers=result.players||[];
  populateFundsTargets();
  updateFundsPreview();
  fundsStatus.textContent='';
  const rows=(result.history||[]).map(x=>[
""")
change('static/admin.js',""" const person=data?.players?.find(x=>x.student_id===student_id);
""",""" const person=fundsPlayers.find(x=>x.student_id===student_id);
""")
change('static/admin.js',"""  await refresh();
  populateFundsTargets();
  fundsTarget.value=request.student_id;
  updateFundsPreview();
  await loadFundsHistory();
""","""  await loadFundsHistory();
  fundsTarget.value=request.student_id;
  updateFundsPreview();
  // Refresh heavyweight dashboard separately; a chart failure must not
  // disable player selection or transaction history.
  void refresh(true);
""")
# Do not reset funds list from the heavyweight dashboard.
change('static/admin.js',"""render();populateFundsTargets();updateFundsPreview();notice('');""",
"""render();notice('');""")
# On successful login load target options independently, not only after clicking.
change('static/admin.js',"""  await openControls();
  notice('');
""","""  await openControls();
  notice('');
""")
# Trigger once on already authenticated manager session; also refresh
# after login (without waiting for large dashboard).
change('static/admin.js',"""  await openControls();
  notice('');
 }catch(error){notice(error.message);}
""","""  await openControls();
  void loadFundsHistory();
  notice('');
 }catch(error){notice(error.message);}
""")
change('static/admin.js',"""openControls().catch(()=>{});
""","""openControls().then(()=>loadFundsHistory()).catch(()=>{});
""")
# Reset local account list after logout.
change('static/admin.js',"""version++;data=null;$('#dashboard').hidden=true;""",
"""version++;data=null;fundsPlayers=[];populateFundsTargets();$('#dashboard').hidden=true;""")
for name in ('admin.py','server.py'):ast.parse(files[name].decode(),filename=name)
output=io.BytesIO()
with ZipFile(output,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(output.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('admin.py','server.py','static/admin.js'):
            assert z.read(info.filename)==data
path.write_bytes(output.getvalue())
print('PASS: fund target options use lightweight authenticated API, independent of rankings dashboard')

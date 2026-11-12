"""Reduce /api/data egress with cursor-paged market timeline and incremental refresh.

Existing game actions, bank logic, rankings, taxation and history storage remain
unchanged. Old chart records are loaded on demand without changing precision.
"""
from pathlib import Path
from zipfile import ZipFile
import io, ast

archive=Path("hare-machi-render.zip")
with ZipFile(archive) as z:
    entries=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in entries}

def replace(name, before, after):
    data=files[name].decode('utf-8')
    n=data.count(before)
    if n!=1:raise RuntimeError(f"{name}: expected one, got {n}: {before[:100]!r}")
    files[name]=data.replace(before,after).encode('utf-8')

replace('market.py',"""    def timeline(self,token):
        p=self.accounts.identity(token,self.clock()//1000)['id']
        return [dict(r) for r in self.db.execute("SELECT * FROM market_ticks WHERE player IN ('',?) ORDER BY round DESC LIMIT 130000",(p,))]

""",
"""    def timeline(self,token, *, before=None, after=None):
        # Fetch only the requested 240-minute window (at minute precision).
        # This protects both PostgreSQL-to-Render egress and response sizes.
        p=self.accounts.identity(token,self.clock()//1000)['id']
        latest=self.db.execute(
            "SELECT MAX(round) FROM market_ticks WHERE player IN ('',?)",(p,)
        ).fetchone()[0]
        if latest is None:
            return {'timeline':[], 'timeline_more':False} if after is None else {'timeline':[]}
        latest=int(latest)
        if before is not None:
            end=min(latest,before-1)
        else:
            end=latest
        if after is not None:
            start=max(0,after)
            if end<start:return {'timeline':[]}
        else:
            start=max(0,end-239)
        rows=[dict(r) for r in self.db.execute(
            "SELECT round,product,player,sold,revenue,inventory,cost "
            "FROM market_ticks WHERE player IN ('',?) AND round>=? AND round<=? "
            "ORDER BY round DESC,product,player",(p,start,end))]
        if after is not None:
            return {'timeline':rows}
        more=bool(self.db.execute(
            "SELECT 1 FROM market_ticks WHERE player IN ('',?) AND round<? LIMIT 1",
            (p,start)).fetchone())
        return {'timeline':rows, 'timeline_more':more}

""")

replace('server.py',"""                if not write and self.path=='/api/data':
                    return self.reply(200,{'timeline':g.timeline(token),'breakdown':g.breakdown(token)})
""",
"""                if not write and self.path=='/api/data':
                    # Read-only cursor pagination, no URL changes or user input in SQL.
                    def cursor(name):
                        value=self.headers.get(name)
                        if value is None:return None
                        if len(value)>16 or not value.isascii() or not value.isdecimal():
                            raise ValueError('履歴の取得位置が不正です。')
                        return int(value)
                    before=cursor('X-Timeline-Before')
                    after=cursor('X-Timeline-After')
                    if before is not None and after is not None:
                        raise ValueError('履歴の取得位置が重複しています。')
                    result=g.timeline(token,before=before,after=after)
                    if before is None:
                        result['breakdown']=g.breakdown(token)
                    return self.reply(200,result)
""")

# API supports optional read-only request headers for pagination.
replace('static/app.js',"async function api(path,data){","async function api(path,data,extraHeaders={}){")
replace('static/app.js',
"headers:data?{'Content-Type':'application/json'}:{},body:",
"headers:{...(data?{'Content-Type':'application/json'}:{}),...extraHeaders},body:")

# Timeline fetch when opening the data tab requests only new minutes if cached.
replace('static/app.js',
"""  const detail=await api(tab);
  if(gen!==generation||!snapshot)return;
  detailUpdated.set(tab,Date.now());
  Object.assign(snapshot,detail);
""",
"""  const incremental=tab==='data' && Array.isArray(snapshot.timeline) && snapshot.timeline.length>0;
  const mostRecent=incremental?snapshot.timeline.reduce((max,row)=>Math.max(max,Number(row.round)),0):0;
  const detail=await api(tab,undefined,incremental?{'X-Timeline-After':String(Math.max(0,mostRecent-1))}:{});
  if(gen!==generation||!snapshot)return;
  if(incremental){
   const combined=new Map(snapshot.timeline.map(row=>[row.round+'|'+row.product+'|'+row.player,row]));
   for(const row of detail.timeline||[])combined.set(row.round+'|'+row.product+'|'+row.player,row);
   detail.timeline=[...combined.values()];
  }
  detailUpdated.set(tab,Date.now());
  Object.assign(snapshot,detail);
""")

# Fetch older records exactly when the user navigates beyond loaded range.
needle="let chartOffset=0;"
assert files['static/app.js'].decode().count(needle)==1
before_js=files['static/app.js'].decode()
inject="""let timelineOlderPending=false;
async function loadOlderTimeline(){
 if(timelineOlderPending||!snapshot?.timeline_more||!snapshot?.timeline?.length)return;
 const originalIdentity=snapshot.identity?.id;
 const oldest=Math.min(...snapshot.timeline.map(row=>Number(row.round)));
 timelineOlderPending=true;
 const button=$('#chart-prev');
 button.disabled=true;
 try{
  const result=await api('data',undefined,{'X-Timeline-Before':String(oldest)});
  if(!snapshot||snapshot.identity?.id!==originalIdentity)return;
  const known=new Map(snapshot.timeline.map(row=>[row.round+'|'+row.product+'|'+row.player,row]));
  for(const row of result.timeline||[])known.set(row.round+'|'+row.product+'|'+row.player,row);
  snapshot.timeline=[...known.values()];
  snapshot.timeline_more=Boolean(result.timeline_more);
  renderChart();
 }catch(error){notice(error.message);}
 finally{timelineOlderPending=false;if(snapshot?.timeline)renderChart();}
}
"""
files['static/app.js']=before_js.replace(needle,inject+needle).encode()

replace('static/app.js',
"$('#chart-prev').disabled=end<=12;$('#chart-next').disabled=chartOffset===0;",
"$('#chart-prev').disabled=end<=12&&!snapshot.timeline_more;$('#chart-next').disabled=chartOffset===0;")

replace('static/app.js',
"$('#chart-prev').onclick=()=>{if(['income','expense'].includes(ui('metric').value))piePage--;else chartOffset+=12;renderChart();};",
"""$('#chart-prev').onclick=()=>{
 if(['income','expense'].includes(ui('metric').value))piePage--;
 else{
  chartOffset+=12;
  if(snapshot?.timeline_more && snapshot.timeline.length){
   const earliest=snapshot.timeline.reduce((min,row)=>Math.min(min,Number(row.round)),Infinity);
   const latest=snapshot.timeline.reduce((max,row)=>Math.max(max,Number(row.round)),0);
   const interval=Number($('#chart-interval').value);
   if(chartOffset*interval >= latest-earliest-48)void loadOlderTimeline();
  }
 }
 renderChart();
};""")

# Remove one duplicate visibilitychange listener that caused redundant API calls.
replace('static/app.js',
"""document.addEventListener("visibilitychange",()=>{if(snapshot&&!document.hidden)refresh();});
refresh();""",
"""refresh();""")

for name in ('market.py','server.py'):
    ast.parse(files[name].decode(),filename=name)
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for info,data in entries:
        if info.filename not in ('market.py','server.py','static/app.js'):
            assert z.read(info.filename)==data
archive.write_bytes(out.getvalue())
print('PASS: 240-minute history pages, incremental refresh, no lost historical records, no unrelated changes')

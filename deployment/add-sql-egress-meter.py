"""Measure SQL query and bound-parameter bytes sent to external PostgreSQL.

No raw SQL, parameters, credentials, hostnames, identifiers or query data
are logged. Estimates application payload only, not TLS/protocol overhead.
"""
from pathlib import Path
from zipfile import ZipFile
import io, ast

archive=Path('hare-machi-render.zip')
with ZipFile(archive) as z:
    entries=[(info,z.read(info.filename)) for info in z.infolist()]
    comment=z.comment
files={info.filename:data for info,data in entries}
pg=files['postgres.py'].decode('utf-8')
begin="from threading import Lock\n"
assert pg.count(begin)==1
pg=pg.replace(begin,begin+"import json\nimport time\n",1)
anchor="AUTH_GATE = Lock()\n"
assert pg.count(anchor)==1
telemetry='''SQL_METER_LOCK=Lock()
SQL_METER_START=time.monotonic()
SQL_METER={}

def measure_sql_outbound(sql, params):
    """Count query/parameter bytes without retaining any raw content."""
    global SQL_METER_START, SQL_METER
    verb=sql.lstrip().split(None,1)[0].upper() if sql.strip() else 'OTHER'
    if verb not in ('SELECT','INSERT','UPDATE','DELETE','WITH','BEGIN','COMMIT','ROLLBACK'):
        verb='OTHER'
    try:
        nbytes=len(sql.encode('utf-8'))+sum(
            len(str(value).encode('utf-8')) for value in (params or ()) if value is not None)
    except (ValueError,TypeError,OverflowError):
        nbytes=len(sql)
    now=time.monotonic()
    report=None
    with SQL_METER_LOCK:
        counts=SQL_METER.setdefault(verb,[0,0])
        counts[0]+=1
        counts[1]+=nbytes
        if now-SQL_METER_START>=60:
            report={'service':os.environ.get('RENDER_SERVICE_NAME','unknown'),
                    'window_s':round(now-SQL_METER_START),
                    'queries':sum(v[0] for v in SQL_METER.values()),
                    'estimated_outbound_query_bytes':sum(v[1] for v in SQL_METER.values()),
                    'by_operation':{key:{'count':v[0],'query_bytes':v[1]}
                                    for key,v in SQL_METER.items()}}
            SQL_METER={}
            SQL_METER_START=now
    if report:
        import logging
        logging.warning('SQL_BANDWIDTH_REPORT %s',
                        json.dumps(report,ensure_ascii=False,separators=(',',':')))

'''
pg=pg.replace(anchor,anchor+telemetry,1)
needle="        sql = query.strip()\n"
assert pg.count(needle)==1
pg=pg.replace(needle,needle+"        measure_sql_outbound(sql,params)\n",1)
ast.parse(pg,filename='postgres.py')
files['postgres.py']=pg.encode()
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for info,data in entries:z.writestr(info,files[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    assert z.read('postgres.py').count(b'SQL_BANDWIDTH_REPORT')==1
    for info,data in entries:
        if info.filename!='postgres.py':assert z.read(info.filename)==data
archive.write_bytes(out.getvalue())
print('PASS: privacy-safe aggregate PostgreSQL outbound query-byte sampling')

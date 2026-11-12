"""Instrument actual serialized, compressed HTTP response bytes by route.

Only logs aggregate path buckets and HTTP response status classes, with no
player identifiers, IP addresses, query strings, request bodies or tokens.
This does not change routes, response bodies, cache headers, auth, or DB.
"""
from pathlib import Path
from zipfile import ZipFile
import ast
import io

archive=Path("hare-machi-render.zip")
with ZipFile(archive) as z:
    entries=[(info,z.read(info.filename)) for info in z.infolist()]
    comment=z.comment
content={info.filename:data for info,data in entries}
source=content["server.py"].decode("utf-8")
marker='    settings_cache=None\n'
assert source.count(marker)==1, "Unexpected make_server location"
meter_code='''    # Per-process, server-side response byte meter.
    # A route label is never derived from an arbitrary URL or user data.
    bandwidth_lock=threading.Lock()
    bandwidth_started=time.monotonic()
    bandwidth_totals={}

    def measure_bandwidth(method, route, status, raw_bytes, wire_bytes, gzipped):
        nonlocal bandwidth_started, bandwidth_totals
        now=time.monotonic()
        known = route in API_PATHS or route in (
            '/', '/api/site', '/api/weather', '/api/market-quotes',
            '/health', '/admin', '/admin/', '/app.js', '/admin.js',
            '/numbers.js', '/tabs.js', '/weather.js', '/polish.js',
            '/island.css', '/polish.css'
        ) or route.startswith('/api/admin/')
        label = route if known else ('/assets/*' if route.startswith(('/assets/', '/fonts/')) else '/other')
        # Keep metric cardinality bounded; never log arbitrary admin paths.
        if route.startswith('/api/admin/') and route not in (
            '/api/admin/settings', '/api/admin/dashboard', '/api/admin/player',
            '/api/admin/bank', '/api/admin/login', '/api/admin/logout'
        ):
            label='/api/admin/*'
        key=(method+' '+label)
        report=None
        with bandwidth_lock:
            counts=bandwidth_totals.setdefault(key, [0,0,0,0,0,0])
            counts[0]+=1
            counts[1]+=wire_bytes
            counts[2]+=raw_bytes
            counts[3]+=int(gzipped)
            counts[4]+=int(status>=400)
            counts[5]+=int(status==304)
            if now-bandwidth_started>=60:
                report={
                    'service':os.environ.get('RENDER_SERVICE_NAME','unknown'),
                    'window_s':round(now-bandwidth_started),
                    'total_responses':sum(v[0] for v in bandwidth_totals.values()),
                    'total_bytes':sum(v[1] for v in bandwidth_totals.values()),
                    'by_route':[
                        {'route':route, 'requests':v[0],
                         'bytes':v[1], 'uncompressed_bytes':v[2],
                         'gzipped':v[3], 'errors':v[4], 'not_modified':v[5]}
                        for route,v in sorted(bandwidth_totals.items(),
                                              key=lambda x:x[1][1],reverse=True)
                    ]
                }
                bandwidth_totals={}
                bandwidth_started=now
        if report:
            logging.warning('BANDWIDTH_REPORT %s',
                            json.dumps(report,ensure_ascii=False,separators=(',',':')))

'''
source=source.replace(marker,marker+meter_code)
snippet='''            self.send_response(status)
            if status!=304:
'''
replace='''            # Measure the actual serialized response length after Gzip.
            # Header bytes/TLS overhead are excluded, so this is an estimate
            # of billable outbound bytes rather than Render's exact counter.
            measure_bandwidth(self.command, self.path.split('?',1)[0],
                              status, len(data) if not compressed else raw_length,
                              0 if status==304 else len(data), compressed)
            self.send_response(status)
            if status!=304:
'''
assert source.count(snippet)==1
source=source.replace('''            compressed=False
            compressible=kind.startswith(('application/json','text/'))
''','''            compressed=False
            raw_length=len(data)
            compressible=kind.startswith(('application/json','text/'))
''')
source=source.replace(snippet,replace)
assert source.count('BANDWIDTH_REPORT')==1
ast.parse(source,filename="server.py")
content["server.py"]=source.encode("utf-8")
out=io.BytesIO()
with ZipFile(out,"w") as dst:
    dst.comment=comment
    for info,data in entries:
        dst.writestr(info,content[info.filename])
with ZipFile(io.BytesIO(out.getvalue())) as check:
    assert check.testzip() is None
    for info,data in entries:
        if info.filename!="server.py":
            assert check.read(info.filename)==data,info.filename
    assert b'BANDWIDTH_REPORT' in check.read('server.py')
archive.write_bytes(out.getvalue())
print("PASS: aggregate route-level compressed-byte telemetry; other game files unchanged")

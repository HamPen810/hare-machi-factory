"""Audit the exact production ZIP for live V2 cutover compatibility; read-only.

Only source-code metadata is printed. No credentials, database traffic,
code modifications, or production assets involved.
"""
import ast,json,re
from collections import Counter
from zipfile import ZipFile

with ZipFile('hare-machi-render.zip') as z:
    for name in ('server.py','accounts.py','market.py','bank.py','admin.py','exact.py','static/app.js','static/admin.js','static/data.js','static/numbers.js'):
        if name not in z.namelist():
            print('MISSING',name);continue
        src=z.read(name).decode('utf-8')
        print('SOURCE',name,'bytes',len(src))
        if name.endswith('.py'):
            tree=ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and any(x in node.name.lower() for x in (
                   'action','ship','market','buy','sell','offer','listing','price','trade','upgrade',
                   'tap','bank','admin','fund','grant','collect','debt','forgiv','settle',
                   'tax','rank','data','chart','dash','profit','snapshot','inventory','stock','factory')):
                    snippet=ast.get_source_segment(src,node) or ''
                    queries=[]
                    for match in re.finditer(r'(?is)(?:UPDATE|INSERT INTO|DELETE FROM|SELECT|REPLACE INTO)\\s+[a-z_]+',snippet):
                        queries.append(re.sub(r'\\s+',' ',match.group(0)).upper())
                    print('FN',name,node.lineno,node.end_lineno,node.name,'SQL',','.join(dict.fromkeys(queries))[:350])
            print('CONVERSION',name,{x:len(re.findall(r'\\b'+x+r'\\s*\\(',src)) for x in ('int','str','float','Decimal')})
        else:
            for token in ('Number(', 'BigInt(', 'parseFloat(', 'parseInt(', '.toFixed(', 'JSON.stringify', 'chart', 'ranking'):
                count=src.count(token)
                if count:print('JS',name,token,count)
print('AUDIT_FINISHED_NO_PRODUCTION_WRITES')

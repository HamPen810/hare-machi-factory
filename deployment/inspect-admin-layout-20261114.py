"""One-time read-only introspection of current packaged admin user interface."""
from zipfile import ZipFile
import re,html
with ZipFile('hare-machi-render.zip') as z:
    files={name:z.read(name).decode('utf-8') for name in ('static/admin.html','static/admin.js','static/admin-ux.js','server.py','admin.py')}
h=files['static/admin.html'];j=files['static/admin.js'];server=files['server.py'];admin=files['admin.py']
print('=== ADMIN HTML NAV ===')
m=re.search(r'<nav class="tabs".*?</nav>',h,re.S)
print(m.group() if m else 'NOT FOUND')
print('=== ADMIN HTML PANEL IDS, FORM IDS ===')
print(re.findall(r'<(?:section|form|div|dialog|details|button)[^>]*id="([^"]+)"',h))
print('=== ADMIN PAGE SECTION SHORT CONTENT ===')
for id in re.findall(r'<section id="(panel-[^"]+)"',h):
    pos=h.find('id="'+id+'"')
    print(id,repr(re.sub('<[^>]+>',' ',h[pos:pos+260])[:220]))
print('=== OPERATIONS FULL MARKUP ===')
q=h.find('<section id="panel-operations"')
print(h[q:q+10000])
print('=== BULLETIN HTML ===')
for match in list(re.finditer(r'(bulletin|message|notice|announcement|お知らせ|メッセージ)',h,re.I))[:35]:
    print(match.group(),repr(h[max(0,match.start()-170):match.start()+350]))
print('=== BULLETIN JS ===')
for match in list(re.finditer(r'(bulletin|message|announcement|お知らせ|メッセージ)',j,re.I))[:35]:
    print(match.group(),repr(j[max(0,match.start()-140):match.start()+400]))
print('=== BULLETIN SERVER ROUTES ===')
for match in list(re.finditer(r'(bulletin|message|announcement|admin/dashboard)',server,re.I))[:28]:
    print(match.group(),repr(server[max(0,match.start()-140):match.start()+420]))
print('=== BULLETIN ADMIN API ===')
for match in list(re.finditer(r'(bulletin|message|announcement)',admin,re.I))[:22]:
    print(match.group(),repr(admin[max(0,match.start()-140):match.start()+480]))
print('=== ADMIN LENGTHS ===',[(k,len(v)) for k,v in files.items()])

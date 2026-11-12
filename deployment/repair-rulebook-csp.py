"""Put rulebook tabs in the server's existing allowed /tabs.js and /island.css.
The server enforces CSP script-src 'self': standalone inline JS is blocked.
New /rulebook*.js URLs are not allowlisted. Avoid both failure modes.
"""
from pathlib import Path
import io, re, zipfile
src=Path('hare-machi-render.zip')
with zipfile.ZipFile(src) as z:
    original=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
    content={i.filename:data for i,data in original}
def strip_marked(raw,start,end):
    return re.sub(re.escape(start)+r'.*?'+re.escape(end), '', raw, flags=re.S)
html=content['static/index.html'].decode('utf-8')
html=strip_marked(html,'<!-- RULEBOOK_INLINE_BEGIN -->','<!-- RULEBOOK_INLINE_END -->')
html=re.sub(r'<script id="rb-inline-scripts">.*?</script>', '',html,flags=re.S)
html=re.sub(r'<script\s+src="/rulebook-[^"]+"\s+defer></script>', '',html)
html=re.sub(r'<link\s+rel="stylesheet"\s+href="/rulebook-[^"]+">', '',html)
assert 'src="/tabs.js"' in html and 'href="/island.css"' in html
# Preserve the exact game markup, except for the old failed injections.
content['static/index.html']=html.encode('utf-8')
js=content['static/tabs.js'].decode('utf-8')
js=strip_marked(js,'/* RULEBOOK_TABS_START */','/* RULEBOOK_TABS_END */')
addjs='\n/* RULEBOOK_TABS_START */\n'+Path('deployment/rulebook-tabs.js').read_text()+'\n'+Path('deployment/rulebook-custom-tabs.js').read_text()+'\n/* RULEBOOK_TABS_END */\n'
content['static/tabs.js']=(js+addjs).encode('utf-8')
css=content['static/island.css'].decode('utf-8')
css=strip_marked(css,'/* RULEBOOK_TABS_START */','/* RULEBOOK_TABS_END */')
addcss='\n/* RULEBOOK_TABS_START */\n'+Path('deployment/rulebook-tabs.css').read_text()+'\n'+Path('deployment/rulebook-custom-tabs.css').read_text()+'\n/* RULEBOOK_TABS_END */\n'
content['static/island.css']=(css+addcss).encode('utf-8')
with zipfile.ZipFile(src,'w') as z:
    z.comment=comment
    for i,data in original:
        z.writestr(i,content[i.filename])
with zipfile.ZipFile(src) as z:
    assert z.testzip() is None
    assert z.read('static/tabs.js').count(b'/* RULEBOOK_TABS_START */')==1
    assert z.read('static/island.css').count(b'/* RULEBOOK_TABS_START */')==1
    assert b'rb-inline-scripts' not in z.read('static/index.html')
    assert b'/rulebook-tabs.js' not in z.read('static/index.html')
    for i,data in original:
        if i.filename not in ('static/tabs.js','static/island.css','static/index.html'):
            assert z.read(i.filename)==data
print('PASS: tab code in CSP-permitted files; no blocked scripts; game logic unchanged')

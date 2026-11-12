from pathlib import Path
from zipfile import ZipFile
import io

archive=Path('hare-machi-render.zip')
replacements={
 'static/rulebook-tabs.js':Path('deployment/rulebook-tabs.js').read_bytes(),
 'static/rulebook-tabs.css':Path('deployment/rulebook-tabs.css').read_bytes(),
 'static/rulebook-custom-tabs.js':Path('deployment/rulebook-custom-tabs.js').read_bytes(),
 'static/rulebook-custom-tabs.css':Path('deployment/rulebook-custom-tabs.css').read_bytes(),
}
with ZipFile(archive) as src:
    html=src.read('static/index.html').decode('utf-8')
    if 'rulebook-tabs.js' not in html:
        assert '</body>' in html and '</head>' in html
        html=html.replace('</head>','<link rel="stylesheet" href="/rulebook-tabs.css?v=1"></head>',1)
        html=html.replace('</body>','<script src="/rulebook-tabs.js?v=1" defer></script></body>',1)
    if 'rulebook-custom-tabs.js' not in html:
        assert '</body>' in html and '</head>' in html
        html=html.replace('</head>','<link rel="stylesheet" href="/rulebook-custom-tabs.css?v=2"></head>',1)
        html=html.replace('</body>','<script src="/rulebook-custom-tabs.js?v=2" defer></script></body>',1)
    replacements['static/index.html']=html.encode('utf-8')
    out=io.BytesIO()
    with ZipFile(out,'w') as dst:
        dst.comment=src.comment
        seen=set()
        for member in src.infolist():
            seen.add(member.filename)
            dst.writestr(member,replacements.get(member.filename,src.read(member)))
        for name,content in replacements.items():
            if name not in seen:
                dst.writestr(name,content,compress_type=8)
archive.write_bytes(out.getvalue())
with ZipFile(archive) as check:
    assert check.testzip() is None
    for name,content in replacements.items():
        assert check.read(name)==content
    assert check.read('static/index.html').count(b'rulebook-tabs.js')==1
    assert check.read('static/index.html').count(b'rulebook-custom-tabs.js')==1
print('Rulebook assets packaged safely')

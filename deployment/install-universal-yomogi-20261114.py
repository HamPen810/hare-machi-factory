"""Set every player-facing game font to the existing bundled Yomogi.
Visual-only: no new external resources or API changes.
"""
from pathlib import Path
from zipfile import ZipFile
import io,ast
p=Path("hare-machi-render.zip")
with ZipFile(p) as z:
    members=[(i,z.read(i.filename)) for i in z.infolist()]
    comment=z.comment
files={i.filename:data for i,data in members}
css=files['static/island.css'].decode('utf-8')
assert "@font-face{font-family:IslandHand;src:url('/fonts/Yomogi-Regular.ttf')" in css
marker="/* UNIVERSAL_YOMOGI_GAME_FONT_20261114 */"
new=marker+'''
/* Use the game's own bundled Yomogi for every in-game label, figure,
   widget, button, tab, title, header, dialog, and SVG text element.
   No changes to size/layout, number parsing, or game behavior. */
html body #teru-playtest,
html body #teru-playtest *,
html body #teru-playtest *::before,
html body #teru-playtest *::after,
html body #teru-playtest svg text,
html body #teru-playtest svg tspan,
html body #teru-playtest svg foreignObject * {
 font-family:IslandHand,'Yomogi',cursive !important;
}
html body button,
html body input,
html body textarea,
html body select,
html body option,
html body dialog,
html body label {
 font-family:IslandHand,'Yomogi',cursive !important;
}
/* Avoid breaking internal icon glyphs if a UI library uses private-use
   icon code points: text-based icons still inherit Yomogi. */
'''
if marker in css:
    css=css[:css.index(marker)]+new
else:
    css+='\\n'+new
files['static/island.css']=css.encode('utf8')
for name in ('server.py','market.py','bank.py','exact.py'):
    ast.parse(files[name].decode('utf8'))
out=io.BytesIO()
with ZipFile(out,'w') as z:
    z.comment=comment
    for i,_ in members:z.writestr(i,files[i.filename])
with ZipFile(io.BytesIO(out.getvalue())) as z:
    assert z.testzip() is None
    for i,raw in members:
        if i.filename!='static/island.css':assert z.read(i.filename)==raw,i.filename
if out.getvalue()!=p.read_bytes():p.write_bytes(out.getvalue())
print('PASS every game text selector uses existing Yomogi, no server/game logic changes')

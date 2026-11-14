from zipfile import ZipFile
import re
with ZipFile("hare-machi-render.zip") as z:
 print("STATIC FILES", [x for x in z.namelist() if x.startswith("static/") and (x.endswith(".css") or x.endswith(".html") or x.endswith(".woff2"))])
 for name in [x for x in z.namelist() if x.startswith("static/") and x.endswith((".css",".html"))]:
  txt=z.read(name).decode('utf-8',errors='replace')
  matches=[m.group() for m in re.finditer(r'(?:@font-face\s*\{[^}]+\}|font-family\s*:[^;}]{1,200})',txt,re.I|re.S)]
  print("FONT_SOURCE",name, matches[:30])
 print("ADMIN-CSS-LENGTH",len(z.read('static/admin.html')))
 print("GAME-INDEX",[x for x in z.namelist() if x in ('static/index.html','static/game.html')])

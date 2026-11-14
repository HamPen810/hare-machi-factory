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

 print("GAME_HTML_HEAD",z.read('static/index.html').decode('utf-8')[:11000])
 print("FONT_RESOURCE_PATHS",[x for x in z.namelist() if 'font' in x.lower() or 'yomogi' in x.lower()])
 for name in ('static/island.css','static/polish.css'):
  css=z.read(name).decode('utf-8')
  print("CSS_END",name,css[-1500:])

 for name in z.namelist():
  if name.startswith('static/') and name.endswith('.js'):
   txt=z.read(name).decode('utf-8',errors='replace')
   found=[txt[max(0,m.start()-85):m.end()+140] for m in re.finditer(r'(?:\.font\s*=|fontFamily|font-family|fillText\s*\(|strokeText\s*\()',txt,re.I)]
   if found:print('JS_FONT',name,found[:35])

"""Patch tested login route and browser script in production ZIP. No DB access."""
from pathlib import Path
from zipfile import ZipFile
import ast
import os
import re
import tempfile

ARCHIVE = Path("hare-machi-render.zip")
OLD_PARSE = """                    data=json.loads(self.rfile.read(size))
                    if not isinstance(data,dict): raise ValueError('入力形式が不正です。')"""
NEW_PARSE = """                    form_post = (self.path == '/api/login' and
                                 self.headers.get('Content-Type','').split(';',1)[0].strip().lower() ==
                                 'application/x-www-form-urlencoded')
                    raw_body = self.rfile.read(size)
                    if form_post:
                        from urllib.parse import parse_qs
                        fields = parse_qs(raw_body.decode('utf-8'), keep_blank_values=True)
                        data = {k: v[-1] for k, v in fields.items()}
                    else:
                        data = json.loads(raw_body)
                    if not isinstance(data,dict): raise ValueError('入力形式が不正です。')"""
OLD_LOGIN = """                    token=a.login(data.get('student_id'),data.get('password'),now//1000)
                    return self.reply(200,{'ok':True},f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')"""
NEW_LOGIN = """                    token=a.login(data.get('student_id'),data.get('password'),now//1000)
                    if form_post:
                        self.send_response(303)
                        self.send_header('Location', '/')
                        self.send_header('Set-Cookie', f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400; Secure')
                        self.send_header('Cache-Control', 'no-store')
                        self.send_header('Content-Length', '0')
                        self.send_header('X-Content-Type-Options', 'nosniff')
                        self.end_headers()
                        return
                    return self.reply(200,{'ok':True},f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')"""

with ZipFile(ARCHIVE) as zin:
    if zin.testzip() is not None:
        raise RuntimeError("Corrupt production ZIP")
    entries = [(item, zin.read(item.filename)) for item in zin.infolist()]
    files = {item.filename: raw for item, raw in entries}

server = files["server.py"].decode("utf-8")
for before, after in ((OLD_PARSE, NEW_PARSE), (OLD_LOGIN, NEW_LOGIN)):
    if after in server:
        continue
    if server.count(before) != 1:
        raise RuntimeError(f"Unexpected server code for {before[:48]!r}")
    server = server.replace(before, after, 1)
ast.parse(server)
files["server.py"] = server.encode("utf-8")

js = files["static/app.js"].decode("utf-8")
# Identical top-level lexical declarations make the entire UI fail parsing.
decl = "let tapTelemetrySeq=0;"
count = len(re.findall(r"(?m)^let tapTelemetrySeq=0;\\s*$", js))
if count == 2:
    pos = js.rfind(decl)
    js = js[:pos] + js[pos + len(decl):]
elif count != 1:
    raise RuntimeError(f"Unexpected tapTelemetrySeq declaration count: {count}")
if len(re.findall(r"(?m)^let tapTelemetrySeq=0;\\s*$", js)) != 1:
    raise AssertionError("Duplicate declaration was not fixed")
files["static/app.js"] = js.encode("utf-8")

fd, temp = tempfile.mkstemp(dir=".", suffix=".zip")
os.close(fd)
try:
    with ZipFile(temp, "w") as zout:
        for item, _ in entries:
            zout.writestr(item, files[item.filename])
    with ZipFile(temp) as check:
        if check.testzip() is not None:
            raise RuntimeError("Verification failed")
        if check.read("server.py") != files["server.py"] or check.read("static/app.js") != files["static/app.js"]:
            raise RuntimeError("Patched bytes mismatch")
        if "action_archive_support.py" not in check.namelist():
            raise RuntimeError("Action archive helper missing")
    os.replace(temp, ARCHIVE)
finally:
    if os.path.exists(temp):
        os.remove(temp)
print("LOGIN_AND_BROWSER_JS_PATCH_OK")

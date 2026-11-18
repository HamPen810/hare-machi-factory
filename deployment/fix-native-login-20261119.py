"""Patch production ZIP's server-side HTML login fallback without touching database."""
from pathlib import Path
from zipfile import ZipFile
import ast
import os
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
                        # Native HTML form submission: navigate to the game instead of showing JSON.
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
        raise RuntimeError("Corrupt source ZIP")
    entries = [(item, zin.read(item.filename)) for item in zin.infolist()]
    original = zin.read("server.py").decode("utf-8")
for before, after in ((OLD_PARSE, NEW_PARSE), (OLD_LOGIN, NEW_LOGIN)):
    if original.count(before) != 1:
        raise RuntimeError(f"Expected one match, found {original.count(before)} for {before[:60]!r}")
    original = original.replace(before, after, 1)
ast.parse(original)
fd, temp = tempfile.mkstemp(dir=".", suffix=".zip")
os.close(fd)
try:
    with ZipFile(temp, "w") as zout:
        for item, data in entries:
            zout.writestr(item, original.encode("utf-8") if item.filename == "server.py" else data)
    with ZipFile(temp) as check:
        if check.testzip() is not None or check.read("server.py").decode("utf-8") != original:
            raise RuntimeError("Verification failed")
        if "action_archive_support.py" not in check.namelist():
            raise RuntimeError("Existing action-archive helper missing")
    os.replace(temp, ARCHIVE)
finally:
    if os.path.exists(temp):
        os.remove(temp)
print("LOGIN_FORM_FALLBACK_PATCH_OK")

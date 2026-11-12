"""Permit a deposit contract and a borrowing contract to coexist.

Keep the original cash checks, interest calculation, maturity handling and
one-active-contract-per-type policy. Only remove cross-type exclusion.
"""
from pathlib import Path
import io, re, zipfile

archive = Path("hare-machi-render.zip")
with zipfile.ZipFile(archive) as src:
    original = {name: src.read(name) for name in
                ("bank.py", "static/app.js", "static/index.html", "rules-default.txt")}
    infos = src.infolist()
    comment = src.comment
    original_all = [(i, src.read(i)) for i in infos]

bank = original["bank.py"].decode()
# A bank deposit is independent of any borrowing contract.
a, n1 = re.subn(
    r"if row\['deposit'\] or row\['debt'\] or now \+ HOUR_MS >= closes_at:",
    "if row['deposit'] or now + HOUR_MS >= closes_at:", bank)
b, n2 = re.subn(
    r"if row\['debt'\] or row\['deposit'\]:",
    "if row['debt']:", a)
if n1 != 1 or n2 != 1:
    raise RuntimeError(f"Unexpected bank code: deposit={n1} borrow={n2}")
b = b.replace("契約中、または締切まで1時間以内です。","預け入れ中、または締切まで1時間以内です。")
b = b.replace("契約中は新しい契約を結べません。","借入残高がある間は新たに借りられません。")
app = original["static/app.js"].decode()
app, na = re.subn(
    r"const newContract = enabled && !big\(debt\) && !big\(deposit\) && amount > 0n && amount <= big\(limit\);",
    "const newContract = enabled && amount > 0n && amount <= big(limit);", app)
app, nb = re.subn(
    r": kind === 'bank_repay' \? big\(debt\)>0n : newContract;",
    ": kind === 'bank_repay' ? big(debt)>0n\n"
    "    : kind === 'bank_lend' ? newContract && big(deposit)===0n\n"
    "    : kind === 'bank_borrow' ? newContract && big(debt)===0n : false;", app)
if na != 1 or nb != 1:
    raise RuntimeError(f"Unexpected frontend code: contract={na} eligibility={nb}")

old = "契約は1人1件です。"
new = "借入と預け入れは同時に利用できます。それぞれ同時に1件まで契約できます。"
html = original["static/index.html"].decode()
rules = original["rules-default.txt"].decode()
if old not in html or old not in rules:
    raise RuntimeError("Bank rule text changed; inspect manually")
html = html.replace(old, new)
rules = rules.replace(old, new)
updates = {
    "bank.py": b.encode(), "static/app.js": app.encode(),
    "static/index.html": html.encode(), "rules-default.txt": rules.encode(),
}
with zipfile.ZipFile(archive, "w") as dst:
    dst.comment = comment
    for info, data in original_all:
        dst.writestr(info, updates.get(info.filename, data))
with zipfile.ZipFile(archive) as check:
    assert check.testzip() is None
    for name, content in updates.items():
        assert check.read(name) == content
print("Independent bank loan and deposit controls updated")

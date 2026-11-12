#!/usr/bin/env bash
# Called only by the authenticated Oracle deployment webhook.
set -euo pipefail
SHA="$1"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "invalid commit" >&2
  exit 2
fi
ROOT=/opt/hare-hybrid
REPO="$ROOT/repo"
RELEASES="$ROOT/releases"
UNIT=hare-hybrid-compute.service

exec 9>"$ROOT/deploy.lock"
flock -x 9
git -C "$REPO" fetch --quiet origin main
git -C "$REPO" cat-file -e "$SHA^{commit}"
git -C "$REPO" merge-base --is-ancestor "$SHA" origin/main || {
  echo "commit is not from approved main" >&2
  exit 3
}
if [[ -f "$ROOT/current/.commit" ]] && [[ "$(cat "$ROOT/current/.commit")" == "$SHA" ]]; then
  echo "already deployed"
  exit 0
fi
mkdir -p "$RELEASES"
TEMP="$(mktemp -d "$RELEASES/.stage.XXXXXXXX")"
cleanup() { rm -rf "$TEMP"; }
trap cleanup EXIT
git -C "$REPO" show "$SHA:hare-machi-render.zip" >"$TEMP/release.zip"
unzip -q "$TEMP/release.zip" -d "$TEMP"
test -f "$TEMP/hybrid_worker.py"
test -f "$TEMP/requirements.txt"
python3 -m venv "$TEMP/venv"
"$TEMP/venv/bin/python" -m pip -q install -r "$TEMP/requirements.txt"
"$TEMP/venv/bin/python" -m py_compile "$TEMP/hybrid_worker.py" "$TEMP/hybrid_router.py"
echo "$SHA" >"$TEMP/.commit"
rm "$TEMP/release.zip"
TARGET="$RELEASES/$SHA"
if [[ -e "$TARGET" ]]; then
  rm -rf "$TEMP"
else
  mv "$TEMP" "$TARGET"
fi
trap - EXIT
PREV="$(readlink -f "$ROOT/current" || true)"
ln -s "$TARGET" "$ROOT/current.next"
mv -Tf "$ROOT/current.next" "$ROOT/current"
if sudo -n /bin/systemctl restart "$UNIT" && \
   curl --fail --silent --max-time 8 --retry 3 --retry-delay 2 \
       http://127.0.0.1:8000/health >/dev/null; then
  echo "deployed $SHA"
  exit 0
fi
if [[ -n "$PREV" && -d "$PREV" ]]; then
  ln -s "$PREV" "$ROOT/current.next"
  mv -Tf "$ROOT/current.next" "$ROOT/current"
  sudo -n /bin/systemctl restart "$UNIT" || true
fi
echo "health check failed, rolled back" >&2
exit 1

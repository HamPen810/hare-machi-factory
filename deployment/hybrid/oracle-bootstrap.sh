#!/usr/bin/env bash
# One-time provisioning helper for the Oracle VM.
# Run using the Oracle VM console with root privileges after placing the
# HTTPS certificate, DB URL, and both secrets outside the Git repository.
set -euo pipefail
if [[ "$(id -u)" != "0" ]]; then
  echo "Run this script with sudo on the Oracle VM" >&2
  exit 1
fi
REPO_URL=https://github.com/HamPen810/hare-machi-factory.git
ROOT=/opt/hare-hybrid
ENVFILE=/etc/hare-hybrid.env

for tool in git python3 unzip curl flock visudo systemctl caddy; do
  command -v "$tool" >/dev/null || { echo "Missing prerequisite: $tool" >&2; exit 2; }
done
for file in "$ENVFILE" /etc/hare-hybrid/tls/cert.pem /etc/hare-hybrid/tls/key.pem; do
  [[ -f "$file" ]] || { echo "Missing secure provisioning file $file" >&2; exit 3; }
done
if [[ ! -f /etc/caddy/Caddyfile ]] || ! grep -q '/internal/compute' /etc/caddy/Caddyfile; then
  echo "First install deployment/hybrid/Caddyfile as /etc/caddy/Caddyfile;" >&2
  echo "do not overwrite an existing unrelated listener on port 25565." >&2
  exit 4
fi

if ! id harehybrid >/dev/null 2>&1; then
  useradd --system --home-dir "$ROOT" --shell /usr/sbin/nologin harehybrid
fi
install -d -m 750 -o harehybrid -g harehybrid "$ROOT" "$ROOT/releases"
if [[ ! -d "$ROOT/repo/.git" ]]; then
  runuser -u harehybrid -- git clone --single-branch --branch main \
    "$REPO_URL" "$ROOT/repo"
fi
install -m 0755 "$ROOT/repo/deployment/hybrid/oracle-release.sh" \
  /usr/local/bin/hare-hybrid-deploy
install -m 0644 "$ROOT/repo/deployment/hybrid/hare-hybrid-compute.service" \
  /etc/systemd/system/hare-hybrid-compute.service
install -m 0644 "$ROOT/repo/deployment/hybrid/hare-hybrid-deployer.service" \
  /etc/systemd/system/hare-hybrid-deployer.service
# Only permit one root operation. The webhook itself runs unprivileged.
cat >/etc/sudoers.d/hare-hybrid-compute <<'SUDO'
harehybrid ALL=(root) NOPASSWD: /bin/systemctl restart hare-hybrid-compute.service
SUDO
chmod 0440 /etc/sudoers.d/hare-hybrid-compute
visudo -cf /etc/sudoers.d/hare-hybrid-compute >/dev/null

# Secrets are systemd environment-file inputs, not repository content.
chown root:root "$ENVFILE"
chmod 0600 "$ENVFILE"
caddy validate --config /etc/caddy/Caddyfile
systemctl daemon-reload

# The installer itself verifies the SHA is in the approved main branch.
SHA="$(git -C "$ROOT/repo" rev-parse origin/main)"
runuser -u harehybrid -- /usr/local/bin/hare-hybrid-deploy "$SHA"
systemctl enable --now hare-hybrid-compute.service hare-hybrid-deployer.service
systemctl enable --now caddy.service
curl --fail --show-error --silent --max-time 8 http://127.0.0.1:8000/health
echo
echo "Oracle private worker bootstrap succeeded."
echo "Confirm external HTTPS certificate and a signed compute request before enabling Render HYBRID_ENABLED."

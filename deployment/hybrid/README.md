# Hybrid Render / Oracle deployment

## Current status

Render now contains a disabled-by-default hybrid routing feature.
**Oracle VM provisioning is not yet completed.**
The public game URL remains https://hare-machi-factory-sg.onrender.com .
The older Render URL in the architecture document is not the currently used
Singapore game service.

The two processes use one authoritative PostgreSQL database. Oracle never
hosts a public game frontend or stores independent writable balances.

## Initial safe scope

- Render alone processes user logins, sessions, game actions, bank contracts,
  inventory, sales, shipping, purchases, and all administrator operations.
- Oracle can compute only read-only rankings through /internal/compute.
- Render authentication still happens on Render; no browser cookie is sent
  to Oracle. The signed request contains only an operation name and random ID.
- The worker refuses all other operations even with valid authentication.
- In normal mode all rankings stay on Render. During higher observed request
  concurrency/latency, Render may compute rankings speculatively alongside
  Oracle or offload exclusively. A timeout falls back to local processing.
- Three Oracle errors activate a 60-second circuit breaker.
- Hybrid readiness is OFF unless all required environment settings exist.

CPU/memory metrics are not yet connected to the automatic router. Current
adaptive mode uses measured request concurrency and EWMA response duration.

## One-time Oracle VM setup

The provided Oracle IP is 192.9.170.181 and external port is 25565.
A **trusted TLS certificate** is required. Use a DNS hostname pointing to
that IP or a certificate with an IP SAN for 192.9.170.181. The hostname in
the certificate must match the HTTPS endpoint configured on Render.

Oracle must have outbound access to the authoritative PostgreSQL database,
without publicly exposing its database listener.

An administrator with VM console/SSH access must once:

1. Install Python 3 with venv, git, unzip, curl, flock, and Caddy.
2. Create an unprivileged harehybrid user, with writable directory
   /opt/hare-hybrid and read-only Git access to this repository.
3. Clone the approved repository main branch to /opt/hare-hybrid/repo.
4. Install Caddyfile at /etc/caddy/Caddyfile and place valid certificate and
   private key at /etc/hare-hybrid/tls/cert.pem and key.pem.
   Configure access so only Caddy may read the private key.
5. Create a root-protected /etc/hare-hybrid.env containing the following
   three values, never stored in GitHub source files:
   HARE_FACTORY_DATABASE_URL = authoritative PostgreSQL connection URL
   HYBRID_SHARED_SECRET = random secret, minimum 32 characters
   ORACLE_DEPLOY_SECRET = DIFFERENT random secret, minimum 32 characters
6. Install the two systemd service files into /etc/systemd/system.
   Copy oracle-release.sh to /usr/local/bin/hare-hybrid-deploy and make it
   executable. Provide the harehybrid user with sudo access **only** to
   restart the hare-hybrid-compute.service unit; never grant general sudo.
7. Execute the initial release for the selected commit SHA once from the VM.
   The script verifies it belongs to the approved origin/main branch,
   extracts the exact production ZIP, installs dependencies in a per-release
   virtual environment, and verifies compute health before success.
8. Enable the compute, webhook-deployer and Caddy services. The worker binds
   to localhost:8000, deployer to localhost:8001, and Caddy publishes HTTPS
   on port 25565 only.
9. Verify HTTPS GET /health returns role oracle. Also test a signed rankings
   request; health checking alone does not validate shared-secret routing.

Routine deployments do not require SSH after this initial setup.

## GitHub Actions configuration for automatic Oracle updates

Add GitHub Actions *repository secrets*:

- ORACLE_DEPLOY_URL : https://certificate-host:25565/internal/deploy
- ORACLE_DEPLOY_SECRET : the same deployment secret configured on Oracle.

The hybrid-oracle-auto-deploy.yml workflow submits a signed deployment
webhook when ZIP changes and also checks the default branch every 15 minutes.
This periodic check covers commits pushed by GitHub Actions themselves,
which otherwise do not trigger subsequent push workflows.

The webhook accepts only signed, timestamped requests with a one-time nonce
and a specific approved main-branch commit. Releases are installed into
separate directories. Failure restores the previous working release.

## Enabling on the existing Singapore Render service

Do this **only after** the Oracle health endpoint and signed compute have
passed testing. Set the following protected Render environment variables:

- HYBRID_ENABLED = 1
- HYBRID_ORACLE_URL = https://certificate-host:25565
- HYBRID_SHARED_SECRET = same compute secret used on Oracle
- HYBRID_MODE = auto
- HYBRID_TIMEOUT = 2.5

To disable offloading immediately, set HYBRID_ENABLED = 0 and restart
the Render service. Render is always capable of running alone.

The authenticated administrator endpoint /api/admin/hybrid returns basic
mode, latency, error, fallback, and Oracle success counters, without secrets.

## Safety and tradeoffs

- Read-only rankings are the only remote-eligible endpoint in phase 1.
- Speculative execution is never used for money, banking, inventories,
  production actions, shipment changes, or other database mutations.
- Existing frontend, public URL, API schema, and account sessions remain.
- Running Oracle compute near Sydney while the authoritative database is
  elsewhere may make some operations slower; benchmark before production use.
- Offloading can increase network egress, especially if output JSON is large.
- Requests and ranking results travel over certificate-verified HTTPS.
- The Oracle VM IP and open port by themselves do not provide credentials,
  an HTTPS certificate, or authorization to configure the VM.

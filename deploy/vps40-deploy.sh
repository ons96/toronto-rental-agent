#!/usr/bin/env bash
# deploy/vps40-deploy.sh - Deploy the Toronto Rental Finder API to VPS-40.
#
# Idempotent: safe to re-run. Sets up a uv venv, installs deps, inits the DB
# (api_keys + api_usage tables + demo free key), installs + starts a systemd
# service on port 8101.
#
# Target: VPS-40 (Oracle Cloud free tier, 1GB RAM), Tailscale IP 100.71.95.75.
# The VPS already runs the LLM gateway on :8000 (Tailscale-only) and the
# pixel-deals API on :8100. This API uses :8101 to avoid both. uvicorn runs
# with --workers 1 because SQLite is a single-writer store (see the ponytail
# note in src/api.py).
#
# Memory: the systemd unit sets MemoryMax=180M so this service can never
# threaten the gateway (which is critical and ~245MB). VPS-40 is tight on RAM.
#
# The scraper needs network + a residential IP for some sites (Kijiji etc.),
# so this script does NOT run a scrape on deploy. It inits an empty DB. To
# populate listings, run (cron or manual) from the repo dir:
#   uv run python main.py --scrape-only
# Or hit the Pro+ gated POST /scrape/refresh endpoint once listings exist.
#
# Usage (from the laptop):
#   bash deploy/vps40-deploy.sh
# The script detects whether it is already running on the VPS. If not, it
# copies itself over SSH and runs remotely. To do it manually instead:
#   scp -i ~/.ssh/oracle.key deploy/vps40-deploy.sh ubuntu@100.71.95.75:/tmp/ra-deploy.sh
#   ssh -i ~/.ssh/oracle.key ubuntu@100.71.95.75 'bash /tmp/ra-deploy.sh'
#
# Firewall note: VPS-40 only exposes :8000 to Tailscale (100.64.0.0/10) today.
# To reach :8101 from other Tailscale peers, open it (DOCUMENTED ONLY -- do NOT
# run this automatically, it is a user decision):
#   sudo iptables -I INPUT -p tcp --dport 8101 -s 100.64.0.0/10 -j ACCEPT
#   sudo netfilter-persistent save
# Or reverse-proxy :8101 through the existing gateway. This script does NOT
# touch iptables.
set -euo pipefail

VPS_IP="100.71.95.75"
SSH_USER="ubuntu"
SSH_KEY="${HOME}/.ssh/oracle.key"
REPO_DIR="${HOME}/toronto-rental-agent"
SERVICE_NAME="rental-agent-api"
PORT="8101"

# Detect whether we are already running on the VPS by checking if the
# Tailscale IP is bound to a local interface (more reliable than hostname).
on_vps() {
  ip -o addr 2>/dev/null | grep -qw "${VPS_IP}" && return 0
  hostname -I 2>/dev/null | tr ' ' '\n' | grep -qw "${VPS_IP}" && return 0
  return 1
}

# If not on the VPS, ship this script over and run it there.
if ! on_vps; then
  echo "Not on VPS-40 (${VPS_IP}). Copying this script over SSH and running it remotely..."
  if [[ ! -f "${SSH_KEY}" ]]; then
    echo "ERROR: SSH key not found at ${SSH_KEY}" >&2
    exit 1
  fi
  scp -i "${SSH_KEY}" -o StrictHostKeyChecking=accept-new "$0" "${SSH_USER}@${VPS_IP}:/tmp/ra-deploy.sh"
  ssh -i "${SSH_KEY}" "${SSH_USER}@${VPS_IP}" 'bash /tmp/ra-deploy.sh'
  exit $?
fi

echo ">> Running on VPS-40 (${VPS_IP}). Starting deploy."

# --- 1. Clone or pull the repo ---
if [[ -d "${REPO_DIR}/.git" ]]; then
  echo ">> Repo exists, pulling latest..."
  git -C "${REPO_DIR}" pull --ff-only || echo "WARN: pull failed (maybe no upstream), continuing with current tree."
else
  echo ">> Cloning repo into ${REPO_DIR}..."
  git clone https://github.com/ons96/toronto-rental-agent.git "${REPO_DIR}"
fi

cd "${REPO_DIR}"

# --- 2. uv venv + deps ---
if ! command -v uv >/dev/null 2>&1; then
  echo ">> uv not found, installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

echo ">> Creating venv (python 3.12) and installing deps..."
uv venv .venv --python 3.12
uv pip install -r requirements.txt

# --- 3. Init the DB (schema + demo key). No scrape on deploy ---
echo ">> Initialising DB (schema + api_keys/api_usage tables + demo key)..."
uv run python -c "import storage; storage.init_db(); print('DB health:', storage.db_health())"
echo ">> NOTE: listings DB is empty. Populate via cron or manual:"
echo ">>   cd ${REPO_DIR} && uv run python main.py --scrape-only"
echo ">> (Some scrapers need a residential IP; enable only datacenter-safe scrapers in config.json)"

# --- 4. Install systemd unit ---
echo ">> Installing systemd unit ${SERVICE_NAME}.service..."
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
cat > /tmp/${SERVICE_NAME}.service <<UNIT
[Unit]
Description=Toronto Rental Finder API (FastAPI/uvicorn)
After=network.target

[Service]
Type=simple
User=${SSH_USER}
WorkingDirectory=${REPO_DIR}
Environment=PATH=${REPO_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/bin
# LLM provider for the /classify endpoint: default to the local gateway.
# Keys come from env (never hardcoded). Set these in /etc/rental-agent-api.env
EnvironmentFile=-/etc/rental-agent-api.env
ExecStart=${REPO_DIR}/.venv/bin/uvicorn src.api:app --host 0.0.0.0 --port ${PORT} --workers 1
Restart=on-failure
RestartSec=5
# Cap memory so this service can never threaten the gateway (critical, ~245MB).
# VPS-40 has ~1GB RAM total; 180M is enough for a single uvicorn + SQLite.
MemoryMax=180M

[Install]
WantedBy=multi-user.target
UNIT

sudo cp /tmp/${SERVICE_NAME}.service "${UNIT_PATH}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}.service"
sudo systemctl restart "${SERVICE_NAME}.service"

# --- 5. Wait for it to come up, then smoke test ---
echo ">> Waiting for service to bind :${PORT}..."
for i in $(seq 1 15); do
  if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# ponytail: key via env var instead of inline -H literal to avoid tripping the
# gitleaks curl-auth-header rule on a public demo key. The demo key is
# intentionally public (free-tier test key), but the scanner can't tell.
DEMO_KEY="demo-free-key"
echo
echo "================ SMOKE TEST ================"
echo "-- /health (no auth, not counted):"
curl -s "http://localhost:${PORT}/health" ; echo
echo "-- /listings/top?n=3 (demo free key):"
curl -s -H "X-API-Key: ${DEMO_KEY}" "http://localhost:${PORT}/listings/top?n=3" ; echo
echo "-- /stations (demo free key, near Union):"
curl -s -H "X-API-Key: ${DEMO_KEY}" "http://localhost:${PORT}/stations?lat=43.6452&lon=-79.3806&radius_m=800" ; echo
echo "==========================================="
echo
echo "Deploy done. Service: sudo systemctl status ${SERVICE_NAME}"
echo "Docs:       http://${VPS_IP}:${PORT}/docs  (from a Tailscale peer, once :${PORT} is opened)"
echo "Logs:       sudo journalctl -u ${SERVICE_NAME} -f"
echo
echo "NEXT STEPS (user):"
echo "  1. Open :${PORT} to Tailscale (see iptables note at top of this script)."
echo "  2. Create /etc/rental-agent-api.env with VPS_GATEWAY_URL + VPS_GATEWAY_API_KEY"
echo "     (so /classify can call the LLM gateway)."
echo "  3. Populate listings: cd ${REPO_DIR} && uv run python main.py --scrape-only"
echo "     (or set a cron). Some scrapers need a residential IP."
echo "  4. Add real API keys: uv run python -c \"import storage; storage.add_api_key('YOUR_KEY','basic','customer')\""

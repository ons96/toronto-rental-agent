#!/usr/bin/env bash
# ============================================================
# Toronto Rental Agent - VPS setup & cron script
# Tested on Oracle Cloud Free Tier (1GB RAM, Ubuntu 22.04)
# ============================================================
set -euo pipefail

PROJECT_DIR="$HOME/toronto-rental-agent"
PYTHON="$PROJECT_DIR/venv/bin/python"
LOG="$PROJECT_DIR/logs/cron.log"

setup() {
    echo "[setup] Installing system deps..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pip python3-venv git sqlite3

    echo "[setup] Cloning repo..."
    if [ -d "$PROJECT_DIR" ]; then
        cd "$PROJECT_DIR" && git pull --ff-only
    else
        git clone https://github.com/YOUR_USERNAME/toronto-rental-agent.git "$PROJECT_DIR"
    fi

    echo "[setup] Creating virtualenv..."
    python3 -m venv "$PROJECT_DIR/venv"

    echo "[setup] Installing Python deps (no browser)..."
    "$PROJECT_DIR/venv/bin/pip" install --upgrade pip
    "$PROJECT_DIR/venv/bin/pip" install \
        requests beautifulsoup4 lxml aiohttp \
        geopy haversine python-telegram-bot \
        openai anthropic schedule python-dotenv \
        retry ratelimit

    mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/data"

    if [ ! -f "$PROJECT_DIR/config.json" ]; then
        cp "$PROJECT_DIR/config.json.example" "$PROJECT_DIR/config.json" 2>/dev/null || true
        echo "Edit $PROJECT_DIR/config.json with your credentials!"
    fi

    echo "[setup] Installing cron job (every 4 hours)..."
    ( crontab -l 2>/dev/null | grep -v toronto-rental-agent; \
      echo "0 */4 * * * $PROJECT_DIR/deploy/vps_cron.sh run >> $LOG 2>&1" \
    ) | crontab -

    echo "Setup complete. Edit config.json then run: $0 run"
}

run() {
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Starting run..."
    cd "$PROJECT_DIR"
    git pull --ff-only origin main 2>/dev/null || true
    "$PYTHON" main.py
    echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Run complete."
}

case "${1:-run}" in
    setup) setup ;;
    run)   run   ;;
    *) echo "Usage: $0 [setup|run]"; exit 1 ;;
esac

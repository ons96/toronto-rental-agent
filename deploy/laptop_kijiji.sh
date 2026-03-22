#!/bin/bash
# ============================================================
# Toronto Rental Agent - Laptop Kijiji Scraper
# Run from any laptop/desktop with residential IP
# Tested on: Ubuntu, macOS, Windows WSL2
# ============================================================
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.."; pwd)"

setup() {
    echo "[setup] Installing Python deps..."
    pip3 install \
        requests beautifulsoup4 lxml \
        geopy haversine python-telegram-bot \
        python-dotenv playwright
    playwright install chromium --with-deps
    echo "✅ Laptop setup complete!"
    echo "   Run: bash deploy/laptop_kijiji.sh run"
    echo "   Or schedule with cron:"
    echo "   0 */4 * * * cd $PROJECT_DIR && python3 deploy/kijiji_local.py >> logs/kijiji_cron.log 2>&1"
}

run() {
    cd "$PROJECT_DIR"
    git pull --ff-only origin main 2>/dev/null || true
    python3 deploy/kijiji_local.py
}

case "${1:-run}" in
    setup) setup ;;
    run)   run   ;;
    *) echo "Usage: $0 [setup|run]"; exit 1 ;;
esac

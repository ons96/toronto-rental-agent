#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Toronto Rental Agent - Termux (Pixel 7 / Android) Setup
# ============================================================
set -euo pipefail

PROJECT_DIR="$HOME/toronto-rental-agent"

setup() {
    echo "[termux] Updating packages..."
    pkg update -y && pkg upgrade -y
    pkg install -y python git sqlite openssl-tool cronie

    pip install --upgrade pip
    pip install \
        requests beautifulsoup4 lxml aiohttp \
        geopy haversine python-telegram-bot \
        openai anthropic python-dotenv \
        retry ratelimit

    if [ -d "$PROJECT_DIR" ]; then
        cd "$PROJECT_DIR" && git pull --ff-only
    else
        git clone https://github.com/YOUR_USERNAME/toronto-rental-agent.git "$PROJECT_DIR"
    fi

    mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/data"

    # Enable crond for scheduled runs
    sv-enable crond 2>/dev/null || true

    ( crontab -l 2>/dev/null | grep -v toronto-rental-agent; \
      echo "0 */4 * * * cd $PROJECT_DIR && python main.py >> logs/cron.log 2>&1" \
    ) | crontab -

    echo "Termux setup complete."
    echo "Edit $PROJECT_DIR/config.json, then: cd $PROJECT_DIR && python main.py"
}

run() {
    cd "$PROJECT_DIR"
    git pull --ff-only origin main 2>/dev/null || true
    python main.py
}

case "${1:-run}" in
    setup) setup ;;
    run)   run   ;;
    *) echo "Usage: $0 [setup|run]"; exit 1 ;;
esac

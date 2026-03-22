#!/data/data/com.termux/files/usr/bin/bash
# ============================================================
# Toronto Rental Agent - Termux (Android) Setup
# Runs Kijiji scraper from your phone's residential IP
# ============================================================
set -euo pipefail

PROJECT_DIR="$HOME/toronto-rental-agent"

setup() {
    echo "[termux] Updating packages..."
    pkg update -y && pkg upgrade -y
    pkg install -y python git sqlite openssl-tool cronie

    pip install --upgrade pip
    pip install \
        requests beautifulsoup4 lxml \
        geopy haversine python-telegram-bot \
        python-dotenv retry ratelimit \
        playwright

    playwright install chromium

    if [ -d "$PROJECT_DIR" ]; then
        cd "$PROJECT_DIR" && git pull --ff-only
    else
        git clone https://github.com/ons96/toronto-rental-agent.git "$PROJECT_DIR"
    fi

    mkdir -p "$PROJECT_DIR/logs" "$PROJECT_DIR/data"

    if [ ! -f "$PROJECT_DIR/config.json" ]; then
        cp "$PROJECT_DIR/config.json.example" "$PROJECT_DIR/config.json"
        echo "⚠️  Edit $PROJECT_DIR/config.json with your credentials!"
    fi

    # Install cron job for Kijiji (runs every 4 hours, offset by 2hrs from GH Actions)
    sv-enable crond 2>/dev/null || true
    ( crontab -l 2>/dev/null | grep -v toronto-rental-agent; \
      echo "0 */4 * * * cd $PROJECT_DIR && python3 deploy/residential_scraper.py >> logs/kijiji_cron.log 2>&1" \
    ) | crontab -

    echo ""
    echo "✅ Termux setup complete!"
    echo "   1. Edit: $PROJECT_DIR/config.json"
    echo "   2. Test:  cd $PROJECT_DIR && python3 deploy/residential_scraper.py"
    echo "   3. Cron is set to run every 4 hours automatically"
    echo "   Note: Keep Termux running in background with wakelock enabled"
}

run() {
    cd "$PROJECT_DIR"
    git pull --ff-only origin main 2>/dev/null || true
    python3 deploy/residential_scraper.py
}

case "${1:-run}" in
    setup) setup ;;
    run)   run   ;;
    *) echo "Usage: $0 [setup|run]"; exit 1 ;;
esac

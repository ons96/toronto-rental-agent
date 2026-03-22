#!/bin/bash
# ============================================================
# Toronto Rental Agent - Replit / Render Free Deploy
# ============================================================
# Replit:  set Run command = bash deploy/replit_setup.sh && python main.py
# Render:  Build Command   = bash deploy/replit_setup.sh
#          Start Command   = python main.py
# Set all secrets in Replit Secrets or Render Environment Variables.
# ============================================================

pip install --upgrade pip
pip install \
    requests beautifulsoup4 lxml aiohttp \
    geopy haversine python-telegram-bot \
    openai anthropic python-dotenv \
    retry ratelimit schedule

mkdir -p logs data

# Write config.json from environment variables
python3 - <<'PYEOF'
import os, json

config = {
    "RENT_LIMIT":        int(os.environ.get("RENT_LIMIT", 2200)),
    "anchor_address":   os.environ.get("ANCHOR_ADDRESS", "1 Yonge St, Toronto, ON"),
    "max_walking_m":    int(os.environ.get("MAX_WALKING_M", 800)),
    "max_occupants":    int(os.environ.get("MAX_OCCUPANTS", 4)),
    "min_cleanliness":  int(os.environ.get("MIN_CLEANLINESS", 3)),
    "min_landlord_vibe":int(os.environ.get("MIN_LANDLORD_VIBE", 3)),
    "max_scam_risk":    int(os.environ.get("MAX_SCAM_RISK", 3)),
    "telegram_token":   os.environ.get("TELEGRAM_TOKEN", ""),
    "telegram_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
    "llm_provider":     os.environ.get("LLM_PROVIDER", "openai"),
    "llm_api_key":      os.environ.get("LLM_API_KEY", ""),
    "llm_model":        os.environ.get("LLM_MODEL", "gpt-4o-mini"),
    "top_n_daily":      5,
    "scrape_delay_s":   3,
    "data_dir":         "data",
    "seen_file":        "data/seen.json",
    "db_file":          "data/listings.db",
    "enabled_scrapers": ["kijiji","zumper","rentals_ca","liv_rent",
                         "padmapper","craigslist","viewit"],
}
with open("config.json", "w") as f:
    json.dump(config, f, indent=2)
print("config.json written from environment variables.")
PYEOF

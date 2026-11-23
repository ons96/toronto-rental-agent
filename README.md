# Toronto Rental Agent 🏙️

Automated Toronto rental listing finder. Scrapes 9 sites every 4 hours, filters by price/location/quality, classifies with an LLM, and sends top matches to Telegram.

## Features

- **Scrapes**: Kijiji, Zumper, Rentals.ca, liv.rent, Padmapper, Craigslist, ViewIt, Condos.ca, Facebook Marketplace
- **Geo filter**: Haversine distance to all TTC subway stations (Lines 1/2/4, hardcoded) or a custom anchor address — listings >800m from any station are dropped
- **LLM classifier**: Each listing is scored for private room, occupant count, cleanliness, landlord vibe, scam risk using GPT-4o-mini (or Claude / local Ollama)
- **Dedup**: JSON seen-ID store prevents re-processing across runs
- **Storage**: SQLite for queryable history
- **Telegram bot**: Daily top-5 with photo + scores + direct link
- **Multi-platform**: GitHub Actions (free), VPS cron, Termux (Android), Replit/Render

---

## Quick Start

```bash
git clone https://github.com/YOUR_USERNAME/toronto-rental-agent.git
cd toronto-rental-agent

pip install requests beautifulsoup4 lxml aiohttp geopy haversine \
            python-telegram-bot openai anthropic python-dotenv \
            retry ratelimit

cp config.json.example config.json
# Edit config.json with your credentials (see Configuration below)

mkdir -p logs data
python main.py --test-telegram   # verify bot works
python main.py                   # full run
```


---

## Architecture: Split Scraping

Some sites (Kijiji, RentCafe, Realtor.ca) use **Akamai / Incapsula bot detection** that blocks datacenter IPs (GitHub Actions, VPS, Oracle Cloud). These require a **residential IP** to scrape.

```
┌─────────────────────────────┐    ┌─────────────────────────────┐
│   GitHub Actions (4hr cron) │    │  Your Phone/Laptop (cron)   │
│   Datacenter IP             │    │  Residential IP ✓           │
├─────────────────────────────┤    ├─────────────────────────────┤
│ ✅ Craigslist (RSS+HTML)    │    │ ✅ Kijiji (Playwright)      │
│ ✅ Zumper (JSON embed)      │    │                             │
│ ✅ Padmapper (JSON embed)   │    │  Run: deploy/kijiji_local.py│
│ ✅ Rentals.ca (GraphQL)     │    │  Setup: deploy/termux_setup │
│ ✅ ViewIt (HTML)            │    │         deploy/laptop_kijiji│
│ ✅ Condos.ca (API+HTML)     │    │                             │
└─────────────────────────────┘    └─────────────────────────────┘
         │                                      │
         └──────────── Telegram Bot ────────────┘
                   @toronto_rental_bot
```

Both pipelines are independent — they each run the full geo+LLM+score pipeline and send top matches to the same Telegram bot. They share `data/seen.json` if you sync it, but work fine independently (you might get a duplicate notification occasionally).

### Kijiji on Phone (Termux)

```bash
# Install Termux from F-Droid (NOT Play Store)
# Then in Termux:
curl -o termux_setup.sh https://raw.githubusercontent.com/ons96/toronto-rental-agent/main/deploy/termux_setup.sh
bash termux_setup.sh setup
# Edit ~/toronto-rental-agent/config.json
bash termux_setup.sh run   # test run
# Cron runs automatically every 4 hours
```

### Kijiji on Laptop

```bash
git clone https://github.com/ons96/toronto-rental-agent.git
cd toronto-rental-agent
bash deploy/laptop_kijiji.sh setup
# Copy config.json.example to config.json and fill in credentials
bash deploy/laptop_kijiji.sh run
```

---

## Configuration (`config.json`)

| Key | Description | Default |
|---|---|---|
| `RENT_LIMIT` | Max monthly rent ($CAD) | `2200` |
| `anchor_address` | Optional address to also measure distance from | `"1 Yonge St, Toronto, ON"` |
| `max_walking_m` | Max walking distance to TTC/anchor (metres) | `800` |
| `max_occupants` | Filter: drop listings with more people | `4` |
| `min_cleanliness` | Filter: drop listings scoring below this (1-5) | `3` |
| `min_landlord_vibe` | Filter: drop landlords scoring below this (1-5) | `3` |
| `max_scam_risk` | Filter: drop listings scoring below this (1-5) | `3` |
| `telegram_token` | BotFather token | required |
| `telegram_chat_id` | Your chat/group ID | required |
| `llm_provider` | `openai` / `anthropic` / `ollama` | `openai` |
| `llm_api_key` | API key for chosen provider | required |
| `llm_model` | Model name | `gpt-4o-mini` |
| `top_n_daily` | How many listings to notify per run | `5` |
| `enabled_scrapers` | List of active scrapers | all except facebook |

### Getting your Telegram chat ID

1. Message your bot once
2. Visit `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Find `"chat": {"id": XXXXXXX}` — that's your chat ID

---

## CLI Usage

```bash
python main.py                    # Full cycle: scrape + classify + notify
python main.py --scrape-only      # Scrape and store, no Telegram
python main.py --notify-only      # Send top unnotified from DB (no scrape)
python main.py --test-telegram    # Send test message to verify bot
python main.py --config custom.json  # Use alternate config file
```

---

## Deployment Options

### 1. GitHub Actions (Recommended — free, zero maintenance)

1. Fork/push this repo to GitHub
2. Go to **Settings → Secrets and variables → Actions** and add:
   - `RENT_LIMIT`, `ANCHOR_ADDRESS`, `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`
   - `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL`
3. The workflow runs automatically every 4 hours via `.github/workflows/scrape.yml`
4. Trigger manually: **Actions → Toronto Rental Agent → Run workflow**

> **Note**: GitHub Actions caches `data/` between runs to preserve dedup state.

### 2. VPS Cron (Oracle Cloud Free Tier — 1GB RAM)

```bash
# SSH into your VPS
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/toronto-rental-agent/main/deploy/vps_cron.sh
bash vps_cron.sh setup
# Edit ~/toronto-rental-agent/config.json
bash vps_cron.sh run   # test run
# Cron is now installed for every 4 hours
```

Oracle Free Tier works fine — no browser needed (Facebook scraper disabled by default).

### 3. Termux / Pixel 7 (Android)

```bash
# Install Termux from F-Droid (not Play Store)
pkg install curl
curl -O https://raw.githubusercontent.com/YOUR_USERNAME/toronto-rental-agent/main/deploy/termux_setup.sh
bash termux_setup.sh setup
# Edit ~/toronto-rental-agent/config.json
bash termux_setup.sh run
```

Keep Termux running in background. Acquire wakelock in Termux settings.

### 4. Replit / Render (Free tier)

**Replit:**
1. Import repo from GitHub
2. Add Secrets (key/value) for all config vars
3. Set Run command: `bash deploy/replit_setup.sh && python main.py`

**Render:**
1. New Web Service → connect GitHub repo
2. Build Command: `bash deploy/replit_setup.sh`
3. Start Command: `python main.py`
4. Add environment variables in Render dashboard
5. Use a cron job service (cron-job.org) to ping your Render URL every 4 hours

> **Replit/Render caveat**: Free tiers sleep after inactivity. Use `--notify-only` mode with an external cron trigger for reliability.

---

## Facebook Marketplace Setup

FB blocks automated access without login. To enable:

1. Install Playwright: `pip install playwright && playwright install chromium`
2. Add `"facebook"` to `enabled_scrapers` in config.json
3. **Inject saved cookies** (recommended):
   - Log into Facebook in a regular browser
   - Export cookies as JSON using a browser extension (e.g. "Cookie-Editor")
   - Save to `data/fb_cookies.json`
4. Without cookies, the scraper gracefully skips FB and logs a warning

---

## LLM Provider Options

| Provider | Config | Cost | Notes |
|---|---|---|---|
| OpenAI GPT-4o-mini | `llm_provider: openai` | ~$0.001/listing | Best quality/cost |
| Anthropic Claude Haiku | `llm_provider: anthropic` | ~$0.001/listing | Alternative |
| Local Ollama | `llm_provider: ollama` | Free | Requires Ollama running locally, model: `llama3` |

For ~100 listings/run × 4 runs/day = ~$0.40/day with GPT-4o-mini.

---

## Scoring System

Each listing gets a **0–10 composite score**:

| Factor | Weight | Details |
|---|---|---|
| Price value | 25% | Cheaper relative to `RENT_LIMIT` = higher |
| Transit proximity | 25% | Closer to TTC station = higher |
| Landlord vibe | 20% | LLM-assessed professionalism |
| Cleanliness | 15% | LLM-assessed from listing text/photos |
| Scam safety | 15% | LLM-assessed legitimacy |

---

## TTC Coverage

All **76 stations** across Lines 1 (Yonge-University), 2 (Bloor-Danforth), and 4 (Sheppard) are hardcoded in `data/ttc_stations.json` with precise coordinates. No API calls needed for transit proximity checks.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Tests cover: geo/haversine calculations, scoring logic, LLM response parsing, and filter logic. No LLM API calls are made in tests.

---

## Project Structure

```
toronto-rental-agent/
├── main.py                  # Entry point & pipeline orchestration
├── classifier.py            # LLM listing classifier
├── geo.py                   # Geocoding + TTC distance filter
├── scorer.py                # Composite 0-10 scorer
├── storage.py               # SQLite + JSON dedup store
├── notifier.py              # Telegram bot notifications
├── config.json              # Your local config (gitignored)
├── config.json.example      # Template
├── requirements.txt         # All dependencies
├── scrapers/
│   ├── base.py              # BaseScraper with retry session
│   ├── kijiji.py            # Kijiji (BS4)
│   ├── zumper.py            # Zumper (JSON API)
│   ├── rentals_ca.py        # Rentals.ca (Next.js JSON + BS4)
│   ├── liv_rent.py          # liv.rent (REST API + BS4)
│   ├── padmapper.py         # Padmapper (JSON API)
│   ├── craigslist.py        # Craigslist (RSS + HTML fallback)
│   ├── viewit.py            # ViewIt.ca (BS4)
│   ├── condos_ca.py         # Condos.ca (API + BS4)
│   └── facebook.py          # Facebook Marketplace (Playwright)
├── data/
│   ├── ttc_stations.json    # All 76 TTC subway station coords
│   ├── seen.json            # Dedup seen-IDs (auto-generated)
│   └── listings.db          # SQLite store (auto-generated)
├── deploy/
│   ├── vps_cron.sh          # Oracle VPS setup + cron
│   ├── termux_setup.sh      # Termux/Android setup
│   └── replit_setup.sh      # Replit/Render setup
├── tests/
│   ├── test_geo.py
│   ├── test_scorer.py
│   └── test_classifier.py
└── .github/
    └── workflows/
        └── scrape.yml       # GitHub Actions 4hr cron
```

---

## Scraper Success Rate Notes

| Site | Method | Anti-Bot | Expected Rate |
|---|---|---|---|
| Craigslist | RSS feed | None | 95%+ |
| Kijiji | requests+BS4 | Light | 80-90% |
| Zumper | Internal JSON API | Light | 85%+ |
| Padmapper | Internal JSON API | Light | 85%+ |
| Rentals.ca | Next.js JSON embed | Light | 80%+ |
| liv.rent | REST API | Medium | 70-85% |
| ViewIt | requests+BS4 | None | 90%+ |
| Condos.ca | API + BS4 | Light | 75%+ |
| Facebook | Playwright + cookies | Heavy | 60%+ (with cookies) |

---

## Legal & Ethical Notes

- Respects `robots.txt` implicitly via polite delays (configurable `scrape_delay_s`)
- Nominatim usage follows OSM rate limit (1 req/sec, User-Agent set)
- For personal rental search use only
- Do not deploy at high frequency or commercial scale

---

## API Mode

The scraper pipeline can also be served as a REST API with RapidAPI-style
usage caps, for deployment as a paid API product. The API layer is additive:
it reuses `storage.py` / `scorer.py` / `geo.py` and does NOT modify the CLI
scraper (`main.py` / `classifier.py` / `notifier.py` stay functional for your
own scraping).

### Run locally

```bash
uv venv .venv --python 3.12
uv pip install -r requirements.txt
uv run uvicorn src.api:app --port 8101
# or: uv run python -m src.api
# Swagger docs at http://localhost:8101/docs
```

Inline smoke test (no network, no real LLM call):

```bash
uv run python -m src.api --smoke
```

### Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | none | Liveness + DB listing count + last scrape time. Not counted. |
| GET | `/listings/top` | counted | Top-N scored listings with filters (`rent_limit`, `max_walking_m`, `min_cleanliness`, `min_landlord_vibe`, `max_scam_risk`). |
| GET | `/listings/{id}` | counted | Single listing with full detail + classification. 404 if not found. |
| POST | `/classify` | counted | Classify a listing dict `{title, price, address, description}` on general quality (generic prompt, no personal data). Falls back to a default classification on LLM failure (never 500). |
| GET | `/stations` | counted | TTC subway stations within `radius_m` of a `lat`/`lon` point. |
| POST | `/scrape/refresh` | counted + Pro+ | Trigger a scrape cycle (`python main.py --scrape-only`, 300s timeout). 503 on failure. |

Auth: send `X-RapidAPI-Proxy-Secret` (RapidAPI injects this) or `X-API-Key`
(direct customers). Missing/unknown key = 401. Over the daily limit = 429
with `resets_at` (next midnight UTC).

### Usage tiers

| Tier | Daily requests | Notes |
|---|---|---|
| free | 100 | Demo key `demo-free-key` works for testing (intentionally public). |
| basic | 5,000 | Personal bots, light feeds. |
| pro | 50,000 | Includes `/scrape/refresh`. |
| ultra | unlimited | High-volume platforms. |

Keys + usage are stored in the same SQLite DB (`data/listings.db`) in
`api_keys` and `api_usage` tables. Add a key with:

```bash
uv run python -c "import storage; storage.add_api_key('YOUR_KEY','basic','customer email')"
```

### LLM provider for `/classify`

The API's `/classify` endpoint uses a GENERIC prompt (general listing quality)
and reads keys from env vars only -- it does NOT use the personal prompt or
any hardcoded key from `classifier.py`. Default provider is `gateway` (the
free LLM gateway on VPS-40):

```bash
export RENTAL_LLM_PROVIDER=gateway
export VPS_GATEWAY_URL=http://localhost:8000/v1
export VPS_GATEWAY_API_KEY=your-gateway-key
export RENTAL_LLM_MODEL=coding-fast
```

### Deploy to VPS-40

```bash
bash deploy/vps40-deploy.sh
```

Idempotent. Installs a systemd unit `rental-agent-api.service` on port 8101
(avoids 8100 = pixel-deals, 8000 = gateway) with `--workers 1` (SQLite
single-writer) and `MemoryMax=180M` (VPS-40 is RAM-tight). See the deploy
script header for the iptables line to open 8101 to Tailscale (documented
only, not run automatically).

The deploy inits an empty listings DB. Populate it with
`uv run python main.py --scrape-only` (cron or manual). Some scrapers need a
residential IP; enable only datacenter-safe scrapers in `config.json` on the
VPS.

### RapidAPI listing

See `docs/RAPIDAPI_LISTING.md` for the RapidAPI marketplace listing copy
(name, tagline, description, use cases, endpoint table, pricing tiers, sample
code).

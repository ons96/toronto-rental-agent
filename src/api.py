"""FastAPI service exposing Toronto rental data with RapidAPI-style usage caps.

Additive API layer. Imports and reuses the existing pipeline (storage.py /
scorer.py / geo.py) without duplicating it. The CLI scraper (main.py /
classifier.py / notifier.py) stays functional for the user's own scraping.

The LLM classifier here uses a GENERIC prompt (general listing quality) and
reads keys from env vars only -- it does NOT use the personal "the tenant" prompt
or any hardcoded key from classifier.py.

Run locally:
    uv run uvicorn src.api:app --port 8101
or:
    uv run python -m src.api
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import storage
from geo import haversine_m, load_ttc_stations

log = logging.getLogger("api")

API_VERSION = "1.0"

# Path to the project root (repo dir), so subprocess calls to main.py work
# regardless of the current working directory.
ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Generic classifier (NO personal data, NO hardcoded keys)
# ---------------------------------------------------------------------------
# This is a standalone generic prompt for the PUBLIC API. It classifies
# listings on general quality signals (private room, occupants, cleanliness,
# landlord vibe, scam risk, lease flexibility) -- NOT for a specific person.
# It deliberately does NOT reference the personal CLASSIFY_PROMPT in
# classifier.py (which is for the user's own CLI scraping only).
# Reuse the proven _parse_response / _default_classification helpers from
# classifier.py for the JSON parsing (they are good and well-tested), but the
# prompt + provider selection here are fully generic and env-var-keyed.

API_CLASSIFY_PROMPT = """
You are a Toronto rental listing analyst. Assess the listing below on general
quality signals that matter to any renter. Do not assume any specific person.

Listing:
Title: {title}
Price: ${price}/month
Address: {address}
Description:
{description}

Return JSON with exactly these keys:
{{"private_room": true/false, "occupants": 1-10, "cleanliness": 1-5, "landlord_vibe": 1-5, "scam_risk": 1-5, "lease_flexibility": 1-5, "move_in_match": 1-5, "furniture_match": 1-5, "reasoning": "Brief general assessment of room type, occupant count, cleanliness, landlord professionalism, scam risk, and lease flexibility."}}

Scoring guide:
- private_room: true if the listing is a private room or whole unit; false for a shared room.
- occupants: estimated max number of people in the unit (1-10).
- cleanliness: 5=clearly very clean, 3=average/unknown, 1=clearly dirty.
- landlord_vibe: 5=professional/property manager, 3=average, 1=sketchy/unresponsive signals.
- scam_risk: 5=very likely legitimate (verifyable listing, photos, price realistic), 3=neutral, 1=strong scam signals (too cheap, wire-only, no viewing).
- lease_flexibility: 5=month-to-month/sublet/roommate, 3=standard 1yr, 1=strict long-term only.
- move_in_match: 5=available now/immediately, 3=near-term/unknown, 1=far future.
- furniture_match: 5=unfurnished, 3=furnished, 1=incomplete/unknown.

Return ONLY the JSON.
"""


def _api_providers() -> list:
    """Build the LLM provider list from env vars only (never hardcoded keys).

    Default provider = gateway (the user's free LLM gateway on VPS-40).
    Falls back to noobrouter (its public giveaway key is published as a
    giveaway) if no gateway env vars are set. The supacoder key is NEVER used
    here -- it is a personal key that must never ship in the API path, so this
    function deliberately does NOT call classifier._get_provider_list (which
    appends the hardcoded supacoder key as a fallback).

    Returns a list of (base_url, api_key, model) tuples.
    """
    provider = os.environ.get("RENTAL_LLM_PROVIDER", "gateway").lower()
    model = os.environ.get("RENTAL_LLM_MODEL", "coding-fast")
    providers: list = []

    if provider == "gateway":
        gw_url = os.environ.get("VPS_GATEWAY_URL", "http://localhost:8000/v1")
        gw_key = os.environ.get("VPS_GATEWAY_API_KEY", "")
        providers.append((gw_url, gw_key, model))
        # Public noobrouter giveaway key is published as a giveaway; OK as fallback.
        nb_key = os.environ.get("NOOBROUTER_API_KEY", "sk-zenith-giveaway")
        providers.append(("https://noobrouter.azurewebsites.net/v1", nb_key, "openai/gpt-5.1"))
        return providers

    if provider == "noobrouter":
        nb_key = os.environ.get("NOOBROUTER_API_KEY", "sk-zenith-giveaway")
        providers.append(("https://noobrouter.azurewebsites.net/v1", nb_key, model))
        return providers

    if provider == "openai":
        base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
        key = os.environ.get("OPENAI_API_KEY", "")
        providers.append((base_url, key, model))
        return providers

    if provider == "ollama":
        base_url = os.environ.get("OLLAMA_URL", "http://localhost:11434/v1")
        providers.append((base_url, "ollama", model))
        return providers

    # Unknown provider -> gateway default.
    gw_url = os.environ.get("VPS_GATEWAY_URL", "http://localhost:8000/v1")
    gw_key = os.environ.get("VPS_GATEWAY_API_KEY", "")
    providers.append((gw_url, gw_key, "coding-fast"))
    nb_key = os.environ.get("NOOBROUTER_API_KEY", "sk-zenith-giveaway")
    providers.append(("https://noobrouter.azurewebsites.net/v1", nb_key, "openai/gpt-5.1"))
    return providers


def api_classify(listing: Dict[str, Any], timeout_s: int = 30) -> Dict[str, Any]:
    """Classify a listing with the GENERIC prompt. Never raises.

    Uses a GENERIC prompt (general listing quality) and an env-var-only
    provider list. Reuses the proven _call_openai_compat + _parse_response
    helpers from classifier.py for the HTTP call + JSON parsing (they are
    good and well-tested), but builds the provider list itself so the
    hardcoded supacoder key is NEVER in the API path.

    Falls back to a default classification on any failure (network, timeout,
    parse error) so the API never returns a 500 from the classifier.
    """
    try:
        from classifier import _call_openai_compat, _parse_response, _default_classification

        prompt = API_CLASSIFY_PROMPT.format(
            title=listing.get("title", ""),
            price=listing.get("price", 0),
            address=listing.get("address", ""),
            description=str(listing.get("description", ""))[:2000],
        )

        for base_url, api_key, model in _api_providers():
            try:
                raw = _call_openai_compat(prompt, base_url, api_key, model)
                if raw:
                    result = _parse_response(raw)
                    if result["reasoning"] != "Classification unavailable.":
                        return result
            except Exception as e:
                log.debug("[api] provider %s failed: %s", base_url, e)
                continue

        log.warning("[api] all LLM providers failed, returning default classification")
        return _default_classification()
    except Exception as e:  # pragma: no cover - defensive
        log.warning("[api] classify failed: %s", e)
        from classifier import _default_classification

        return _default_classification()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure the schema + demo key exist when the server boots."""
    storage.init_db()
    yield


app = FastAPI(
    title="Toronto Rental Finder API",
    version=API_VERSION,
    description="Toronto rental listings aggregated from 9 sources, scored by price + TTC transit proximity + LLM quality classification.",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Auth + usage-cap dependency
# ---------------------------------------------------------------------------
# ponytail: SQLite single-writer is the ceiling. Single uvicorn process on the
# VPS (--workers 1) = no write contention. Upgrade path: Redis INCR/EXPIRE for
# counters if multi-worker; keep SQLite as the key/tier source of truth.

# RapidAPI injects X-RapidAPI-Proxy-Secret; direct/own customers use X-API-Key.
_API_KEY_HEADERS = ("x-api-key", "x-rapidapi-proxy-secret")


def _resets_at_iso() -> str:
    """Next midnight UTC as an ISO-8601 string."""
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.isoformat()


def require_api_key(request: Request) -> dict:
    """Resolve the caller's key+tier and enforce the daily usage cap.

    Reads X-RapidAPI-Proxy-Secret (RapidAPI) or X-API-Key (direct customers).
    Unknown / missing key -> 401. Over daily limit -> 429. Otherwise returns
    a dict describing the caller and increments today's counter.
    """
    key: Optional[str] = None
    for h in _API_KEY_HEADERS:
        v = request.headers.get(h)
        if v:
            key = v.strip()
            break
    if not key:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "missing_api_key",
                "message": "Provide X-API-Key (direct) or X-RapidAPI-Proxy-Secret (RapidAPI).",
            },
        )

    row = storage.get_api_key(key)
    if row is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_api_key", "message": "Unknown or inactive API key."},
        )

    tier = row["tier"]
    limit = storage.tier_limit(tier)
    used = storage.today_usage(key)

    # None limit = unlimited (ultra tier); skip both the check and the increment
    # so ultra callers never touch the usage table.
    if limit is not None:
        if used >= limit:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "daily_limit_exceeded",
                    "limit": limit,
                    "used": used,
                    "tier": tier,
                    "resets_at": _resets_at_iso(),
                },
            )
        used = storage.incr_usage(key)

    return {"key": key, "tier": tier, "limit": limit, "used": used}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ClassifyRequest(BaseModel):
    title: str = Field(..., description="Listing title")
    price: int = Field(0, description="Monthly rent in CAD")
    address: str = Field("", description="Listing address")
    description: str = Field("", description="Full listing description text")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    """Liveness + DB listing count + last scrape time. Not auth-gated, not rate-counted."""
    return {"status": "ok", "db": storage.db_health(), "version": API_VERSION}


@app.get("/listings/top")
def listings_top(
    request: Request,
    n: int = Query(20, ge=1, le=500),
    rent_limit: Optional[int] = Query(None, ge=0, description="Max monthly rent (CAD)"),
    max_walking_m: Optional[int] = Query(None, ge=0, description="Max transit walking distance (m)"),
    min_cleanliness: Optional[int] = Query(None, ge=1, le=5),
    min_landlord_vibe: Optional[int] = Query(None, ge=1, le=5),
    max_scam_risk: Optional[int] = Query(None, ge=1, le=5, description="Min scam-safety score (higher=safer)"),
    caller: dict = Depends(require_api_key),
) -> dict:
    """Top-N scored listings from SQLite with optional filters.

    scam_risk is stored as a safety score (higher = safer), so the filter is
    `scam_risk >= max_scam_risk` (a higher min-safety floor). This matches the
    scorer's interpretation: scam_score = (scam_risk - 1) / 4 * 10.
    """
    listings = storage.get_top_listings(
        n=n,
        rent_limit=rent_limit,
        max_walking_m=max_walking_m,
        min_cleanliness=min_cleanliness,
        min_landlord_vibe=min_landlord_vibe,
        max_scam_risk=max_scam_risk,
    )
    return {
        "count": len(listings),
        "listings": listings,
        "tier": caller["tier"],
        "used": caller["used"],
        "limit": caller["limit"],
    }


@app.get("/listings/{listing_id}")
def listing_one(
    listing_id: str,
    request: Request,
    caller: dict = Depends(require_api_key),
) -> dict:
    """Single listing with full detail + classification. 404 if not found."""
    listing = storage.get_listing_by_id(listing_id)
    if listing is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "id": listing_id},
        )
    return {"listing": listing, "tier": caller["tier"], "used": caller["used"]}


@app.post("/classify")
def classify(
    body: ClassifyRequest,
    request: Request,
    caller: dict = Depends(require_api_key),
) -> dict:
    """Classify a listing dict on general quality (generic prompt, no personal data).

    The LLM call has a 30s timeout and falls back to a default classification
    on any failure -- this endpoint never returns 500 from the classifier.
    """
    listing = {
        "title": body.title,
        "price": body.price,
        "address": body.address,
        "description": body.description,
    }
    classification = api_classify(listing, timeout_s=30)
    return {
        "classification": classification,
        "tier": caller["tier"],
        "used": caller["used"],
    }


@app.get("/stations")
def stations(
    request: Request,
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_m: int = Query(800, ge=50, le=10000),
    caller: dict = Depends(require_api_key),
) -> dict:
    """TTC subway stations within radius_m of a lat/lon point."""
    all_stations = load_ttc_stations()
    within: List[Dict[str, Any]] = []
    for s in all_stations:
        d = haversine_m(lat, lon, s["lat"], s["lon"])
        if d <= radius_m:
            within.append(
                {"name": s["name"], "line": s["line"], "lat": s["lat"], "lon": s["lon"], "distance_m": round(d, 0)}
            )
    within.sort(key=lambda x: x["distance_m"])
    return {
        "count": len(within),
        "stations": within,
        "tier": caller["tier"],
        "used": caller["used"],
    }


@app.post("/scrape/refresh")
def scrape_refresh(
    request: Request,
    caller: dict = Depends(require_api_key),
) -> JSONResponse:
    """Trigger a scrape cycle (Pro+ gated, paid feature).

    Shells out to `python main.py --scrape-only` with a 300s timeout. Returns
    503 on failure (network down, CF block, timeout). The service keeps
    serving cached data from SQLite regardless.
    """
    if caller["tier"] not in ("pro", "ultra"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "tier_required",
                "message": "Scrape refresh is a Pro+ feature. Upgrade your tier.",
                "tier": caller["tier"],
            },
        )

    try:
        proc = subprocess.run(
            [sys.executable, "main.py", "--scrape-only"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=503,
            detail={"error": "scrape_timeout", "message": "Scrape cycle timed out (300s). Cached data still served."},
        )
    except Exception as e:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=503,
            detail={"error": "scrape_failed", "message": f"Could not run scrape: {e}"},
        )

    if proc.returncode != 0:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "scrape_failed",
                "message": "Scrape did not complete. The service is still serving cached data.",
                "returncode": proc.returncode,
                "stderr_tail": (proc.stderr or "").strip().splitlines()[-1] if proc.stderr else "",
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "refreshed",
            "db": storage.db_health(),
            "stdout_tail": (proc.stdout or "").strip().splitlines()[-1] if proc.stdout else "",
        },
    )


# ---------------------------------------------------------------------------
# Boot / smoke
# ---------------------------------------------------------------------------

def _smoke() -> None:
    """Tiny inline smoke using FastAPI TestClient (no network, no real LLM call)."""
    from fastapi.testclient import TestClient

    storage.init_db()

    client = TestClient(app)

    h = client.get("/health")
    assert h.status_code == 200, h.text
    body = h.json()
    assert body["status"] == "ok"
    assert "db" in body and "version" in body
    print("health OK:", json.dumps(body))

    # No key -> 401
    noauth = client.get("/listings/top?n=3")
    assert noauth.status_code == 401, noauth.text
    print("no-auth 401 OK:", noauth.json())

    # Invalid key -> 401
    bad = client.get("/listings/top?n=3", headers={"X-API-Key": "not-a-real-key"})
    assert bad.status_code == 401, bad.text
    print("invalid-key 401 OK:", bad.json())

    # Demo key -> 200 (empty DB returns count=0, not an error)
    r = client.get("/listings/top?n=3", headers={"X-API-Key": storage.DEMO_KEY})
    assert r.status_code == 200, r.text
    j = r.json()
    assert "count" in j and "listings" in j
    print("listings/top OK:", json.dumps(j))

    # /classify with demo key -> 200, returns a classification dict (no network
    # -> falls back to default classification, still a valid 200 response).
    c = client.post(
        "/classify",
        headers={"X-API-Key": storage.DEMO_KEY},
        json={"title": "Bright private room near Bloor-Yonge", "price": 1350,
              "address": "Bloor St W, Toronto", "description": "Clean private room, shared bath, month-to-month."},
    )
    assert c.status_code == 200, c.text
    cj = c.json()
    assert "classification" in cj
    clf = cj["classification"]
    for k in ("private_room", "occupants", "cleanliness", "landlord_vibe", "scam_risk", "lease_flexibility"):
        assert k in clf, f"missing key {k}"
    print("classify OK:", json.dumps(cj))

    # /stations with demo key -> 200
    s = client.get("/stations", headers={"X-API-Key": storage.DEMO_KEY},
                   params={"lat": 43.6532, "lon": -79.3832, "radius_m": 1000})
    assert s.status_code == 200, s.text
    print("stations OK:", json.dumps(s.json()))

    print("SMOKE PASS")


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Toronto Rental Finder API")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8101)
    p.add_argument("--smoke", action="store_true", help="run inline smoke and exit")
    p.add_argument("--reload", action="store_true")
    args = p.parse_args()

    if args.smoke:
        _smoke()
        return 0

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    storage.init_db()
    import uvicorn

    print(f"Toronto Rental Finder API: http://{args.host}:{args.port}  (docs at /docs)")
    uvicorn.run("src.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

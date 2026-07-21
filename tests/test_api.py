"""Tests for the FastAPI API layer (TestClient, no network, no real LLM call)."""

import os
import sys
from pathlib import Path

# Ensure the project root is importable (storage, geo, classifier, src.api).
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient

import storage


def _fresh_db(tmp_path, monkeypatch) -> str:
    """Point storage at a fresh temp DB and init it."""
    db_file = str(tmp_path / "test_listings.db")
    monkeypatch.setenv("RENTAL_DB_FILE", db_file)
    # storage caches nothing at module level for the path (reads env each call),
    # but the app's lifespan calls storage.init_db() which reads _db_path().
    storage.init_db(db_file)
    return db_file


def test_health_ok(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    from src.api import app

    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert "db" in body
    assert "version" in body


def test_listings_top_no_key_401(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    from src.api import app

    client = TestClient(app)
    r = client.get("/listings/top?n=3")
    assert r.status_code == 401, r.text
    assert r.json()["detail"]["error"] == "missing_api_key"


def test_listings_top_invalid_key_401(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    from src.api import app

    client = TestClient(app)
    r = client.get("/listings/top?n=3", headers={"X-API-Key": "not-a-real-key"})
    assert r.status_code == 401, r.text
    assert r.json()["detail"]["error"] == "invalid_api_key"


def test_listings_top_demo_key_empty_db_200(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    from src.api import app

    client = TestClient(app)
    r = client.get("/listings/top?n=3", headers={"X-API-Key": storage.DEMO_KEY})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 0
    assert body["listings"] == []
    assert body["tier"] == "free"


def test_listings_top_with_seed_data(tmp_path, monkeypatch):
    db_file = _fresh_db(tmp_path, monkeypatch)
    # Seed a listing directly so the top endpoint returns it.
    import sqlite3

    conn = sqlite3.connect(db_file)
    conn.execute(
        """
        INSERT INTO listings (
            id, source, url, title, price, address, description,
            nearest_transit, transit_dist_m, private_room, occupants,
            cleanliness, landlord_vibe, scam_risk, lease_flexibility,
            move_in_match, furniture_match, reasoning, score, scraped_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            "test-1", "zumper", "https://example.com/1",
            "Bright room near Bloor", 1300, "Bloor St W, Toronto",
            "Clean private room.", "TTC: Bloor-Yonge", 180, 1, 2,
            4, 4, 4, 5, 4, 3, "Looks good.", 8.5, "2026-07-15T03:00:00",
        ),
    )
    conn.commit()
    conn.close()

    from src.api import app

    client = TestClient(app)
    r = client.get("/listings/top?n=3", headers={"X-API-Key": storage.DEMO_KEY})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 1
    listing = body["listings"][0]
    assert listing["id"] == "test-1"
    assert listing["price"] == 1300
    assert listing["score"] == 8.5
    assert "classification" in listing
    assert listing["classification"]["cleanliness"] == 4


def test_listings_top_rent_limit_filter(tmp_path, monkeypatch):
    db_file = _fresh_db(tmp_path, monkeypatch)
    import sqlite3

    conn = sqlite3.connect(db_file)
    for i, price in enumerate((1200, 1500, 2000), start=1):
        conn.execute(
            "INSERT INTO listings (id, title, price, score, scraped_at) VALUES (?,?,?,5.0,'2026-07-15')",
            (f"r-{i}", f"room {i}", price),
        )
    conn.commit()
    conn.close()

    from src.api import app

    client = TestClient(app)
    r = client.get(
        "/listings/top?n=10&rent_limit=1500",
        headers={"X-API-Key": storage.DEMO_KEY},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    prices = [l["price"] for l in body["listings"]]
    assert all(p <= 1500 for p in prices)
    assert 2000 not in prices


def test_listing_by_id_404_and_200(tmp_path, monkeypatch):
    db_file = _fresh_db(tmp_path, monkeypatch)
    import sqlite3

    conn = sqlite3.connect(db_file)
    conn.execute(
        "INSERT INTO listings (id, title, price, score, scraped_at) VALUES (?,?,?,5.0,'2026-07-15')",
        ("real-1", "a room", 1300),
    )
    conn.commit()
    conn.close()

    from src.api import app

    client = TestClient(app)
    missing = client.get("/listings/nope", headers={"X-API-Key": storage.DEMO_KEY})
    assert missing.status_code == 404, missing.text

    found = client.get("/listings/real-1", headers={"X-API-Key": storage.DEMO_KEY})
    assert found.status_code == 200, found.text
    assert found.json()["listing"]["id"] == "real-1"


def test_classify_demo_key_200(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    # No LLM env vars set -> api_classify falls back to default classification,
    # but the endpoint must still return 200 with a full classification dict.
    monkeypatch.delenv("VPS_GATEWAY_API_KEY", raising=False)
    monkeypatch.delenv("NOOBROUTER_API_KEY", raising=False)
    from src.api import app

    client = TestClient(app)
    r = client.post(
        "/classify",
        headers={"X-API-Key": storage.DEMO_KEY},
        json={
            "title": "Bright private room near Bloor-Yonge",
            "price": 1350,
            "address": "Bloor St W, Toronto",
            "description": "Clean private room, shared bath, month-to-month.",
        },
    )
    assert r.status_code == 200, r.text
    clf = r.json()["classification"]
    for k in ("private_room", "occupants", "cleanliness", "landlord_vibe",
              "scam_risk", "lease_flexibility", "move_in_match",
              "furniture_match", "reasoning"):
        assert k in clf, f"missing key {k}"


def test_stations_demo_key_200(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    from src.api import app

    client = TestClient(app)
    r = client.get(
        "/stations",
        headers={"X-API-Key": storage.DEMO_KEY},
        params={"lat": 43.6452, "lon": -79.3806, "radius_m": 1000},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] >= 1
    assert "distance_m" in body["stations"][0]
    # Union Station is at the query point, so it must be within 1000m.
    names = [s["name"] for s in body["stations"]]
    assert "Union" in names


def test_scrape_refresh_free_tier_403(tmp_path, monkeypatch):
    _fresh_db(tmp_path, monkeypatch)
    from src.api import app

    client = TestClient(app)
    # Free tier (demo key) must not be allowed to trigger a scrape.
    r = client.post("/scrape/refresh", headers={"X-API-Key": storage.DEMO_KEY})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["error"] == "tier_required"


def test_api_classify_no_hardcoded_personal_prompt():
    """The generic API prompt must NOT contain personal data."""
    from src.api import API_CLASSIFY_PROMPT

    # No person's name, no permit deadline, no personal move-in date.
    for forbidden in ("the tenant", "Sept 2026", "work permit", "April 20", "April 20th"):
        assert forbidden not in API_CLASSIFY_PROMPT, (
            f"API_CLASSIFY_PROMPT leaks personal data: {forbidden}"
        )
    assert "specific person" not in API_CLASSIFY_PROMPT.lower() or "do not assume" in API_CLASSIFY_PROMPT.lower()


def test_api_providers_no_hardcoded_secrets():
    """The API provider list must never contain the supacoder key or any sk- literal."""
    from src.api import _api_providers

    providers = _api_providers()
    blob = str(providers)
    # The leaked personal supacoder key must NEVER appear in the API path.
    assert "REDACTED_SUPACODER_KEY" not in blob
    # No supacoder URL in the API provider list at all.
    assert "supacoder.top" not in blob
    # The only sk- literal allowed is the published noobrouter giveaway key.
    for _base, key, _model in providers:
        assert key in ("", "ollama", "sk-zenith-giveaway") or key.startswith("${") or os.environ.get("VPS_GATEWAY_API_KEY"), (
            f"unexpected hardcoded key in API provider list: {key!r}"
        )

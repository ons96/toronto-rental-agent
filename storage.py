"""Storage layer: SQLite for listings, JSON for seen-IDs dedup."""
import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── Schema constants (shared by Store._init_db and the module-level init_db) ──

LISTINGS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    source TEXT,
    url TEXT,
    title TEXT,
    price INTEGER,
    address TEXT,
    description TEXT,
    image_url TEXT,
    lat REAL,
    lon REAL,
    bedrooms TEXT,
    bathrooms TEXT,
    nearest_transit TEXT,
    transit_dist_m REAL,
    private_room INTEGER,
    occupants INTEGER,
    cleanliness INTEGER,
    landlord_vibe INTEGER,
    scam_risk INTEGER,
    lease_flexibility INTEGER,
    move_in_match INTEGER,
    furniture_match INTEGER,
    reasoning TEXT,
    score REAL,
    notified INTEGER DEFAULT 0,
    scraped_at TEXT,
    notified_at TEXT
);
"""

API_KEYS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS api_keys (
    key TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    contact TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    active INTEGER NOT NULL DEFAULT 1
);
"""

API_USAGE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS api_usage (
    key TEXT NOT NULL,
    date TEXT NOT NULL,
    count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (key, date)
);
CREATE INDEX IF NOT EXISTS idx_api_usage_date ON api_usage(date);
"""


class Store:
    def __init__(self, config: Dict):
        data_dir = Path(config.get("data_dir", "data"))
        data_dir.mkdir(parents=True, exist_ok=True)

        self.seen_file = Path(config.get("seen_file", "data/seen.json"))
        self.db_path = Path(config.get("db_file", "data/listings.db"))
        self._seen: Set[str] = self._load_seen()
        self.conn = self._init_db()

    # ── Seen-ID dedup ────────────────────────────────────────────────────────

    def _load_seen(self) -> Set[str]:
        if self.seen_file.exists():
            try:
                with open(self.seen_file) as f:
                    return set(json.load(f))
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"[store] Could not load seen file: {e}")
        return set()

    def _save_seen(self):
        with open(self.seen_file, "w") as f:
            json.dump(list(self._seen), f)

    def is_seen(self, listing_id: str) -> bool:
        return listing_id in self._seen

    def mark_seen(self, listing_id: str):
        self._seen.add(listing_id)
        self._save_seen()

    def mark_seen_batch(self, listing_ids: List[str]):
        self._seen.update(listing_ids)
        self._save_seen()

    # ── SQLite ───────────────────────────────────────────────────────────────

    def _init_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(
            LISTINGS_SCHEMA_SQL + API_KEYS_SCHEMA_SQL + API_USAGE_SCHEMA_SQL
        )
        _seed_demo_key(conn)
        conn.commit()
        return conn

    def upsert_listing(self, listing: Dict[str, Any]):
        """Insert or replace a listing record."""
        now = datetime.utcnow().isoformat()
        clf = listing.get("classification", {})
        self.conn.execute("""
            INSERT OR REPLACE INTO listings (
                id, source, url, title, price, address, description, image_url,
                lat, lon, bedrooms, bathrooms,
                nearest_transit, transit_dist_m,
                private_room, occupants, cleanliness, landlord_vibe, scam_risk,
                reasoning, score, scraped_at
            ) VALUES (
                :id, :source, :url, :title, :price, :address, :description, :image_url,
                :lat, :lon, :bedrooms, :bathrooms,
                :nearest_transit, :transit_dist_m,
                :private_room, :occupants, :cleanliness, :landlord_vibe, :scam_risk,
                :reasoning, :score, :scraped_at
            )
        """, {
            "id": listing["id"],
            "source": listing.get("source", ""),
            "url": listing.get("url", ""),
            "title": listing.get("title", ""),
            "price": listing.get("price", 0),
            "address": listing.get("address", ""),
            "description": listing.get("description", ""),
            "image_url": listing.get("image_url", ""),
            "lat": listing.get("lat"),
            "lon": listing.get("lon"),
            "bedrooms": str(listing.get("bedrooms", "")),
            "bathrooms": str(listing.get("bathrooms", "")),
            "nearest_transit": listing.get("nearest_transit", ""),
            "transit_dist_m": listing.get("transit_dist_m"),
            "private_room": int(clf.get("private_room", True)),
            "occupants": clf.get("occupants", 0),
            "cleanliness": clf.get("cleanliness", 0),
            "landlord_vibe": clf.get("landlord_vibe", 0),
            "scam_risk": clf.get("scam_risk", 0),
            "reasoning": clf.get("reasoning", ""),
            "score": listing.get("score", 0.0),
            "scraped_at": now,
        })
        self.conn.commit()

    def get_top_unnotified(self, n: int = 5) -> List[Dict]:
        """Fetch top N unnotified listings by score."""
        cur = self.conn.execute("""
            SELECT * FROM listings
            WHERE notified = 0
            ORDER BY score DESC
            LIMIT ?
        """, (n,))
        return [dict(row) for row in cur.fetchall()]

    def mark_notified(self, listing_id: str):
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            "UPDATE listings SET notified=1, notified_at=? WHERE id=?",
            (now, listing_id),
        )
        self.conn.commit()


    def export_csv(self, path: str = "data/listings.csv"):
        """Export all qualifying listings to CSV for easy review."""
        import csv
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        cur = self.conn.execute("""
            SELECT
                id, source, scraped_at, price, title, address,
                url, image_url,
                lat, lon, nearest_transit, transit_dist_m,
                private_room, occupants,
                cleanliness, landlord_vibe, scam_risk, score,
                reasoning, description
            FROM listings
            ORDER BY score DESC, scraped_at DESC
        """)
        rows = cur.fetchall()
        if not rows:
            return 0
        cols = [d[0] for d in cur.description]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=cols)
            writer.writeheader()
            for row in rows:
                writer.writerow(dict(zip(cols, row)))
        return len(rows)
    def close(self):
        self.conn.close()


# ── Module-level API helpers (for the FastAPI layer) ──────────────────────────
# These operate on the same data/listings.db file as the Store class but use
# short-lived connections so the API process does not hold a long-lived
# single-writer connection open (the CLI Store owns one for its run).
# ponytail: SQLite single-writer is the ceiling. The API runs as one uvicorn
# process (--workers 1) so there is no write contention. Upgrade path: move
# usage counting to Redis (INCR + EXPIRE) if you scale to multiple workers or
# need sub-millisecond counters; SQLite stays the source of truth for keys.

DEMO_KEY = "demo-free-key"

# Tier -> daily request cap. None means unlimited (ultra tier).
TIER_LIMITS: Dict[str, Optional[int]] = {
    "free": 100,
    "basic": 5000,
    "pro": 50000,
    "ultra": None,
}

DEFAULT_DB_PATH = str(Path("data/listings.db"))


def _db_path() -> str:
    return os.environ.get("RENTAL_DB_FILE", DEFAULT_DB_PATH)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Ensure the schema + demo key exist. Safe to call on every boot."""
    path = db_path or _db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        LISTINGS_SCHEMA_SQL + API_KEYS_SCHEMA_SQL + API_USAGE_SCHEMA_SQL
    )
    _seed_demo_key(conn)
    conn.commit()
    conn.close()


def _seed_demo_key(conn: sqlite3.Connection) -> None:
    """Seed the demo free key on init if the api_keys table is empty."""
    n = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
    if n == 0:
        conn.execute(
            "INSERT INTO api_keys(key, tier, contact) VALUES (?,?,?)",
            (DEMO_KEY, "free", "demo/test key, intentionally public"),
        )


def get_api_key(key: str) -> Optional[Dict[str, Any]]:
    """Return the api_keys row for ``key`` if active, else None."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key=? AND active=1", (key,)
        ).fetchone()
    return dict(row) if row else None


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def today_usage(key: str) -> int:
    """Today's (UTC) request count for ``key`` (0 if none yet)."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT count FROM api_usage WHERE key=? AND date=?",
            (key, _today_utc()),
        ).fetchone()
    return int(row["count"]) if row else 0


def incr_usage(key: str) -> int:
    """Atomically increment today's counter and return the new value."""
    today = _today_utc()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO api_usage(key, date, count) VALUES (?,?,1)
            ON CONFLICT(key, date) DO UPDATE SET count = count + 1
            """,
            (key, today),
        )
        row = conn.execute(
            "SELECT count FROM api_usage WHERE key=? AND date=?",
            (key, today),
        ).fetchone()
        conn.commit()
    return int(row["count"]) if row else 1


def tier_limit(tier: str) -> Optional[int]:
    """Daily request cap for ``tier`` (None = unlimited)."""
    return TIER_LIMITS.get(tier)


def add_api_key(key: str, tier: str, contact: str = "") -> None:
    """Insert (or reactivate) an API key. Used by an admin CLI / deploy."""
    if tier not in TIER_LIMITS:
        raise ValueError(f"unknown tier: {tier}")
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO api_keys(key, tier, contact, active) VALUES (?,?,?,1)
            ON CONFLICT(key) DO UPDATE SET tier=excluded.tier, contact=excluded.contact, active=1
            """,
            (key, tier, contact),
        )
        conn.commit()


# ── Listing query helpers (read-only, for the API endpoints) ─────────────────

def _row_to_public(row: sqlite3.Row) -> Dict[str, Any]:
    """Shape a listing row into the public API response."""
    d = dict(row)
    return {
        "id": d.get("id"),
        "source": d.get("source"),
        "url": d.get("url"),
        "title": d.get("title"),
        "price": d.get("price"),
        "address": d.get("address"),
        "image_url": d.get("image_url"),
        "lat": d.get("lat"),
        "lon": d.get("lon"),
        "bedrooms": d.get("bedrooms"),
        "bathrooms": d.get("bathrooms"),
        "nearest_transit": d.get("nearest_transit"),
        "transit_dist_m": d.get("transit_dist_m"),
        "score": d.get("score"),
        "classification": {
            "private_room": bool(d.get("private_room", True)),
            "occupants": d.get("occupants"),
            "cleanliness": d.get("cleanliness"),
            "landlord_vibe": d.get("landlord_vibe"),
            "scam_risk": d.get("scam_risk"),
            "lease_flexibility": d.get("lease_flexibility"),
            "move_in_match": d.get("move_in_match"),
            "furniture_match": d.get("furniture_match"),
            "reasoning": d.get("reasoning"),
        },
        "scraped_at": d.get("scraped_at"),
    }


def count_listings() -> int:
    with _connect() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0])


def last_scrape_at() -> Optional[str]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(scraped_at) AS m FROM listings"
        ).fetchone()
    return row["m"] if row and row["m"] is not None else None


def db_health() -> Dict[str, Any]:
    """Counts + freshness for /health."""
    return {
        "listings": count_listings(),
        "last_scrape_at": last_scrape_at(),
    }


def get_top_listings(
    n: int = 20,
    rent_limit: Optional[int] = None,
    max_walking_m: Optional[int] = None,
    min_cleanliness: Optional[int] = None,
    min_landlord_vibe: Optional[int] = None,
    max_scam_risk: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Top-N scored listings with optional filters. Returns public-shaped dicts."""
    sql = (
        "SELECT * FROM listings WHERE score IS NOT NULL "
        "AND (:rent_limit IS NULL OR price <= :rent_limit) "
        "AND (:max_walking_m IS NULL OR transit_dist_m IS NULL OR transit_dist_m <= :max_walking_m) "
        "AND (:min_cleanliness IS NULL OR cleanliness >= :min_cleanliness) "
        "AND (:min_landlord_vibe IS NULL OR landlord_vibe >= :min_landlord_vibe) "
        "AND (:max_scam_risk IS NULL OR scam_risk >= :max_scam_risk) "
        "ORDER BY score DESC LIMIT :n"
    )
    params = {
        "rent_limit": rent_limit,
        "max_walking_m": max_walking_m,
        "min_cleanliness": min_cleanliness,
        "min_landlord_vibe": min_landlord_vibe,
        "max_scam_risk": max_scam_risk,
        "n": n,
    }
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_public(r) for r in rows]


def get_listing_by_id(listing_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM listings WHERE id = ?", (listing_id,)
        ).fetchone()
    return _row_to_public(row) if row else None

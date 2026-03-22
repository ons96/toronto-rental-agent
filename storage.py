"""Storage layer: SQLite for listings, JSON for seen-IDs dedup."""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id              TEXT PRIMARY KEY,
                source          TEXT,
                url             TEXT,
                title           TEXT,
                price           INTEGER,
                address         TEXT,
                description     TEXT,
                image_url       TEXT,
                lat             REAL,
                lon             REAL,
                bedrooms        TEXT,
                bathrooms       TEXT,
                nearest_transit TEXT,
                transit_dist_m  REAL,
                private_room    INTEGER,
                occupants       INTEGER,
                cleanliness     INTEGER,
                landlord_vibe   INTEGER,
                scam_risk       INTEGER,
                reasoning       TEXT,
                score           REAL,
                notified        INTEGER DEFAULT 0,
                scraped_at      TEXT,
                notified_at     TEXT
            )
        """)
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

    def close(self):
        self.conn.close()

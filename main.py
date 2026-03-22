"""Toronto Rental Agent — main entry point.

Usage:
  python main.py                  # Run full scrape + notify cycle
  python main.py --scrape-only    # Scrape and classify, no Telegram
  python main.py --notify-only    # Send top unnotified from DB
  python main.py --test-telegram  # Send a test message to verify bot config
"""
import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional

from geo import geocode, is_within_range, load_ttc_stations
from classifier import classify_listing, passes_filter
from scorer import score_listing
from storage import Store
from notifier import send_listings

# ── Logging ──────────────────────────────────────────────────────────────────
Path("logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/agent.log", mode="a"),
    ],
)
logger = logging.getLogger("main")


# ── Config ───────────────────────────────────────────────────────────────────

def load_config(path: str = "config.json") -> Dict:
    config_path = Path(path)
    if not config_path.exists():
        logger.error(f"Config file not found: {path}")
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


# ── Scraper registry ─────────────────────────────────────────────────────────

def get_scrapers(config: Dict):
    enabled = set(config.get("enabled_scrapers", []))
    scrapers = []
    if "kijiji" in enabled:
        from scrapers.kijiji import KijijiScraper
        scrapers.append(KijijiScraper(config))
    if "zumper" in enabled:
        from scrapers.zumper import ZumperScraper
        scrapers.append(ZumperScraper(config))
    if "rentals_ca" in enabled:
        from scrapers.rentals_ca import RentalsCaScraper
        scrapers.append(RentalsCaScraper(config))
    if "liv_rent" in enabled:
        from scrapers.liv_rent import LivRentScraper
        scrapers.append(LivRentScraper(config))
    if "padmapper" in enabled:
        from scrapers.padmapper import PadmapperScraper
        scrapers.append(PadmapperScraper(config))
    if "craigslist" in enabled:
        from scrapers.craigslist import CraigslistScraper
        scrapers.append(CraigslistScraper(config))
    if "viewit" in enabled:
        from scrapers.viewit import ViewitScraper
        scrapers.append(ViewitScraper(config))
    if "facebook" in enabled:
        from scrapers.facebook import FacebookScraper
        scrapers.append(FacebookScraper(config))
    if "condos_ca" in enabled:
        from scrapers.condos_ca import CondosCaScraper
        scrapers.append(CondosCaScraper(config))
    return scrapers


# ── Concurrent scraping ───────────────────────────────────────────────────────

def _run_scraper_safe(scraper) -> List[Dict]:
    """Run a single scraper, catch all exceptions."""
    try:
        results = scraper.scrape()
        logger.info(f"[{scraper.name}] returned {len(results)} listings")
        return results
    except Exception as e:
        logger.error(f"[{scraper.name}] crashed: {e}", exc_info=True)
        return []


def scrape_all_concurrent(scrapers, max_workers: int = 4) -> List[Dict]:
    """Run all scrapers concurrently with ThreadPoolExecutor."""
    all_listings = []
    # Group scrapers: run up to max_workers at once
    # Each scraper does its own internal rate-limiting via _sleep()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_run_scraper_safe, s): s.name for s in scrapers}
        for future in as_completed(futures):
            name = futures[future]
            try:
                listings = future.result()
                all_listings.extend(listings)
            except Exception as e:
                logger.error(f"[{name}] future error: {e}")
    return all_listings


# ── Pipeline ─────────────────────────────────────────────────────────────────

def run_scrape(config: Dict, store: Store) -> List[Dict]:
    ttc_stations = load_ttc_stations()

    # Geocode anchor address
    anchor_coords: Optional[tuple] = None
    anchor = config.get("anchor_address", "")
    if anchor:
        anchor_coords = geocode(anchor)
        if anchor_coords:
            logger.info(f"Anchor geocoded: {anchor} → {anchor_coords}")
        else:
            logger.warning(f"Could not geocode anchor: {anchor}")

    anchor_lat = anchor_coords[0] if anchor_coords else None
    anchor_lon = anchor_coords[1] if anchor_coords else None

    scrapers = get_scrapers(config)
    logger.info(f"Running {len(scrapers)} scrapers concurrently (max_workers=4)...")

    # ── Concurrent scrape ──
    raw_listings = scrape_all_concurrent(scrapers, max_workers=4)
    logger.info(f"Total raw listings collected: {len(raw_listings)}")

    # ── Process: geo-filter → classify → score (concurrent geocoding) ──
    new_listings: List[Dict] = []
    
    # Batch geocode addresses concurrently (Nominatim: 1 req/sec enforced inside geocode())
    # We do this serially to respect Nominatim rate limit
    for listing in raw_listings:
        lid = listing.get("id", "")
        if not lid:
            continue
        if store.is_seen(lid):
            continue

        # Geocode if no coords
        if not listing.get("lat") or not listing.get("lon"):
            coords = geocode(listing.get("address", ""))
            if coords:
                listing["lat"], listing["lon"] = coords

        # Distance filter
        passes_geo, dist_m, transit_label = is_within_range(
            listing.get("lat"),
            listing.get("lon"),
            ttc_stations,
            anchor_lat,
            anchor_lon,
            max_m=config.get("max_walking_m", 1200),
        )
        listing["transit_dist_m"] = dist_m
        listing["nearest_transit"] = transit_label

        if not passes_geo:
            logger.debug(f"Geo-filtered ({dist_m:.0f}m): {lid}")
            store.mark_seen(lid)
            continue

        # LLM classification
        classification = classify_listing(listing, config)
        listing["classification"] = classification

        # Quality filter
        if not passes_filter(classification, config):
            logger.debug(f"Quality-filtered: {lid}")
            store.mark_seen(lid)
            continue

        # Score
        listing["score"] = score_listing(listing, config)

        # Persist
        store.upsert_listing(listing)
        store.mark_seen(lid)
        new_listings.append(listing)
        logger.info(
            f"✅ [{listing['source']}] {listing['title'][:50]} "
            f"${listing['price']}/mo score={listing['score']} "
            f"| {transit_label} {dist_m:.0f}m"
        )

    logger.info(f"Scrape complete. {len(new_listings)} new qualifying listings.")
    return new_listings


def run_notify(config: Dict, store: Store, listings: Optional[List[Dict]] = None):
    if listings is None:
        top_n = config.get("top_n_daily", 5)
        listings = store.get_top_unnotified(top_n)
    if not listings:
        logger.info("No new listings to notify.")
        send_listings([], config)
        return
    top_n = config.get("top_n_daily", 5)
    to_notify = sorted(listings, key=lambda x: x.get("score", 0), reverse=True)[:top_n]
    send_listings(to_notify, config)
    for listing in to_notify:
        store.mark_notified(listing["id"])
    logger.info(f"Notified {len(to_notify)} listings via Telegram.")


def test_telegram(config: Dict):
    import asyncio
    from telegram import Bot
    async def _test():
        bot = Bot(token=config["telegram_token"])
        await bot.send_message(
            chat_id=config["telegram_chat_id"],
            text="✅ Toronto Rental Agent is configured correctly! Bot is working.",
        )
        logger.info("Test message sent successfully.")
    asyncio.run(_test())


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Toronto Rental Agent")
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--scrape-only", action="store_true")
    parser.add_argument("--notify-only", action="store_true")
    parser.add_argument("--test-telegram", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    store = Store(config)

    try:
        if args.test_telegram:
            test_telegram(config)
        elif args.notify_only:
            run_notify(config, store)
        elif args.scrape_only:
            run_scrape(config, store)
        else:
            new_listings = run_scrape(config, store)
            run_notify(config, store, new_listings)
    finally:
        store.close()


if __name__ == "__main__":
    main()

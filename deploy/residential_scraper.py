"""Kijiji scraper - run from phone (Termux) or laptop (residential IP).

This script is designed to be run from a device with a residential IP address.
It scrapes Kijiji (which blocks datacenter IPs) and sends matches directly
to Telegram, sharing the same seen.json dedup file as the main agent.

Usage:
  python3 deploy/kijiji_local.py
  python3 deploy/kijiji_local.py --config config.json

Setup:
  Termux:  bash deploy/termux_setup.sh setup
  Laptop:  pip install requests beautifulsoup4 lxml playwright playwright-stealth
           playwright install chromium
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("kijiji_local")


def load_config(path: str = "config.json") -> dict:
    p = Path(path)
    if not p.exists():
        # Try parent dir (if running from deploy/)
        p = Path(__file__).parent.parent / "config.json"
    if not p.exists():
        logger.error(f"config.json not found at {path}")
        sys.exit(1)
    with open(p) as f:
        return json.load(f)


def load_seen(config: dict) -> set:
    seen_file = Path(config.get("seen_file", "data/seen.json"))
    if seen_file.exists():
        try:
            with open(seen_file) as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_seen(config: dict, seen: set):
    seen_file = Path(config.get("seen_file", "data/seen.json"))
    seen_file.parent.mkdir(parents=True, exist_ok=True)
    with open(seen_file, "w") as f:
        json.dump(list(seen), f)


def scrape_kijiji_playwright(config: dict) -> list:
    """Scrape Kijiji using Playwright with stealth. Requires residential IP."""
    from playwright.sync_api import sync_playwright
    import re

    rent_limit = config["RENT_LIMIT"]
    listings = []

    SEARCH_URLS = [
        f"https://www.kijiji.ca/b-apartments-condos/city-of-toronto/c37l1700273?price=__-{rent_limit}",
        f"https://www.kijiji.ca/b-room-rental-roommate/city-of-toronto/c886l1700273?price=__-{rent_limit}",
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-CA",
            timezone_id="America/Toronto",
        )
        # Stealth patches
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-CA','en-US','en']});
            window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}, app: {}};
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (p) =>
                p.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                originalQuery(p);
        """)

        for url in SEARCH_URLS:
            logger.info(f"[kijiji] Fetching: {url}")
            page = ctx.new_page()
            try:
                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(3)
                content = page.content()

                if "captcha" in content.lower() or "robot" in content.lower():
                    logger.warning("[kijiji] Captcha detected - try again later or use cookie injection")
                    page.close()
                    continue

                # Try Next.js data first
                m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', content, re.DOTALL)
                if m:
                    items = _parse_nextdata(m.group(1), rent_limit)
                    listings.extend(items)
                    logger.info(f"[kijiji] Found {len(items)} from Next.js data")
                else:
                    # BS4 HTML fallback
                    items = _parse_html(content, rent_limit)
                    listings.extend(items)
                    logger.info(f"[kijiji] Found {len(items)} from HTML")

                page.close()
                time.sleep(2)
            except Exception as e:
                logger.error(f"[kijiji] Error: {e}")
                page.close()

        browser.close()
    return listings


def _parse_nextdata(json_str: str, rent_limit: int) -> list:
    import re
    import json as _json
    results = []
    try:
        d = _json.loads(json_str)
        # Walk to find ads array
        def find_ads(obj, depth=0):
            if depth > 8: return None
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ('ads', 'listings', 'adEntries') and isinstance(v, list) and v:
                        return v
                    r = find_ads(v, depth + 1)
                    if r: return r
            elif isinstance(obj, list):
                for item in obj[:3]:
                    r = find_ads(item, depth + 1)
                    if r: return r
            return None

        ads = find_ads(d) or []
        for ad in ads:
            if not isinstance(ad, dict): continue
            price_obj = ad.get('price', {})
            if isinstance(price_obj, dict):
                price_amount = price_obj.get('amount', 0)
            else:
                price_amount = 0
            # Try to parse price from string
            if isinstance(price_amount, str):
                nums = re.findall(r'[\d,]+', price_amount)
                price_amount = int(nums[0].replace(',', '')) if nums else 0
            price_amount = int(price_amount or 0)
            if price_amount > rent_limit or price_amount == 0:
                continue
            lid = str(ad.get('id', '') or ad.get('adId', ''))
            loc = ad.get('location', {}) or {}
            results.append({
                'id': f'kijiji_{lid}',
                'source': 'kijiji',
                'url': f"https://www.kijiji.ca{ad.get('seoUrl', '')}",
                'title': ad.get('title', ''),
                'price': price_amount,
                'address': loc.get('mapAddress', '') or f"{loc.get('areaName', '')}, Toronto, ON",
                'description': ad.get('description', ''),
                'image_url': (ad.get('images', [{}]) or [{}])[0].get('href', ''),
                'lat': loc.get('lat'),
                'lon': loc.get('lng'),
            })
    except Exception as e:
        logger.debug(f"[kijiji] nextdata parse error: {e}")
    return results


def _parse_html(html: str, rent_limit: int) -> list:
    from bs4 import BeautifulSoup
    import re
    soup = BeautifulSoup(html, 'lxml')
    results = []
    for card in soup.select('[data-listing-id],[class*=regularListing],[class*=topListing]'):
        try:
            lid = card.get('data-listing-id', '')
            link_el = card.select_one('a[href*="/v-"]')
            price_el = card.select_one('[class*=price]')
            title_el = card.select_one('[class*=title], h3, h2')
            img_el = card.select_one('img')
            if not link_el: continue
            link = 'https://www.kijiji.ca' + link_el['href'] if not link_el['href'].startswith('http') else link_el['href']
            price_text = price_el.get_text() if price_el else '0'
            nums = re.findall(r'[\d,]+', price_text)
            price = int(nums[0].replace(',', '')) if nums else 0
            if price > rent_limit or price == 0: continue
            if not lid:
                m = re.search(r'/(\d+)$', link)
                lid = m.group(1) if m else link[-10:]
            results.append({
                'id': f'kijiji_{lid}',
                'source': 'kijiji',
                'url': link,
                'title': title_el.get_text(strip=True) if title_el else '',
                'price': price,
                'address': 'Toronto, ON',
                'description': '',
                'image_url': img_el.get('src', '') if img_el else '',
                'lat': None, 'lon': None,
            })
        except Exception:
            pass
    return results


def run(config_path: str = "config.json"):
    config = load_config(config_path)
    seen = load_seen(config)
    Path("logs").mkdir(exist_ok=True)
    Path("data").mkdir(exist_ok=True)

    all_raw = []

    # Kijiji (Playwright, residential IP required)
    logger.info("Starting Kijiji scrape...")
    try:
        kijiji_listings = scrape_kijiji_playwright(config)
        logger.info(f"Kijiji: {len(kijiji_listings)} raw listings")
        all_raw.extend(kijiji_listings)
    except Exception as e:
        logger.error(f"Kijiji scrape failed: {e}")

    # Realtor.ca (requests, residential IP required - Incapsula blocked on datacenter)
    logger.info("Starting Realtor.ca scrape...")
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from scrapers.realtor_ca import RealtorCaScraper
        sc = RealtorCaScraper(config)
        realtor_listings = sc.scrape()
        logger.info(f"Realtor.ca: {len(realtor_listings)} raw listings")
        all_raw.extend(realtor_listings)
    except Exception as e:
        logger.error(f"Realtor.ca scrape failed: {e}")

    listings = all_raw
    logger.info(f"Total raw listings: {len(listings)}")

    # Import pipeline modules
    from geo import geocode, is_within_range, load_ttc_stations
    from classifier import classify_listing, passes_filter
    from scorer import score_listing
    from notifier import send_listings

    ttc = load_ttc_stations()
    anchor_coords = geocode(config.get('anchor_address', ''))
    anchor_lat = anchor_coords[0] if anchor_coords else None
    anchor_lon = anchor_coords[1] if anchor_coords else None

    qualifying = []
    for listing in listings:
        lid = listing.get('id', '')
        if not lid or lid in seen:
            continue
        # Geocode if needed
        if not listing.get('lat') or not listing.get('lon'):
            coords = geocode(listing.get('address', ''))
            if coords:
                listing['lat'], listing['lon'] = coords
        # Geo filter
        passes, dist_m, label = is_within_range(
            listing.get('lat'), listing.get('lon'),
            ttc, anchor_lat, anchor_lon,
            max_m=config.get('max_walking_m', 1200),
        )
        if not passes:
            seen.add(lid)
            continue
        listing['transit_dist_m'] = dist_m
        listing['nearest_transit'] = label
        # LLM classify
        clf = classify_listing(listing, config)
        listing['classification'] = clf
        if not passes_filter(clf, config):
            seen.add(lid)
            continue
        listing['score'] = score_listing(listing, config)
        qualifying.append(listing)
        seen.add(lid)
        logger.info(f"✅ [kijiji] {listing['title'][:50]} ${listing['price']}/mo score={listing['score']} | {label} {dist_m:.0f}m")

    save_seen(config, seen)
    logger.info(f"{len(qualifying)} qualifying listings from residential scrapers")

    # Export CSV (append to same file as main agent if it exists)
    if qualifying:
        import csv
        csv_path = Path(config.get("data_dir", "data")) / "listings.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "id", "source", "scraped_at", "price", "title", "address",
            "url", "image_url", "lat", "lon", "nearest_transit", "transit_dist_m",
            "private_room", "occupants", "cleanliness", "landlord_vibe",
            "scam_risk", "score", "reasoning",
        ]
        write_header = not csv_path.exists()
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            if write_header:
                writer.writeheader()
            for listing in qualifying:
                row = {**listing, **listing.get("classification", {})}
                row["scraped_at"] = __import__("datetime").datetime.utcnow().isoformat()
                writer.writerow({k: row.get(k, "") for k in fieldnames})
        logger.info(f"Appended {len(qualifying)} listings to {csv_path}")

    if qualifying:
        top_n = config.get('top_n_daily', 5)
        to_notify = sorted(qualifying, key=lambda x: x.get('score', 0), reverse=True)[:top_n]
        send_listings(to_notify, config)
    else:
        logger.info("No qualifying Kijiji listings this run.")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Kijiji local scraper (residential IP required)')
    parser.add_argument('--config', default='config.json')
    args = parser.parse_args()
    run(args.config)

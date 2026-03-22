"""Facebook Marketplace Toronto rental scraper.

Facebook aggressively blocks scrapers. Strategy:
1. Use public group RSS/feeds where available
2. Use Playwright in stealth mode (headless=False on local, headless=True on server)
3. Gracefully degrade - return empty list if blocked rather than crashing

Note: FB scraping is inherently fragile. This module does best-effort.
For production, consider manual Playwright cookie injection after login.
"""
import re
import logging
import json
import os
from typing import List, Dict, Any
from .base import BaseScraper

logger = logging.getLogger(__name__)

# Public Toronto rental Facebook groups (public posts only)
PUBLIC_GROUP_IDS = [
    "torontorentals",
    "1585082741744559",  # Toronto Rentals
    "359637554057965",   # Toronto Rooms & Apartments For Rent
]


class FacebookScraper(BaseScraper):
    name = "facebook"
    MARKETPLACE_URL = "https://www.facebook.com/marketplace/toronto/propertyrentals"

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        # Try Playwright approach
        try:
            pw_listings = self._scrape_playwright()
            listings.extend(pw_listings)
        except ImportError:
            logger.warning("[facebook] playwright not installed, skipping FB scrape")
        except Exception as e:
            logger.warning(f"[facebook] playwright scrape failed: {e}")

        logger.info(f"[facebook] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _scrape_playwright(self) -> List[Dict]:
        """Use Playwright with stealth to scrape Marketplace."""
        from playwright.sync_api import sync_playwright
        import time

        results = []
        cookies_file = self.config.get("fb_cookies_file", "data/fb_cookies.json")

        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 720},
                locale="en-CA",
            )

            # Inject saved cookies if present
            if os.path.exists(cookies_file):
                with open(cookies_file) as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                logger.info("[facebook] Loaded saved cookies")

            page = context.new_page()
            # Hide webdriver
            page.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            url = (
                f"{self.MARKETPLACE_URL}"
                f"?minPrice=0&maxPrice={self.rent_limit}"
                f"&latitude=43.7001&longitude=-79.4163&radius=30"
            )
            page.goto(url, timeout=30000)
            time.sleep(3)

            # Check if login wall appeared
            if "login" in page.url or page.locator("[data-testid='royal_login_form']").count() > 0:
                logger.warning("[facebook] Hit login wall - need saved cookies. See README for setup.")
                browser.close()
                return []

            # Scroll to load more
            for _ in range(3):
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2)

            # Extract listing data from page JSON blobs
            content = page.content()
            results = self._parse_marketplace_html(content)

            browser.close()
        return results

    def _parse_marketplace_html(self, html: str) -> List[Dict]:
        """Parse Facebook Marketplace listing data from embedded JSON."""
        results = []
        # FB embeds data in <script type="application/json"> tags
        patterns = [
            r'<script type="application/json" data-content-len[^>]*>(.*?)</script>',
            r'<script type="application/json"[^>]*>(.*?)</script>',
        ]
        for pattern in patterns:
            for blob in re.finditer(pattern, html, re.DOTALL):
                try:
                    data = json.loads(blob.group(1))
                    listings = self._extract_fb_listings(data)
                    results.extend(listings)
                except (json.JSONDecodeError, Exception):
                    continue
        return results

    def _extract_fb_listings(self, data) -> List[Dict]:
        """Recursively find Marketplace listing nodes in FB JSON."""
        results = []
        if isinstance(data, dict):
            # Look for marketplace listing shape
            listing_type = data.get("__typename", "")
            if "MarketplaceListing" in listing_type or "Listing" in listing_type:
                parsed = self._parse_fb_node(data)
                if parsed:
                    results.append(parsed)
                    return results
            for v in data.values():
                results.extend(self._extract_fb_listings(v))
        elif isinstance(data, list):
            for item in data:
                results.extend(self._extract_fb_listings(item))
        return results

    def _parse_fb_node(self, node: Dict) -> Dict | None:
        try:
            price_info = node.get("listing_price") or node.get("price") or {}
            if isinstance(price_info, dict):
                price = int(re.sub(r'[^\d]', '', str(price_info.get("amount", "0"))))
            else:
                price = int(re.sub(r'[^\d]', '', str(price_info)))
            if price > self.rent_limit or price == 0:
                return None
            lid = str(node.get("id", ""))
            location = node.get("location") or node.get("rentals_unit") or {}
            address = (
                location.get("reverse_geocode", {}).get("city_page", {}).get("display_name")
                or location.get("address")
                or "Toronto, ON"
            )
            primary_photo = node.get("primary_listing_photo") or node.get("cover_photo") or {}
            img = ""
            if isinstance(primary_photo, dict):
                img_data = primary_photo.get("image") or primary_photo
                img = img_data.get("uri") or img_data.get("url", "")
            title = (
                node.get("marketplace_listing_title")
                or node.get("title")
                or address
            )
            desc = node.get("redacted_description", {}).get("text") or node.get("description") or ""
            return {
                "id": f"facebook_{lid}",
                "url": f"https://www.facebook.com/marketplace/item/{lid}/",
                "title": title,
                "price": price,
                "address": address,
                "description": desc,
                "image_url": img,
                "lat": location.get("latitude"),
                "lon": location.get("longitude"),
            }
        except Exception as e:
            logger.debug(f"[facebook] node parse error: {e}")
            return None

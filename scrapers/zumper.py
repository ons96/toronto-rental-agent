"""Zumper Toronto scraper - parses inline JSON from HTML (listables/spotlight/featured)."""
import re
import json
import logging
from typing import List, Dict, Any, Optional
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE = "https://www.zumper.com"


class ZumperScraper(BaseScraper):
    name = "zumper"
    use_curl_cffi = True

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        for page in range(1, 4):
            url = f"{BASE}/apartments-for-rent/toronto-on?sort=matched&page={page}"
            resp = self._get(url)
            if not resp:
                break
            items = self._extract_listings(resp.text)
            if not items:
                break
            listings.extend(items)
            self._sleep()
        logger.info(f"[zumper] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _extract_listings(self, html: str) -> List[Dict]:
        all_items = []
        for key in ["listables", "spotlight", "featured"]:
            m = re.search(f'"' + key + r'":\s*(\[)', html)
            if not m:
                continue
            start = m.start(1)
            depth, end = 0, start
            for i, ch in enumerate(html[start:start + 500000]):
                if ch == "[": depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        end = start + i + 1
                        break
            try:
                arr = json.loads(html[start:end])
                for item in arr:
                    if isinstance(item, dict) and "listing_id" in item:
                        parsed = self._parse_item(item)
                        if parsed:
                            all_items.append(parsed)
            except Exception as e:
                logger.debug(f"[zumper] parse {key}: {e}")
        return all_items

    def _parse_item(self, item: Dict) -> Optional[Dict]:
        try:
            price = item.get("min_price") or item.get("max_price") or 0
            if not price or price > self.rent_limit:
                return None
            lid = str(item.get("listing_id", ""))
            url = item.get("url", "")
            if url and not url.startswith("http"):
                url = BASE + url
            img = ""
            image_ids = item.get("image_ids", [])
            if image_ids:
                img = f"https://images.zumper.com/listing-images/{image_ids[0]}/large.jpg"
            return {
                "id": f"zumper_{lid}",
                "url": url or f"{BASE}/apartments-for-rent/toronto-on/{lid}",
                "title": item.get("title") or item.get("building_name") or item.get("address", ""),
                "price": int(price),
                "address": item.get("address", "Toronto, ON"),
                "description": item.get("short_description") or "",
                "image_url": img,
                "lat": item.get("lat"),
                "lon": item.get("lng"),
                "bedrooms": item.get("min_bedrooms"),
                "bathrooms": item.get("min_bathrooms"),
            }
        except Exception as e:
            logger.debug(f"[zumper] item error: {e}")
            return None

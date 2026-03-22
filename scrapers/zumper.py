"""Zumper Toronto rental scraper - uses their internal JSON API."""
import re
import logging
from typing import List, Dict, Any
from .base import BaseScraper

logger = logging.getLogger(__name__)


class ZumperScraper(BaseScraper):
    name = "zumper"
    # Zumper exposes a public search API used by their own frontend
    API_URL = "https://www.zumper.com/api/t/1/listings"

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        params = {
            "accepts_pets": "false",
            "cats": "false",
            "dogs": "false",
            "order_by": "ranked",
            "page": 1,
            "rent_max": self.rent_limit,
            "search": "Toronto, ON",
            "min_latitude": 43.58,
            "max_latitude": 43.86,
            "min_longitude": -79.64,
            "max_longitude": -79.11,
        }
        for page in range(1, 4):  # 3 pages
            params["page"] = page
            resp = self._get(
                self.API_URL,
                params=params,
                headers={
                    **self.session.headers,
                    "Accept": "application/json",
                    "Referer": "https://www.zumper.com/apartments-for-rent/toronto-on",
                    "X-Zumper-XZ-Token": self._get_xz_token(),
                },
            )
            if not resp:
                break
            try:
                data = resp.json()
            except Exception:
                break
            items = data if isinstance(data, list) else data.get("listings", data.get("data", []))
            if not items:
                break
            for item in items:
                parsed = self._parse_item(item)
                if parsed:
                    listings.append(parsed)
            self._sleep()
        logger.info(f"[zumper] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _get_xz_token(self) -> str:
        """Fetch XZ token from Zumper homepage (needed for API auth)."""
        try:
            resp = self.session.get(
                "https://www.zumper.com/apartments-for-rent/toronto-on",
                timeout=10,
            )
            m = re.search(r'"xzToken"\s*:\s*"([^"]+)"', resp.text)
            if m:
                return m.group(1)
            # fallback: look in meta tags
            m2 = re.search(r'zumper-xz-token.*?content="([^"]+)"', resp.text)
            if m2:
                return m2.group(1)
        except Exception:
            pass
        return ""

    def _parse_item(self, item: Dict) -> Dict | None:
        try:
            price = item.get("price") or item.get("rent") or 0
            if isinstance(price, (list, tuple)):
                price = price[0] if price else 0
            price = int(price)
            if price > self.rent_limit or price == 0:
                return None
            lid = str(item.get("id", ""))
            photos = item.get("photos") or item.get("images") or []
            img = photos[0] if photos and isinstance(photos[0], str) else ""
            if isinstance(img, dict):
                img = img.get("url", img.get("src", ""))
            location = item.get("location") or {}
            address = (
                item.get("address")
                or f"{location.get('street_address', '')} {location.get('city', 'Toronto')}"
            ).strip()
            return {
                "id": f"zumper_{lid}",
                "url": f"https://www.zumper.com/apartments-for-rent/toronto-on/{lid}",
                "title": item.get("name") or item.get("title") or address,
                "price": price,
                "address": address,
                "description": item.get("summary") or item.get("description") or "",
                "image_url": img,
                "lat": location.get("latitude") or item.get("latitude"),
                "lon": location.get("longitude") or item.get("longitude"),
                "bedrooms": item.get("bedrooms", ""),
                "bathrooms": item.get("bathrooms", ""),
            }
        except Exception as e:
            logger.debug(f"[zumper] item parse error: {e}")
            return None

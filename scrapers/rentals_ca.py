"""Rentals.ca Toronto scraper - parses App.store.search inline JSON (edges[].node)."""
import re
import json
import logging
from typing import List, Dict, Any, Optional
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE = "https://rentals.ca"


class RentalsCaScraper(BaseScraper):
    name = "rentals_ca"
    use_curl_cffi = True

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        # rentals.ca uses cursor-based pagination via hasNextPage/endCursor
        # For simplicity fetch first 3 pages via offset URL params
        for page in range(1, 4):
            url = f"{BASE}/toronto?type=1,2,3,4&price_max={self.rent_limit}&p={page}"
            resp = self._get(url)
            if not resp:
                break
            items = self._extract_listings(resp.text)
            if not items:
                break
            listings.extend(items)
            self._sleep()
        logger.info(f"[rentals_ca] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _extract_listings(self, html: str) -> List[Dict]:
        m = re.search(r'response:\s*(\{)', html)
        if not m:
            return []
        start = m.start(1)
        depth, end = 0, start
        for i, ch in enumerate(html[start:start + 500000]):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = start + i + 1
                    break
        try:
            data = json.loads(html[start:end])
            edges = data.get("data", {}).get("edges", [])
            results = []
            for edge in edges:
                node = edge.get("node", {})
                parsed = self._parse_node(node)
                if parsed:
                    results.append(parsed)
            return results
        except json.JSONDecodeError as e:
            logger.debug(f"[rentals_ca] JSON error: {e}")
            return []

    def _parse_node(self, node: Dict) -> Optional[Dict]:
        try:
            # Price from floorPlans (take minimum)
            floor_plans = node.get("floorPlans", [])
            rent_range = node.get("rentRange", [])
            if floor_plans:
                prices = [fp.get("rent", 0) for fp in floor_plans if fp.get("rent")]
                price = int(min(prices)) if prices else 0
            elif rent_range:
                price = int(rent_range[0])
            else:
                price = 0
            if price == 0 or price > self.rent_limit:
                return None

            lid = node.get("id", node.get("path", ""))
            path = node.get("path", "")
            url = f"{BASE}/{path}" if path else ""

            # Address
            addr_obj = node.get("address", {})
            if isinstance(addr_obj, dict):
                street = addr_obj.get("street", "")
                city = addr_obj.get("city", {}).get("cityName", "Toronto") if isinstance(addr_obj.get("city"), dict) else "Toronto"
                address = f"{street}, {city}".strip(", ")
            else:
                address = str(addr_obj) or "Toronto, ON"

            # Coords from rentalListingLocation [lon, lat]
            loc = node.get("rentalListingLocation", [])
            lat = loc[1] if len(loc) >= 2 else None
            lon = loc[0] if len(loc) >= 2 else None

            # Image
            images = node.get("images", [])
            img = ""
            if images:
                scales = images[0].get("scales", [])
                for s in scales:
                    if s.get("name") == "large":
                        img = s.get("url", "")
                        break
                if not img and scales:
                    img = scales[0].get("url", "")

            name = node.get("rentalListingName") or node.get("name") or address

            return {
                "id": f"rentals_ca_{str(lid).replace('/', '_')}",
                "url": url,
                "title": name,
                "price": price,
                "address": address,
                "description": "",
                "image_url": img,
                "lat": lat,
                "lon": lon,
                "bedrooms": "",
                "bathrooms": "",
            }
        except Exception as e:
            logger.debug(f"[rentals_ca] node error: {e}")
            return None

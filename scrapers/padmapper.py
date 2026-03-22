"""Padmapper Toronto scraper - uses their GraphQL API."""
import re
import logging
import json
from typing import List, Dict, Any
from .base import BaseScraper

logger = logging.getLogger(__name__)

GRAPHQL_QUERY = """
query GetListings($filters: ListingFilters!) {
  listings(filters: $filters) {
    id
    title
    price
    address
    lat
    lng
    photoUrls
    description
    bedrooms
    bathrooms
    source
    sourceUrl
  }
}
"""


class PadmapperScraper(BaseScraper):
    name = "padmapper"
    GRAPHQL_URL = "https://www.padmapper.com/api/t/1/graphql"
    JSON_API = "https://www.padmapper.com/api/t/1/listings"
    WEB_URL = "https://www.padmapper.com"

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        # Try JSON API (same backend as Zumper)
        results = self._scrape_json_api()
        if not results:
            results = self._scrape_web()
        listings.extend(results)
        logger.info(f"[padmapper] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _scrape_json_api(self) -> List[Dict]:
        """Padmapper shares backend infra with Zumper."""
        params = {
            "order_by": "ranked",
            "page": 1,
            "rent_max": self.rent_limit,
            "box": "43.58,-79.64,43.86,-79.11",  # Toronto bounding box
        }
        results = []
        for page in range(1, 4):
            params["page"] = page
            resp = self._get(
                self.JSON_API,
                params=params,
                headers={
                    **self.session.headers,
                    "Accept": "application/json",
                    "Referer": "https://www.padmapper.com/apartments/toronto-on",
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
                    results.append(parsed)
            self._sleep()
        return results

    def _scrape_web(self) -> List[Dict]:
        url = f"{self.WEB_URL}/apartments/toronto-on?rent-max={self.rent_limit}"
        resp = self._get(url)
        if not resp:
            return []
        results = []
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                props = data.get("props", {}).get("pageProps", {})
                items = props.get("listings") or props.get("initialListings") or []
                for item in items:
                    parsed = self._parse_item(item)
                    if parsed:
                        results.append(parsed)
            except json.JSONDecodeError:
                pass
        return results

    def _parse_item(self, item: Dict) -> Dict | None:
        try:
            price = item.get("price") or item.get("rent") or 0
            if isinstance(price, (list, tuple)):
                price = price[0] if price else 0
            price = int(price)
            if price > self.rent_limit or price == 0:
                return None
            lid = str(item.get("id", ""))
            photos = item.get("photoUrls") or item.get("photos") or item.get("images") or []
            img = photos[0] if photos and isinstance(photos[0], str) else ""
            source_url = item.get("sourceUrl") or item.get("url") or f"{self.WEB_URL}/apartments/toronto-on/{lid}"
            return {
                "id": f"padmapper_{lid}",
                "url": source_url,
                "title": item.get("title") or item.get("name") or item.get("address", ""),
                "price": price,
                "address": item.get("address") or "Toronto, ON",
                "description": item.get("description") or item.get("summary") or "",
                "image_url": img,
                "lat": item.get("lat") or item.get("latitude"),
                "lon": item.get("lng") or item.get("longitude"),
                "bedrooms": item.get("bedrooms"),
                "bathrooms": item.get("bathrooms"),
            }
        except Exception as e:
            logger.debug(f"[padmapper] parse error: {e}")
            return None

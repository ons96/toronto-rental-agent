"""liv.rent Toronto scraper - uses their GraphQL/REST API."""
import re
import logging
import json
from typing import List, Dict, Any
from .base import BaseScraper

logger = logging.getLogger(__name__)


class LivRentScraper(BaseScraper):
    name = "liv_rent"
    # liv.rent uses a public REST API
    API_URL = "https://api.liv.rent/api/v2/listings/search"
    WEB_URL = "https://liv.rent"

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        # Try REST API first
        api_results = self._scrape_api()
        if api_results:
            listings.extend(api_results)
        else:
            # Fallback: scrape web with embedded JSON
            listings.extend(self._scrape_web())
        logger.info(f"[liv_rent] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _scrape_api(self) -> List[Dict]:
        payload = {
            "city": "toronto",
            "province": "on",
            "country": "ca",
            "price_max": self.rent_limit,
            "limit": 50,
            "offset": 0,
            "listing_type": ["private_room", "entire_place"],
        }
        results = []
        for offset in [0, 50, 100]:
            payload["offset"] = offset
            resp = self._get(
                self.API_URL,
                headers={
                    **self.session.headers,
                    "Accept": "application/json",
                    "Origin": self.WEB_URL,
                    "Referer": f"{self.WEB_URL}/en/rooms-for-rent/toronto",
                },
            )
            # API may require POST
            if not resp or resp.status_code != 200:
                try:
                    resp2 = self.session.post(
                        self.API_URL,
                        json=payload,
                        timeout=15,
                        headers={
                            "Accept": "application/json",
                            "Content-Type": "application/json",
                            "Origin": self.WEB_URL,
                        },
                    )
                    resp2.raise_for_status()
                    resp = resp2
                except Exception:
                    break
            try:
                data = resp.json()
            except Exception:
                break
            items = (
                data.get("listings")
                or data.get("data", {}).get("listings", [])
                or data if isinstance(data, list) else []
            )
            if not items:
                break
            for item in items:
                parsed = self._parse_item(item)
                if parsed:
                    results.append(parsed)
            self._sleep()
        return results

    def _scrape_web(self) -> List[Dict]:
        url = f"{self.WEB_URL}/en/rooms-for-rent/toronto?max_price={self.rent_limit}"
        resp = self._get(url)
        if not resp:
            return []
        results = []
        # Extract __NUXT__ or __NEXT_DATA__
        for pattern in [
            r'window\.__NUXT__\s*=\s*(\{.*?\});\s*</script>',
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        ]:
            m = re.search(pattern, resp.text, re.DOTALL)
            if m:
                try:
                    raw = json.loads(m.group(1))
                    # Try to find listings array anywhere in the structure
                    listings_arr = self._deep_find_list(raw, "listings")
                    for item in (listings_arr or []):
                        parsed = self._parse_item(item)
                        if parsed:
                            results.append(parsed)
                    if results:
                        return results
                except json.JSONDecodeError:
                    pass
        return results

    def _parse_item(self, item: Dict) -> Dict | None:
        try:
            price = int(
                item.get("price")
                or item.get("rent")
                or item.get("monthly_rent", 0)
            )
            if price > self.rent_limit or price == 0:
                return None
            lid = str(item.get("id") or item.get("listing_id") or item.get("uuid", ""))
            photos = item.get("photos") or item.get("images") or item.get("media") or []
            img = ""
            if photos:
                p = photos[0]
                img = p if isinstance(p, str) else p.get("url", p.get("src", p.get("path", "")))
            address = (
                item.get("address")
                or item.get("street_address")
                or "Toronto, ON"
            )
            loc = item.get("location") or item.get("coordinates") or {}
            return {
                "id": f"livrent_{lid}",
                "url": f"{self.WEB_URL}/en/rooms-for-rent/toronto/{lid}",
                "title": item.get("title") or item.get("name") or address,
                "price": price,
                "address": address,
                "description": item.get("description") or item.get("details") or "",
                "image_url": img,
                "lat": loc.get("lat") or loc.get("latitude") or item.get("lat"),
                "lon": loc.get("lng") or loc.get("longitude") or item.get("lng"),
                "bedrooms": item.get("bedrooms") or item.get("num_bedrooms"),
                "bathrooms": item.get("bathrooms") or item.get("num_bathrooms"),
            }
        except Exception as e:
            logger.debug(f"[liv_rent] parse error: {e}")
            return None

    @staticmethod
    def _deep_find_list(obj, key: str, depth: int = 0) -> list | None:
        if depth > 6:
            return None
        if isinstance(obj, dict):
            if key in obj and isinstance(obj[key], list):
                return obj[key]
            for v in obj.values():
                result = LivRentScraper._deep_find_list(v, key, depth + 1)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj[:5]:
                result = LivRentScraper._deep_find_list(item, key, depth + 1)
                if result:
                    return result
        return None

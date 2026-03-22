"""Condos.ca Toronto rental scraper."""
import re
import logging
import json
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)


class CondosCaScraper(BaseScraper):
    name = "condos_ca"
    API_URL = "https://api.condos.ca/v1/listings"
    WEB_URL = "https://www.condos.ca"
    SEARCH_URL = "https://www.condos.ca/toronto-apartments-for-rent"

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        results = self._scrape_api()
        if not results:
            results = self._scrape_web()
        listings.extend(results)
        logger.info(f"[condos_ca] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _scrape_api(self) -> List[Dict]:
        params = {
            "for": "rent",
            "city": "Toronto",
            "price_max": self.rent_limit,
            "page": 1,
            "per_page": 40,
        }
        results = []
        for page in range(1, 4):
            params["page"] = page
            resp = self._get(
                self.API_URL,
                params=params,
                headers={**self.session.headers, "Accept": "application/json"},
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
        url = f"{self.SEARCH_URL}?price_max={self.rent_limit}"
        resp = self._get(url)
        if not resp:
            return []
        results = []
        soup = BeautifulSoup(resp.text, "lxml")
        # Try embedded JSON first
        for script in soup.find_all("script", type="application/json"):
            try:
                data = json.loads(script.string or "{}")
                items = self._deep_find_list(data, ["listings", "properties", "results"])
                for item in (items or []):
                    parsed = self._parse_item(item)
                    if parsed:
                        results.append(parsed)
                if results:
                    return results
            except Exception:
                pass
        # HTML fallback
        for card in soup.select("[class*='listing'], [class*='property'], [class*='card']"):
            try:
                link_el = card.select_one("a[href]")
                price_el = card.select_one("[class*='price'], [class*='rent']")
                if not link_el or not price_el:
                    continue
                price = self._parse_price(price_el.get_text())
                if price > self.rent_limit or price == 0:
                    continue
                link = link_el["href"]
                if not link.startswith("http"):
                    link = self.WEB_URL + link
                img_el = card.select_one("img")
                img = img_el.get("src", "") if img_el else ""
                addr_el = card.select_one("[class*='address'], [class*='location']")
                address = addr_el.get_text(strip=True) if addr_el else "Toronto, ON"
                m = re.search(r'/([^/?]+)(?:\?|$)', link)
                lid = m.group(1) if m else link[-20:]
                results.append({
                    "id": f"condos_ca_{lid}",
                    "url": link,
                    "title": link_el.get_text(strip=True) or address,
                    "price": price,
                    "address": address,
                    "description": "",
                    "image_url": img,
                })
            except Exception:
                pass
        return results

    def _parse_item(self, item: Dict) -> Dict | None:
        try:
            price = int(item.get("price") or item.get("rent") or item.get("lease_price", 0))
            if price > self.rent_limit or price == 0:
                return None
            lid = str(item.get("id") or item.get("listing_id") or item.get("mls_id", ""))
            photos = item.get("photos") or item.get("images") or []
            img = ""
            if photos:
                p = photos[0]
                img = p if isinstance(p, str) else p.get("url", p.get("src", ""))
            address = item.get("address") or item.get("street_address") or "Toronto, ON"
            slug = item.get("slug") or item.get("url") or lid
            url = slug if slug.startswith("http") else f"{self.WEB_URL}/{slug}"
            return {
                "id": f"condos_ca_{lid}",
                "url": url,
                "title": item.get("title") or item.get("name") or address,
                "price": price,
                "address": address,
                "description": item.get("description") or "",
                "image_url": img,
                "lat": item.get("latitude") or item.get("lat"),
                "lon": item.get("longitude") or item.get("lon"),
                "bedrooms": item.get("bedrooms"),
                "bathrooms": item.get("bathrooms"),
            }
        except Exception as e:
            logger.debug(f"[condos_ca] parse error: {e}")
            return None

    @staticmethod
    def _deep_find_list(obj, keys: List[str], depth: int = 0):
        if depth > 5:
            return None
        if isinstance(obj, dict):
            for key in keys:
                if key in obj and isinstance(obj[key], list) and obj[key]:
                    return obj[key]
            for v in obj.values():
                r = CondosCaScraper._deep_find_list(v, keys, depth + 1)
                if r:
                    return r
        elif isinstance(obj, list):
            for item in obj[:3]:
                r = CondosCaScraper._deep_find_list(item, keys, depth + 1)
                if r:
                    return r
        return None

    @staticmethod
    def _parse_price(text: str) -> int:
        nums = re.findall(r'[\d,]+', str(text))
        if nums:
            try:
                return int(nums[0].replace(",", ""))
            except ValueError:
                pass
        return 0

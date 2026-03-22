"""Craigslist Toronto rental scraper - HTML search."""
import re
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE = "https://toronto.craigslist.org"


class CraigslistScraper(BaseScraper):
    name = "craigslist"
    use_curl_cffi = False

    SEARCH_PATHS = [
        "/search/apa",   # apartments
        "/search/roo",   # rooms
        "/search/sub",   # sublets
    ]

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        for path in self.SEARCH_PATHS:
            url = f"{BASE}{path}?max_price={self.rent_limit}&availabilityMode=0"
            resp = self._get(url)
            if not resp:
                continue
            items = self._parse_page(resp.text)
            listings.extend(items)
            self._sleep()
        # Fetch coords from detail pages (rate limited: 1 req/sec)
        listings = self._enrich_coords(listings)
        logger.info(f"[craigslist] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _enrich_coords(self, listings: List[Dict]) -> List[Dict]:
        """Fetch lat/lon from detail pages. Max 80 pages to stay fast."""
        enriched = []
        for listing in listings[:80]:  # Cap at 80 detail page fetches per run
            url = listing.get("url", "")
            if not url:
                enriched.append(listing)
                continue
            try:
                resp = self._get(url)
                if resp:
                    lat, lon = self._extract_coords(resp.text)
                    if lat and lon:
                        listing["lat"] = lat
                        listing["lon"] = lon
                        # Also extract neighborhood from body
                        addr = self._extract_neighborhood(resp.text)
                        if addr:
                            listing["address"] = addr
                time.sleep(0.8)  # Respect CL rate limit
            except Exception as e:
                logger.debug(f"[craigslist] detail fetch error: {e}")
            enriched.append(listing)
        # Append remaining without coords
        enriched.extend(listings[80:])
        return enriched

    @staticmethod
    def _extract_coords(html: str) -> Tuple[Optional[float], Optional[float]]:
        import re
        lat_m = re.search(r'data-latitude="([^"]+)"', html)
        lon_m = re.search(r'data-longitude="([^"]+)"', html)
        if lat_m and lon_m:
            try:
                return float(lat_m.group(1)), float(lon_m.group(1))
            except ValueError:
                pass
        return None, None

    @staticmethod
    def _extract_neighborhood(html: str) -> str:
        """Extract neighborhood/area from CL posting."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        # CL shows neighborhood in () after title e.g. "Room for rent (Annex)"
        title_el = soup.select_one("#titletextonly, span.postingtitletext")
        if title_el:
            import re
            m = re.search(r'\(([^)]+)\)', title_el.get_text())
            if m:
                return f"{m.group(1)}, Toronto, ON"
        return ""

    def _parse_page(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for li in soup.select("li[class*=result], li.cl-static-search-result"):
            try:
                a = li.select_one("a[href]")
                if not a:
                    continue
                link = a["href"]
                if not link.startswith("http"):
                    link = BASE + link
                title = a.get_text(strip=True) or li.get("title", "")
                price_el = li.select_one(".priceinfo, .price, [class*=price]")
                price = self._parse_price(price_el.get_text() if price_el else "0")
                if price > self.rent_limit or price == 0:
                    continue
                img_el = li.select_one("img")
                img = img_el.get("src", "") if img_el else ""
                m = re.search(r'/([\d]+)\.html', link)
                lid = m.group(1) if m else re.sub(r'\W', '_', link[-20:])
                results.append({
                    "id": f"craigslist_{lid}",
                    "url": link,
                    "title": title,
                    "price": price,
                    "address": "Toronto, ON",
                    "description": li.get("title", ""),
                    "image_url": img,
                })
            except Exception as e:
                logger.debug(f"[craigslist] parse error: {e}")
        return results

    @staticmethod
    def _parse_price(text: str) -> int:
        nums = re.findall(r'[\d,]+', str(text))
        if nums:
            try:
                return int(nums[0].replace(",", ""))
            except ValueError:
                pass
        return 0

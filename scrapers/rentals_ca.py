"""Rentals.ca Toronto scraper."""
import re
import logging
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)


class RentalsCaScraper(BaseScraper):
    name = "rentals_ca"
    base_url = "https://rentals.ca"
    SEARCH_URL = "https://rentals.ca/toronto"

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        for page in range(1, 4):
            url = f"{self.SEARCH_URL}?type=1,2,3,4&price_max={self.rent_limit}&p={page}"
            resp = self._get(url)
            if not resp:
                break
            # Try JSON embedded in page first (faster)
            items = self._extract_json_data(resp.text)
            if not items:
                items = self._parse_html(resp.text)
            if not items:
                break
            listings.extend(items)
            self._sleep()
        logger.info(f"[rentals_ca] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _extract_json_data(self, html: str) -> List[Dict]:
        """Rentals.ca embeds listing data in __NEXT_DATA__ or window.__data."""
        import json
        results = []
        # Try Next.js data
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                # Traverse to listings
                props = data.get("props", {}).get("pageProps", {})
                raw_listings = (
                    props.get("listings")
                    or props.get("searchResults", {}).get("listings", [])
                )
                if raw_listings:
                    for item in raw_listings:
                        parsed = self._parse_json_item(item)
                        if parsed:
                            results.append(parsed)
                    return results
            except json.JSONDecodeError:
                pass
        return []

    def _parse_json_item(self, item: Dict) -> Dict | None:
        try:
            price = int(item.get("price") or item.get("rent") or 0)
            if price > self.rent_limit or price == 0:
                return None
            lid = str(item.get("id", "") or item.get("listing_id", ""))
            slug = item.get("slug") or item.get("url_slug") or lid
            photos = item.get("photos") or item.get("images") or []
            img = ""
            if photos:
                first = photos[0]
                img = first if isinstance(first, str) else first.get("url", first.get("src", ""))
            address = (
                item.get("address")
                or item.get("street_address")
                or item.get("location", {}).get("address", "Toronto, ON")
            )
            return {
                "id": f"rentals_ca_{lid}",
                "url": f"{self.base_url}/toronto/{slug}",
                "title": item.get("title") or item.get("name") or address,
                "price": price,
                "address": address,
                "description": item.get("description") or item.get("summary") or "",
                "image_url": img,
                "lat": item.get("latitude") or item.get("lat"),
                "lon": item.get("longitude") or item.get("lon"),
                "bedrooms": item.get("bedrooms") or item.get("num_bedrooms"),
                "bathrooms": item.get("bathrooms") or item.get("num_bathrooms"),
            }
        except Exception as e:
            logger.debug(f"[rentals_ca] json item error: {e}")
            return None

    def _parse_html(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for card in soup.select("[class*='listing-card'], [class*='property-card'], article"):
            try:
                link_el = card.select_one("a[href]")
                price_el = card.select_one("[class*='price'], [class*='rent']")
                title_el = card.select_one("h2, h3, [class*='title']")
                addr_el = card.select_one("[class*='address'], [class*='location']")
                img_el = card.select_one("img")

                link = link_el["href"] if link_el else ""
                if link and not link.startswith("http"):
                    link = self.base_url + link
                price_text = price_el.get_text() if price_el else "0"
                price = self._parse_price(price_text)
                if price > self.rent_limit or price == 0:
                    continue
                title = title_el.get_text(strip=True) if title_el else ""
                address = addr_el.get_text(strip=True) if addr_el else "Toronto, ON"
                img = ""
                if img_el:
                    img = img_el.get("src") or img_el.get("data-src") or ""
                m = re.search(r'/([^/]+)$', link)
                lid = m.group(1) if m else link
                results.append({
                    "id": f"rentals_ca_{lid}",
                    "url": link,
                    "title": title,
                    "price": price,
                    "address": address,
                    "description": "",
                    "image_url": img,
                })
            except Exception as e:
                logger.debug(f"[rentals_ca] html parse error: {e}")
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

"""ViewIt.ca Toronto scraper."""
import re
import logging
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE = "https://www.viewit.ca"


class ViewitScraper(BaseScraper):
    name = "viewit"
    use_curl_cffi = False

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        for page in range(1, 4):
            resp = self._get(
                f"{BASE}/vwListings.aspx",
                params={"city": "Toronto", "mnRent": 0, "mxRent": self.rent_limit, "pg": page},
            )
            if not resp:
                break
            items = self._parse_page(resp.text)
            if not items:
                break
            listings.extend(items)
            self._sleep()
        logger.info(f"[viewit] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _parse_page(self, html: str) -> List[Dict]:
        soup = BeautifulSoup(html, "lxml")
        results = []
        for card in soup.select(".featuredListing"):
            try:
                # href is on the <a> itself (the card IS the <a>)
                href = card.get("href", "")
                if not href:
                    a = card.select_one("a[href]")
                    href = a["href"] if a else ""
                if href and not href.startswith("http"):
                    url = f"{BASE}/{href.lstrip('/')}"
                else:
                    url = href

                img_el = card.select_one("img")
                alt = img_el.get("alt", "") if img_el else ""
                # Address from img alt: "Rental High-rise 1275 Danforth Rd, Scarborough, ON"
                address = re.sub(r'^Rental[^,]+,?\s*', '', alt).strip() if alt else "Toronto, ON"
                img_src = img_el.get("src", "") if img_el else ""
                if img_src and img_src.startswith("//"):
                    img_src = "https:" + img_src

                name_el = card.select_one(".featuredListing-name")
                title = name_el.get_text(strip=True) if name_el else address

                price_el = card.select_one(".featuredListing-price")
                price = self._parse_price(price_el.get_text() if price_el else "0")
                if price > self.rent_limit or price == 0:
                    continue

                # listing ID from href (e.g. 'B3856')
                lid = re.sub(r'\W', '_', href) if href else title[:20].replace(' ', '_')

                results.append({
                    "id": f"viewit_{lid}",
                    "url": url,
                    "title": title,
                    "price": price,
                    "address": address,
                    "description": alt,
                    "image_url": img_src,
                })
            except Exception as e:
                logger.debug(f"[viewit] parse error: {e}")
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

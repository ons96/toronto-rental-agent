"""ViewIt.ca Toronto scraper."""
import re
import logging
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)


class ViewitScraper(BaseScraper):
    name = "viewit"
    base_url = "https://www.viewit.ca"
    SEARCH_URL = "https://www.viewit.ca/vwListings.aspx"

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        params = {
            "city": "Toronto",
            "mnRent": 0,
            "mxRent": self.rent_limit,
            "pg": 1,
        }
        for page in range(1, 4):
            params["pg"] = page
            resp = self._get(self.SEARCH_URL, params=params)
            if not resp:
                break
            soup = BeautifulSoup(resp.text, "lxml")
            items = self._parse_page(soup)
            if not items:
                break
            listings.extend(items)
            self._sleep()
        logger.info(f"[viewit] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _parse_page(self, soup: BeautifulSoup) -> List[Dict]:
        results = []
        for card in soup.select("[class*='listing'], [id*='listing'], .propBox, .unitRow, tr[id]"):
            try:
                link_el = card.select_one("a[href]")
                price_el = card.select_one("[class*='price'], [class*='rent'], td.rent")
                addr_el = card.select_one("[class*='address'], [class*='addr'], td.address")
                img_el = card.select_one("img")

                if not link_el:
                    continue
                link = link_el.get("href", "")
                if not link.startswith("http"):
                    link = self.base_url + "/" + link.lstrip("/")
                price = self._parse_price(price_el.get_text() if price_el else "0")
                if price > self.rent_limit or price == 0:
                    continue
                address = addr_el.get_text(strip=True) if addr_el else "Toronto, ON"
                img = ""
                if img_el:
                    img = img_el.get("src") or img_el.get("data-src") or ""
                    if img and not img.startswith("http"):
                        img = self.base_url + img
                m = re.search(r'[?&]id=([^&]+)', link)
                lid = m.group(1) if m else re.sub(r'[^\w]', '_', link[-20:])
                results.append({
                    "id": f"viewit_{lid}",
                    "url": link,
                    "title": link_el.get_text(strip=True),
                    "price": price,
                    "address": address,
                    "description": "",
                    "image_url": img,
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

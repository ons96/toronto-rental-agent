"""Kijiji Toronto rental scraper."""
import re
import logging
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)


class KijijiScraper(BaseScraper):
    name = "kijiji"
    base_url = "https://www.kijiji.ca"

    # Kijiji category IDs for Toronto rentals
    CATEGORY_URLS = [
        "/b-apartments-condos/city-of-toronto/c37l1700273",
        "/b-room-rental-roommate/city-of-toronto/c886l1700273",
        "/b-house-rental/city-of-toronto/c43l1700273",
    ]

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        for path in self.CATEGORY_URLS:
            page = 1
            while page <= 3:  # max 3 pages per category
                url = f"{self.base_url}{path}?price=__-{self.rent_limit}&page={page}"
                resp = self._get(url, headers={
                    **self.session.headers,
                    "Referer": self.base_url,
                })
                if not resp:
                    break
                soup = BeautifulSoup(resp.text, "lxml")
                items = self._parse_page(soup)
                if not items:
                    break
                listings.extend(items)
                # Check if next page exists
                next_btn = soup.select_one("[data-testid='pagination-next-link'], a.pagination-next")
                if not next_btn:
                    break
                page += 1
                self._sleep()
        logger.info(f"[kijiji] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _parse_page(self, soup: BeautifulSoup) -> List[Dict]:
        results = []
        # Kijiji uses data-listing-id attributes
        cards = soup.select("[data-listing-id], li[class*='search-item']")
        for card in cards:
            try:
                listing_id = card.get("data-listing-id", "")
                title_el = card.select_one("[class*='title'], h3, h2")
                price_el = card.select_one("[class*='price']")
                loc_el = card.select_one("[class*='location'], [class*='address']")
                desc_el = card.select_one("[class*='description'], p")
                link_el = card.select_one("a[href*='/v-']")
                img_el = card.select_one("img")

                title = title_el.get_text(strip=True) if title_el else ""
                price_text = price_el.get_text(strip=True) if price_el else "0"
                price = self._parse_price(price_text)
                address = loc_el.get_text(strip=True) if loc_el else "Toronto"
                desc = desc_el.get_text(strip=True) if desc_el else ""
                link = self.base_url + link_el["href"] if link_el else ""
                img = img_el.get("src") or img_el.get("data-src", "") if img_el else ""

                if not listing_id and link:
                    m = re.search(r'/(\d+)$', link)
                    listing_id = m.group(1) if m else link

                if price > self.rent_limit or price == 0:
                    continue

                results.append({
                    "id": f"kijiji_{listing_id}",
                    "url": link,
                    "title": title,
                    "price": price,
                    "address": address,
                    "description": desc,
                    "image_url": img,
                })
            except Exception as e:
                logger.debug(f"[kijiji] parse error: {e}")
        return results

    @staticmethod
    def _parse_price(text: str) -> int:
        nums = re.findall(r'[\d,]+', text.replace(" ", ""))
        if nums:
            try:
                return int(nums[0].replace(",", ""))
            except ValueError:
                pass
        return 0

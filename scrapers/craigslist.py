"""Craigslist Toronto rental scraper via RSS + HTML fallback."""
import re
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from .base import BaseScraper

logger = logging.getLogger(__name__)


class CraigslistScraper(BaseScraper):
    name = "craigslist"
    base_url = "https://toronto.craigslist.org"

    # RSS feeds - most reliable for Craigslist
    RSS_FEEDS = [
        "/search/tor/apa.rss",  # apartments
        "/search/tor/roo.rss",  # rooms
        "/search/tor/sub.rss",  # sublets
    ]

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        for feed_path in self.RSS_FEEDS:
            url = f"{self.base_url}{feed_path}?max_price={self.rent_limit}&availabilityMode=0"
            resp = self._get(url)
            if not resp:
                # Fallback to HTML
                listings.extend(self._scrape_html(feed_path.replace('.rss', '')))
                continue
            items = self._parse_rss(resp.text)
            listings.extend(items)
            self._sleep()
        logger.info(f"[craigslist] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _parse_rss(self, xml_text: str) -> List[Dict]:
        results = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"cl": "http://www.craigslist.org/about/basics"}
            channel = root.find("channel")
            if channel is None:
                return []
            for item in channel.findall("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                desc_html = item.findtext("description") or ""
                price_el = item.find("cl:price", ns)
                price_text = price_el.text if price_el is not None else "0"

                price = self._parse_price(price_text)
                if price > self.rent_limit or price == 0:
                    continue

                # Extract image from description HTML
                img_match = re.search(r'src="([^"]+)"', desc_html)
                img = img_match.group(1) if img_match else ""

                # Extract plain text description
                soup = BeautifulSoup(desc_html, "lxml")
                desc = soup.get_text(strip=True)

                listing_id = ""
                m = re.search(r'/(\d+)\.html', link)
                if m:
                    listing_id = m.group(1)

                results.append({
                    "id": f"craigslist_{listing_id}",
                    "url": link,
                    "title": title,
                    "price": price,
                    "address": "Toronto, ON",
                    "description": desc,
                    "image_url": img,
                })
        except ET.ParseError as e:
            logger.warning(f"[craigslist] RSS parse error: {e}")
        return results

    def _scrape_html(self, path: str) -> List[Dict]:
        """HTML fallback for craigslist."""
        url = f"{self.base_url}{path}?max_price={self.rent_limit}&availabilityMode=0"
        resp = self._get(url)
        if not resp:
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        results = []
        for li in soup.select(".result-row, li.cl-search-result"):
            try:
                link_el = li.select_one("a.result-title, a.cl-app-anchor")
                price_el = li.select_one(".result-price, .priceinfo")
                if not link_el:
                    continue
                link = link_el.get("href", "")
                title = link_el.get_text(strip=True)
                price = self._parse_price(price_el.get_text() if price_el else "0")
                if price > self.rent_limit or price == 0:
                    continue
                m = re.search(r'/(\d+)\.html', link)
                lid = m.group(1) if m else link
                results.append({
                    "id": f"craigslist_{lid}",
                    "url": link,
                    "title": title,
                    "price": price,
                    "address": "Toronto, ON",
                    "description": "",
                    "image_url": "",
                })
            except Exception as e:
                logger.debug(f"[craigslist] html parse error: {e}")
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

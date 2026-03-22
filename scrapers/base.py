"""Base scraper class."""
import time
import random
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


class BaseScraper(ABC):
    name: str = "base"
    base_url: str = ""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.rent_limit = config["RENT_LIMIT"]
        self.delay = config.get("scrape_delay_s", 2)
        self.session = self._make_session()

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        s.headers.update(DEFAULT_HEADERS)
        return s

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        try:
            resp = self.session.get(url, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"[{self.name}] GET {url} failed: {e}")
            return None

    def _sleep(self, extra: float = 0.0):
        time.sleep(self.delay + random.uniform(0.5, 1.5) + extra)

    @abstractmethod
    def scrape(self) -> List[Dict[str, Any]]:
        """Return list of raw listing dicts."""
        ...

    def _normalize(self, raw: Dict) -> Dict:
        """Ensure all listings have required keys."""
        return {
            "id": raw.get("id", ""),
            "source": self.name,
            "url": raw.get("url", ""),
            "title": raw.get("title", ""),
            "price": raw.get("price", 0),
            "address": raw.get("address", ""),
            "description": raw.get("description", ""),
            "image_url": raw.get("image_url", ""),
            "lat": raw.get("lat"),
            "lon": raw.get("lon"),
            "bedrooms": raw.get("bedrooms", ""),
            "bathrooms": raw.get("bathrooms", ""),
            "raw": raw,
        }

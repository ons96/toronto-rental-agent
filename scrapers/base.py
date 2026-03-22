"""Base scraper class.

HTTP strategy (tried in order per request):
  1. curl_cffi with browser TLS fingerprint (best anti-bot bypass)
  2. cloudscraper (Cloudflare JS-challenge bypass)
  3. requests with retry adapter (plain fallback)
"""
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

# Try importing optional anti-bot libs
try:
    import curl_cffi.requests as curl_requests
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False
    logger.debug("curl_cffi not available, using fallback")

try:
    import cloudscraper
    HAS_CLOUDSCRAPER = True
except ImportError:
    HAS_CLOUDSCRAPER = False
    logger.debug("cloudscraper not available, using fallback")


class BaseScraper(ABC):
    name: str = "base"
    base_url: str = ""
    # Set to True in subclasses that need Cloudflare bypass
    use_cloudscraper: bool = False
    # Set to True for sites that need TLS fingerprint spoofing
    use_curl_cffi: bool = True

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.rent_limit = config["RENT_LIMIT"]
        self.delay = config.get("scrape_delay_s", 2)
        self._session_requests = self._make_requests_session()
        self._session_cloudscraper = self._make_cloudscraper_session() if HAS_CLOUDSCRAPER else None

    def _make_requests_session(self) -> requests.Session:
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

    def _make_cloudscraper_session(self):
        if not HAS_CLOUDSCRAPER:
            return None
        try:
            return cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
        except Exception:
            return None

    def _get(self, url: str, **kwargs) -> Optional[requests.Response]:
        """Try curl_cffi → cloudscraper → requests in order."""
        # 1. curl_cffi: best TLS fingerprint spoofing
        if self.use_curl_cffi and HAS_CURL_CFFI:
            try:
                resp = curl_requests.get(
                    url,
                    impersonate="chrome124",
                    headers=DEFAULT_HEADERS,
                    timeout=15,
                    **{k: v for k, v in kwargs.items() if k in ("params", "allow_redirects")},
                )
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 403:
                    logger.debug(f"[{self.name}] curl_cffi 403 on {url}, trying cloudscraper")
                elif resp.status_code == 429:
                    logger.debug(f"[{self.name}] Rate limited (curl_cffi), backing off")
                    time.sleep(5)
                    return None
            except Exception as e:
                logger.debug(f"[{self.name}] curl_cffi failed: {e}")

        # 2. cloudscraper: handles Cloudflare JS challenges
        if (self.use_cloudscraper or self.use_curl_cffi) and self._session_cloudscraper:
            try:
                resp = self._session_cloudscraper.get(url, timeout=20, **kwargs)
                if resp.status_code == 200:
                    return resp
                elif resp.status_code == 429:
                    time.sleep(5)
                    return None
            except Exception as e:
                logger.debug(f"[{self.name}] cloudscraper failed: {e}")

        # 3. Plain requests fallback
        try:
            resp = self._session_requests.get(url, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"[{self.name}] GET {url} failed: {e}")
            return None

    def _post(self, url: str, **kwargs) -> Optional[requests.Response]:
        """POST via requests session."""
        try:
            resp = self._session_requests.post(url, timeout=15, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            logger.warning(f"[{self.name}] POST {url} failed: {e}")
            return None

    @property
    def session(self):
        """Compatibility shim - returns requests session."""
        return self._session_requests

    def _sleep(self, extra: float = 0.0):
        time.sleep(self.delay + random.uniform(0.3, 1.0) + extra)

    @abstractmethod
    def scrape(self) -> List[Dict[str, Any]]:
        """Return list of raw listing dicts."""
        ...

    def _normalize(self, raw: Dict) -> Dict:
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

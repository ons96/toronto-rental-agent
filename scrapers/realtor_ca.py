"""Realtor.ca Toronto rental scraper.

Uses the public CREA API (same one the website uses).
Blocked by Incapsula from datacenter IPs - run from residential IP only.
Include in deploy/residential_scraper.py alongside Kijiji.
"""
import re
import logging
import json
from typing import List, Dict, Any, Optional
from .base import BaseScraper

logger = logging.getLogger(__name__)

BASE = "https://www.realtor.ca"
API = "https://api2.realtor.ca/Listing.svc/PropertySearch_Post"

# Toronto bounding box
BOX = {
    "LatitudeMax": "43.86",
    "LatitudeMin": "43.58",
    "LongitudeMax": "-79.11",
    "LongitudeMin": "-79.64",
}


class RealtorCaScraper(BaseScraper):
    name = "realtor_ca"
    use_curl_cffi = True

    def scrape(self) -> List[Dict[str, Any]]:
        listings = []
        for page in range(1, 4):
            items = self._fetch_page(page)
            if not items:
                break
            listings.extend(items)
            self._sleep()
        logger.info(f"[realtor_ca] Found {len(listings)} listings")
        return [self._normalize(l) for l in listings]

    def _fetch_page(self, page: int) -> List[Dict]:
        data = {
            **BOX,
            "ZoomLevel": "11",
            "Sort": "6-D",
            # TransactionTypeId 3 = For Lease/Rent
            "TransactionTypeId": "3",
            # PropertyTypeGroupID 1 = Residential
            "PropertyTypeGroupID": "1",
            "PriceMin": "0",
            "PriceMax": str(self.rent_limit),
            "RecordsPerPage": "20",
            "CurrentPage": str(page),
            "ApplicationId": "1",
            "CultureId": "1",
            "Version": "7.0",
            "PropertySearchTypeId": "1",
        }
        try:
            resp = self._session_requests.post(
                API,
                data=data,
                headers={
                    **self.session.headers,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": BASE + "/",
                    "Origin": BASE,
                    "Accept": "application/json",
                },
                timeout=20,
            )
            resp.raise_for_status()
            d = resp.json()
            results = d.get("Results", [])
            return [self._parse_item(r) for r in results if self._parse_item(r)]
        except Exception as e:
            logger.warning(f"[realtor_ca] page {page} error: {e}")
            return []

    def _parse_item(self, item: Dict) -> Optional[Dict]:
        try:
            prop = item.get("Property", {})
            price_str = prop.get("Price", "0")
            # Price like "$1,200" or "$1,200/Monthly"
            nums = re.findall(r"[\d,]+", str(price_str))
            price = int(nums[0].replace(",", "")) if nums else 0
            if price == 0 or price > self.rent_limit:
                return None

            addr_obj = prop.get("Address", {})
            address = addr_obj.get("AddressText", "Toronto, ON")
            # AddressText like "123 Main St|Toronto, ON M5V 2T6"
            address = address.replace("|", ", ").strip()

            lat = item.get("Property", {}).get("Address", {}).get("Latitude")
            lon = item.get("Property", {}).get("Address", {}).get("Longitude")
            if not lat:
                # Try alternate paths
                lat = item.get("Individual", [{}])[0].get("Latitude") if item.get("Individual") else None

            photos = prop.get("Photo", [])
            img = photos[0].get("HighResPath", photos[0].get("MedResPath", "")) if photos else ""

            mls = item.get("MlsNumber", "")
            rel_url = item.get("RelativeURLEn", "")
            url = BASE + rel_url if rel_url else f"{BASE}/real-estate/{mls}"

            building = item.get("Building", {})
            beds = building.get("Bedrooms", "")
            baths = building.get("BathroomTotal", "")
            title = f"{price_str} - {address}"

            return {
                "id": f"realtor_ca_{mls}",
                "url": url,
                "title": title,
                "price": price,
                "address": address,
                "description": building.get("Type", "") + " " + prop.get("TypeId", ""),
                "image_url": img,
                "lat": float(lat) if lat else None,
                "lon": float(lon) if lon else None,
                "bedrooms": str(beds),
                "bathrooms": str(baths),
            }
        except Exception as e:
            logger.debug(f"[realtor_ca] item parse error: {e}")
            return None

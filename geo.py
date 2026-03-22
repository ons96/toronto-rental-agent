"""Geocoding and distance filtering for Toronto rental agent."""
import json
import logging
import math
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

TTC_STATIONS_FILE = Path(__file__).parent / "data" / "ttc_stations.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Simple in-process cache: address -> (lat, lon)
_geocode_cache: Dict[str, Optional[Tuple[float, float]]] = {}


def load_ttc_stations() -> List[Dict]:
    with open(TTC_STATIONS_FILE) as f:
        return json.load(f)["stations"]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two lat/lon points."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode(address: str, retries: int = 2) -> Optional[Tuple[float, float]]:
    """Geocode an address using Nominatim. Returns (lat, lon) or None."""
    if address in _geocode_cache:
        return _geocode_cache[address]

    query = address if "Toronto" in address or "ON" in address else f"{address}, Toronto, ON, Canada"

    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "ca",
                    "viewbox": "-79.64,43.58,-79.11,43.86",
                    "bounded": 1,
                },
                headers={"User-Agent": "toronto-rental-agent/1.0 (github.com/you/toronto-rental-agent)"},
                timeout=10,
            )
            results = resp.json()
            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                _geocode_cache[address] = (lat, lon)
                return lat, lon
        except Exception as e:
            logger.warning(f"[geo] geocode attempt {attempt+1} failed for '{address}': {e}")
            if attempt < retries:
                time.sleep(1.5)

    _geocode_cache[address] = None
    return None


def nearest_ttc(lat: float, lon: float, stations: List[Dict]) -> Tuple[float, str]:
    """Return (distance_m, station_name) for the nearest TTC subway station."""
    best_dist = float("inf")
    best_name = ""
    for s in stations:
        d = haversine_m(lat, lon, s["lat"], s["lon"])
        if d < best_dist:
            best_dist = d
            best_name = s["name"]
    return best_dist, best_name


def nearest_anchor(lat: float, lon: float, anchor_lat: float, anchor_lon: float) -> float:
    """Distance in metres from listing to anchor address."""
    return haversine_m(lat, lon, anchor_lat, anchor_lon)


def is_within_range(
    listing_lat: Optional[float],
    listing_lon: Optional[float],
    ttc_stations: List[Dict],
    anchor_lat: Optional[float],
    anchor_lon: Optional[float],
    max_m: int = 800,
) -> Tuple[bool, float, str]:
    """
    Returns (passes, nearest_dist_m, nearest_label).
    Passes if within max_m of ANY TTC station OR the anchor address.
    """
    if listing_lat is None or listing_lon is None:
        return False, float("inf"), "no_coords"

    ttc_dist, ttc_name = nearest_ttc(listing_lat, listing_lon, ttc_stations)
    if ttc_dist <= max_m:
        return True, ttc_dist, f"TTC: {ttc_name}"

    if anchor_lat is not None and anchor_lon is not None:
        anchor_dist = nearest_anchor(listing_lat, listing_lon, anchor_lat, anchor_lon)
        if anchor_dist <= max_m:
            return True, anchor_dist, "anchor address"
        # Return the closer of the two for reporting
        if anchor_dist < ttc_dist:
            return False, anchor_dist, "anchor address"

    return False, ttc_dist, f"TTC: {ttc_name}"

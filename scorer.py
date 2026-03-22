"""Composite scorer for rental listings.

Produces a 0-10 score balancing:
  - Price value (cheaper = better, relative to RENT_LIMIT)
  - Transit proximity
  - LLM quality signals (cleanliness, landlord vibe, scam safety)
"""
from typing import Dict


def score_listing(listing: Dict, config: Dict) -> float:
    """
    Returns a 0.0 - 10.0 score. Higher = better match.

    Weights:
      - Price value:      25%
      - Transit dist:     25%
      - Cleanliness:      15%
      - Landlord vibe:    20%
      - Scam safety:      15%
    """
    rent_limit = config.get("RENT_LIMIT", 2200)
    max_m = config.get("max_walking_m", 800)
    clf = listing.get("classification", listing)  # works for both pre/post DB

    # 1. Price value (0-10): cheaper relative to limit = higher score
    price = listing.get("price", rent_limit)
    if price <= 0:
        price_score = 5.0
    else:
        # Score drops linearly from 10 (free) to 0 (at rent_limit)
        price_score = max(0.0, 10.0 * (1 - price / rent_limit))

    # 2. Transit proximity (0-10): closer = higher
    dist_m = listing.get("transit_dist_m") or max_m
    transit_score = max(0.0, 10.0 * (1 - dist_m / max_m))

    # 3. LLM scores — already on 1-5 scale, normalize to 0-10
    clean_score = (clf.get("cleanliness", 3) - 1) / 4 * 10
    landlord_score = (clf.get("landlord_vibe", 3) - 1) / 4 * 10
    # scam_risk: high raw score = safe, so keep direction
    scam_score = (clf.get("scam_risk", 3) - 1) / 4 * 10

    composite = (
        price_score   * 0.25
        + transit_score * 0.25
        + clean_score   * 0.15
        + landlord_score * 0.20
        + scam_score    * 0.15
    )
    return round(min(10.0, max(0.0, composite)), 2)

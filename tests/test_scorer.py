"""Tests for scorer module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scorer import score_listing

BASE_CONFIG = {
    "RENT_LIMIT": 2000,
    "max_walking_m": 800,
}


def _listing(price=1500, dist_m=300, clean=4, landlord=4, scam=4):
    return {
        "price": price,
        "transit_dist_m": dist_m,
        "classification": {
            "cleanliness": clean,
            "landlord_vibe": landlord,
            "scam_risk": scam,
        },
    }


def test_score_range():
    s = score_listing(_listing(), BASE_CONFIG)
    assert 0.0 <= s <= 10.0


def test_cheaper_scores_higher():
    s_cheap = score_listing(_listing(price=800), BASE_CONFIG)
    s_expensive = score_listing(_listing(price=1900), BASE_CONFIG)
    assert s_cheap > s_expensive


def test_closer_transit_scores_higher():
    s_close = score_listing(_listing(dist_m=100), BASE_CONFIG)
    s_far = score_listing(_listing(dist_m=750), BASE_CONFIG)
    assert s_close > s_far


def test_better_quality_scores_higher():
    s_good = score_listing(_listing(clean=5, landlord=5, scam=5), BASE_CONFIG)
    s_bad = score_listing(_listing(clean=1, landlord=1, scam=1), BASE_CONFIG)
    assert s_good > s_bad


def test_perfect_score_near_10():
    s = score_listing(_listing(price=1, dist_m=0, clean=5, landlord=5, scam=5), BASE_CONFIG)
    assert s > 8.5

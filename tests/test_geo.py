"""Tests for geo module."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from geo import haversine_m, nearest_ttc, load_ttc_stations, is_within_range


def test_haversine_same_point():
    assert haversine_m(43.6452, -79.3806, 43.6452, -79.3806) == 0.0


def test_haversine_union_to_king():
    # Union Station to King Station ~450m on Line 1
    d = haversine_m(43.6452, -79.3806, 43.6488, -79.3779)
    assert 300 < d < 700, f"Expected ~450m, got {d:.0f}m"


def test_nearest_ttc_bloor_yonge():
    stations = load_ttc_stations()
    # Test point very close to Bloor-Yonge station
    dist, name = nearest_ttc(43.6709, -79.3858, stations)
    assert "Bloor" in name or "Yonge" in name
    assert dist < 100


def test_within_range_passes():
    stations = load_ttc_stations()
    # Right at Union Station
    passes, dist, label = is_within_range(43.6452, -79.3806, stations, None, None, 800)
    assert passes
    assert dist < 100


def test_within_range_fails_far_point():
    stations = load_ttc_stations()
    # Somewhere far from any TTC station (e.g. Scarborough bluffs)
    passes, dist, label = is_within_range(43.7100, -79.1800, stations, None, None, 800)
    assert not passes


def test_anchor_fallback():
    stations = load_ttc_stations()
    # Point 500m from anchor but >800m from any TTC station
    # Use a point near Scarborough with an anchor close by
    anchor_lat, anchor_lon = 43.7100, -79.1800  # same as listing
    passes, dist, label = is_within_range(
        43.7100, -79.1800, stations,
        anchor_lat, anchor_lon,
        max_m=800,
    )
    # anchor dist = 0m so should pass
    assert passes

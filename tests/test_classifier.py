"""Tests for classifier module (parser/filter only, no LLM calls)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from classifier import _parse_response, passes_filter, _default_classification


def test_parse_valid_json():
    raw = '{"private_room": true, "occupants": 2, "cleanliness": 4, "landlord_vibe": 4, "scam_risk": 5, "reasoning": "Looks good."}'
    result = _parse_response(raw)
    assert result["private_room"] is True
    assert result["occupants"] == 2
    assert result["cleanliness"] == 4
    assert result["scam_risk"] == 5


def test_parse_with_markdown_fences():
    raw = '```json\n{"private_room": false, "occupants": 6, "cleanliness": 1, "landlord_vibe": 1, "scam_risk": 1, "reasoning": "Scam."}\n```'
    result = _parse_response(raw)
    assert result["private_room"] is False
    assert result["occupants"] == 6


def test_parse_invalid_returns_default():
    result = _parse_response("this is not json")
    default = _default_classification()
    assert result["cleanliness"] == default["cleanliness"]


def test_clamps_values_out_of_range():
    raw = '{"private_room": true, "occupants": 99, "cleanliness": 99, "landlord_vibe": 0, "scam_risk": -5, "reasoning": "test"}'
    result = _parse_response(raw)
    assert result["occupants"] <= 20
    assert 1 <= result["cleanliness"] <= 5
    assert 1 <= result["landlord_vibe"] <= 5
    assert 1 <= result["scam_risk"] <= 5


CONFIG = {
    "max_occupants": 4,
    "min_cleanliness": 3,
    "min_landlord_vibe": 3,
    "max_scam_risk": 3,
}


def test_passes_filter_good_listing():
    clf = {"private_room": True, "occupants": 2, "cleanliness": 4, "landlord_vibe": 4, "scam_risk": 4}
    assert passes_filter(clf, CONFIG) is True


def test_fails_filter_shared_room():
    clf = {"private_room": False, "occupants": 2, "cleanliness": 4, "landlord_vibe": 4, "scam_risk": 4}
    assert passes_filter(clf, CONFIG) is False


def test_fails_filter_too_many_occupants():
    clf = {"private_room": True, "occupants": 8, "cleanliness": 4, "landlord_vibe": 4, "scam_risk": 4}
    assert passes_filter(clf, CONFIG) is False


def test_fails_filter_scam():
    clf = {"private_room": True, "occupants": 2, "cleanliness": 4, "landlord_vibe": 4, "scam_risk": 1}
    assert passes_filter(clf, CONFIG) is False
